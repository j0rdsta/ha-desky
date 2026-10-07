"""Data update coordinator for Desky Desk."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
import logging
from typing import cast

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bluetooth import DeskBLEDevice
from .const import DOMAIN, RECONNECT_INTERVAL_SECONDS, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

type DeskyConfigEntry = ConfigEntry[DeskUpdateCoordinator]

# Values some desks report in the Device Information Service instead of real data
DEVICE_INFO_PLACEHOLDERS = frozenset(
    {
        "Manufacturer Name",
        "Model Number",
        "Serial Number",
        "Hardware Revision",
        "Firmware Revision",
    }
)


@dataclass(frozen=True, slots=True)
class DeskData:
    """Snapshot of the desk state shared with every entity."""

    is_connected: bool
    height_cm: float
    collision_detected: bool
    is_moving: bool
    movement_direction: str | None
    light_color: int | None
    brightness: int | None
    lighting_enabled: bool | None
    vibration_enabled: bool | None
    vibration_intensity: int | None
    lock_status: bool
    sensitivity_level: int | None
    height_limit_upper: float | None
    height_limit_lower: float | None
    limits_enabled: bool
    touch_mode: int | None
    unit_preference: str | None
    # Device Information Service (0x180A)
    manufacturer_name: str | None
    model_number: str | None
    serial_number: str | None
    hardware_revision: str | None
    firmware_revision: str | None
    software_revision: str | None


class DeskUpdateCoordinator(DataUpdateCoordinator[DeskData]):
    """Class to manage fetching data from the Desky desk."""

    config_entry: DeskyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: DeskyConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.unique_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self._address: str = entry.data[CONF_ADDRESS]
        self._device: DeskBLEDevice | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._shutdown = False

    @property
    def device(self) -> DeskBLEDevice | None:
        """Return the BLE device."""
        return self._device

    async def async_connect(self) -> None:
        """Find the desk and connect to it before the first refresh.

        Raises ConfigEntryNotReady when the desk cannot be reached, so Home
        Assistant retries setup instead of loading with made-up state.
        """
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if ble_device is None:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"address": self._address},
            )

        self._device = device = DeskBLEDevice(ble_device)
        device.register_notification_callback(
            partial(self._handle_notification, device)
        )
        device.register_disconnect_callback(partial(self._handle_disconnect, device))

        if not await device.connect():
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"address": self._address},
            )

    @staticmethod
    def _build_data(device: DeskBLEDevice) -> DeskData:
        """Build the data snapshot from the device's current state."""
        connected = device.is_connected
        return DeskData(
            is_connected=connected,
            height_cm=device.height_cm,
            # Movement and collision are only meaningful while connected
            collision_detected=connected and device.collision_detected,
            is_moving=connected and device.is_moving,
            movement_direction=device.movement_direction if connected else None,
            light_color=device.light_color,
            brightness=device.brightness,
            lighting_enabled=device.lighting_enabled,
            vibration_enabled=device.vibration_enabled,
            vibration_intensity=device.vibration_intensity,
            lock_status=device.lock_status,
            sensitivity_level=device.sensitivity_level,
            height_limit_upper=device.height_limit_upper,
            height_limit_lower=device.height_limit_lower,
            limits_enabled=device.limits_enabled,
            touch_mode=device.touch_mode,
            unit_preference=device.unit_preference,
            manufacturer_name=device.manufacturer_name,
            model_number=device.model_number,
            serial_number=device.serial_number,
            hardware_revision=device.hardware_revision,
            firmware_revision=device.firmware_revision,
            software_revision=device.software_revision,
        )

    def _device_registry_fields(self) -> dict[str, str]:
        """Return the device registry fields the desk reported, without placeholders."""
        if self.data is None:
            return {}
        fields = {
            "manufacturer": self.data.manufacturer_name,
            "model": self.data.model_number,
            "serial_number": self.data.serial_number,
            "hw_version": self.data.hardware_revision,
            "sw_version": self.data.firmware_revision,
        }
        return {
            key: value
            for key, value in fields.items()
            if value and value not in DEVICE_INFO_PLACEHOLDERS
        }

    def get_device_info(self) -> dr.DeviceInfo:
        """Return device information for Home Assistant device registry."""
        fields = self._device_registry_fields()
        device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, cast(str, self.config_entry.unique_id))},
            connections={(dr.CONNECTION_BLUETOOTH, self._address)},
            name=self._device.name if self._device else "Desky Desk",
            manufacturer=fields.get("manufacturer", "Desky"),
            model=fields.get("model", "Standing Desk"),
        )
        if serial_number := fields.get("serial_number"):
            device_info["serial_number"] = serial_number
        if hw_version := fields.get("hw_version"):
            device_info["hw_version"] = hw_version
        if sw_version := fields.get("sw_version"):
            device_info["sw_version"] = sw_version
        return device_info

    async def async_update_device_registry(self) -> None:
        """Update device registry with information from BLE Device Information Service."""
        if not self._device:
            return

        # Only update if we have actual device information from BLE
        if not (update_kwargs := self._device_registry_fields()):
            return

        try:
            # async_get_or_create() matches on identifiers, so no separate
            # lookup is needed. device_registry.async_get_device() is
            # deprecated and stops working in HA 2027.8.
            dr.async_get(self.hass).async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={(DOMAIN, cast(str, self.config_entry.unique_id))},
                connections={(dr.CONNECTION_BLUETOOTH, self._address)},
                name=self._device.name,
                manufacturer=update_kwargs.get("manufacturer", UNDEFINED),
                model=update_kwargs.get("model", UNDEFINED),
                serial_number=update_kwargs.get("serial_number", UNDEFINED),
                hw_version=update_kwargs.get("hw_version", UNDEFINED),
                sw_version=update_kwargs.get("sw_version", UNDEFINED),
            )
            _LOGGER.info(
                "Updated device registry with BLE device information: %s",
                update_kwargs,
            )

        except Exception as err:
            _LOGGER.error("Failed to update device registry: %s", err)

    async def _async_update_data(self) -> DeskData:
        """Update data via BLE."""
        if self._device is None or not self._device.is_connected:
            self._start_reconnect()
            raise UpdateFailed("Not connected to desk")

        # Request current status
        await self._device.get_status()

        # Log device info for debugging
        if any(
            [
                self._device.manufacturer_name,
                self._device.model_number,
                self._device.serial_number,
            ]
        ):
            _LOGGER.info(
                "Device info in coordinator - Manufacturer: %s, Model: %s, Serial: %s",
                self._device.manufacturer_name,
                self._device.model_number,
                self._device.serial_number,
            )
        else:
            _LOGGER.debug("No device information available in coordinator")

        return self._build_data(self._device)

    def _start_reconnect(self) -> None:
        """Start the reconnect loop unless it is already running."""
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        # A config entry background task is cancelled when the entry unloads
        self._reconnect_task = self.config_entry.async_create_background_task(
            self.hass, self._reconnect(), name=f"{DOMAIN} reconnect {self._address}"
        )

    async def _reconnect(self) -> None:
        """Try to reconnect to the desk."""
        while not self._shutdown and self._device and not self._device.is_connected:
            _LOGGER.debug("Attempting to reconnect to desk")

            try:
                ble_device = bluetooth.async_ble_device_from_address(
                    self.hass, self._address, connectable=True
                )

                if ble_device:
                    self._device._ble_device = ble_device
                    if await self._device.connect():
                        _LOGGER.info("Reconnected to desk")
                        data = await self._async_update_data()
                        self.async_set_updated_data(data)
                        # Update device registry with BLE device information
                        await self.async_update_device_registry()
                        break
                    _LOGGER.debug("Connection attempt failed")
                else:
                    _LOGGER.debug("BLE device not found at address %s", self._address)
            except Exception as err:
                _LOGGER.debug("Reconnection failed: %s", err)

            await asyncio.sleep(RECONNECT_INTERVAL_SECONDS)

    def _handle_notification(
        self, device: DeskBLEDevice, height: float, collision: bool, moving: bool
    ) -> None:
        """Handle notification from the desk.

        The height, collision and moving values mirror the device state, which
        _build_data() reads directly.
        """
        self.async_set_updated_data(self._build_data(device))

    def _handle_disconnect(self, device: DeskBLEDevice) -> None:
        """Handle disconnection from the desk."""
        self.async_set_updated_data(self._build_data(device))

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator.

        Runs when the config entry unloads, including after a failed setup.
        """
        await super().async_shutdown()
        self._shutdown = True

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self._device:
            await self._device.disconnect()
