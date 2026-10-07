"""Data update coordinator for Desky Desk."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
import logging
from typing import cast

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bluetooth import DeskBLEDevice, DeskError
from .const import (
    CONF_STANDING_THRESHOLD,
    DEFAULT_STANDING_THRESHOLD,
    DOMAIN,
    RECONNECT_BACKOFF_MAX_SECONDS,
    RECONNECT_BACKOFF_MIN_SECONDS,
    UPDATE_INTERVAL_SECONDS,
)

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
        self.standing_threshold: float = entry.options.get(
            CONF_STANDING_THRESHOLD, DEFAULT_STANDING_THRESHOLD
        )
        self._device: DeskBLEDevice | None = None
        # True while the entry is loaded, so a lost connection is re-established
        self._expected_connected = False
        # True once the outage is logged, so it is logged once, not per retry
        self._unavailable_logged = False
        self._failed_attempts = 0
        self._cancel_retry: CALLBACK_TYPE | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        # True until the first poll after a connection, which asks again for
        # settings the desk did not report while connecting
        self._recheck_settings = False

    @property
    def device(self) -> DeskBLEDevice:
        """Return the BLE device, which async_connect() creates."""
        assert self._device is not None  # entities exist only after connecting
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

        self._expected_connected = True
        self._recheck_settings = True
        entry = self.config_entry
        # Every advertisement hands over the route the desk is heard on now, and
        # one from a desk that is not connected starts a reconnect
        entry.async_on_unload(
            bluetooth.async_register_callback(
                self.hass,
                self._async_handle_advertisement,
                BluetoothCallbackMatcher(address=self._address, connectable=True),
                BluetoothScanningMode.ACTIVE,
            )
        )
        entry.async_on_unload(
            bluetooth.async_track_unavailable(
                self.hass,
                self._async_handle_unavailable,
                self._address,
                connectable=True,
            )
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
            _LOGGER.debug(
                "Updated device registry with BLE device information: %s",
                update_kwargs,
            )

        except Exception as err:
            _LOGGER.error("Failed to update device registry: %s", err)

    async def _async_update_data(self) -> DeskData:
        """Update data via BLE.

        A disconnected desk is not an update failure: its entities report
        unavailable from the data, and reconnecting is driven by advertisements.
        """
        device = self.device
        if device.is_connected:
            try:
                await self._async_request_status(device)
            except DeskError:
                # A write that fails on an open connection means the desk is gone
                await self._async_drop_connection()

            if any(
                [device.manufacturer_name, device.model_number, device.serial_number]
            ):
                _LOGGER.debug(
                    "Device info in coordinator - Manufacturer: %s, Model: %s, Serial: %s",
                    device.manufacturer_name,
                    device.model_number,
                    device.serial_number,
                )
            else:
                _LOGGER.debug("No device information available in coordinator")

        return self._build_data(device)

    async def _async_request_status(self, device: DeskBLEDevice) -> None:
        """Request the desk's status, and its settings if they are still unknown.

        A desk reached just after it powers up ignores the settings request
        sent while connecting. Asking once more at the first scheduled poll
        catches that; asking at every poll would wake the display of a desk
        that never reports its unit. The refresh straight after setup is not
        a scheduled poll, so it is skipped.
        """
        if self._recheck_settings and self.data is not None:
            self._recheck_settings = False
            if device.unit_preference is None or device.touch_mode is None:
                _LOGGER.debug("Asking the desk at %s for its settings", self._address)
                await device.get_settings()
                return
        await device.get_status()

    @callback
    def _async_handle_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        """Reconnect through whichever adapter or proxy heard the desk."""
        self.device.set_ble_device(service_info.device)
        self._async_request_reconnect()

    @callback
    def _async_handle_unavailable(
        self, service_info: BluetoothServiceInfoBleak
    ) -> None:
        """Handle the Bluetooth stack no longer seeing the desk."""
        if self.device.is_connected:
            # The desk may stop advertising while connected, so check the
            # connection itself rather than dropping it
            self.config_entry.async_create_background_task(
                self.hass,
                self._async_check_connection(),
                name=f"{DOMAIN} check connection {self._address}",
            )
            return
        # Nothing can be reached until the desk advertises again, and that
        # advertisement reconnects at once rather than after the backoff
        self._async_cancel_retry()
        self._failed_attempts = 0

    async def _async_check_connection(self) -> None:
        """Drop the connection if the desk no longer answers on it."""
        try:
            await self.device.get_status()
        except DeskError:
            await self._async_drop_connection()

    async def _async_drop_connection(self) -> None:
        """Close a connection the desk no longer answers on."""
        _LOGGER.debug("The desk at %s stopped responding", self._address)
        device = self.device
        await device.disconnect()
        self._handle_disconnect(device)

    @callback
    def _async_request_reconnect(self) -> None:
        """Start a reconnect unless one is running, waiting or not wanted."""
        if not self._expected_connected or self.device.is_connected:
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        # While backing off after failures, the retry timer reconnects instead
        if self._cancel_retry is not None:
            return
        # A config entry background task is cancelled when the entry unloads
        self._reconnect_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_reconnect(),
            name=f"{DOMAIN} reconnect {self._address}",
        )

    async def _async_reconnect(self) -> None:
        """Try to reconnect once, scheduling a retry with backoff if it fails."""
        device = self.device
        if not await device.connect():
            self._failed_attempts += 1
            delay = min(
                RECONNECT_BACKOFF_MIN_SECONDS * 2 ** (self._failed_attempts - 1),
                RECONNECT_BACKOFF_MAX_SECONDS,
            )
            _LOGGER.debug(
                "Could not reconnect to the desk at %s, retrying in %d seconds",
                self._address,
                delay,
            )
            self._cancel_retry = async_call_later(self.hass, delay, self._async_retry)
            return

        self._failed_attempts = 0
        self._recheck_settings = True
        if self._unavailable_logged:
            _LOGGER.info("The desk at %s is available again", self._address)
            self._unavailable_logged = False
        self.async_set_updated_data(self._build_data(device))
        await self.async_update_device_registry()

    @callback
    def _async_retry(self, _now: datetime) -> None:
        """Retry reconnecting once the backoff delay has passed."""
        self._cancel_retry = None
        if (
            bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            is None
        ):
            # The desk is out of range; its next advertisement reconnects
            self._failed_attempts = 0
            return
        self._async_request_reconnect()

    @callback
    def _async_cancel_retry(self) -> None:
        """Cancel a scheduled reconnect retry."""
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None

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
        if not self._expected_connected:
            return
        if not self._unavailable_logged:
            _LOGGER.warning("The desk at %s is unavailable", self._address)
            self._unavailable_logged = True
        # The desk usually advertises again at once, but do not wait for it
        self._async_request_reconnect()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator.

        Runs when the config entry unloads, including after a failed setup.
        """
        self._expected_connected = False
        self._async_cancel_retry()
        await super().async_shutdown()

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self._device:
            await self._device.disconnect()
