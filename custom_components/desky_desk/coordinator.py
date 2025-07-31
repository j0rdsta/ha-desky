"""Data update coordinator for Desky Desk."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bluetooth import DeskBLEDevice
from .const import DOMAIN, RECONNECT_INTERVAL_SECONDS, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class DeskUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the Desky desk."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.unique_id}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self._device: DeskBLEDevice | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._shutdown = False

    @property
    def device(self) -> DeskBLEDevice | None:
        """Return the BLE device."""
        return self._device

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via BLE."""
        if self._device is None or not self._device.is_connected:
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect())
            raise UpdateFailed("Not connected to desk")

        # Request current status
        await self._device.get_status()
        
        # Return current data
        return {
            "height_cm": self._device.height_cm,
            "collision_detected": self._device.collision_detected,
            "is_moving": self._device.is_moving,
            "is_connected": self._device.is_connected,
        }

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh and establish connection."""
        # Get the BLE device
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.entry.data["address"], connectable=True
        )
        
        if not ble_device:
            raise ConfigEntryNotReady(
                f"Could not find Desky desk with address {self.entry.data['address']}"
            )
        
        # Create device instance
        self._device = DeskBLEDevice(ble_device)
        
        # Register callbacks
        self._device.register_notification_callback(self._handle_notification)
        self._device.register_disconnect_callback(self._handle_disconnect)
        
        # Start connection in background - don't block setup
        self._reconnect_task = asyncio.create_task(self._reconnect())
        
        # Set initial data to indicate disconnected state
        self.async_set_updated_data({
            "height_cm": 0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": False,
        })

    async def _reconnect(self) -> None:
        """Try to reconnect to the desk."""
        while not self._shutdown and self._device and not self._device.is_connected:
            _LOGGER.debug("Attempting to reconnect to desk")
            
            try:
                ble_device = bluetooth.async_ble_device_from_address(
                    self.hass, self.entry.data["address"], connectable=True
                )
                
                if ble_device:
                    self._device._ble_device = ble_device
                    if await self._device.connect():
                        _LOGGER.info("Reconnected to desk")
                        self.async_set_updated_data(await self._async_update_data())
                        break
                    else:
                        _LOGGER.debug("Connection attempt failed")
                else:
                    _LOGGER.debug("BLE device not found at address %s", self.entry.data["address"])
            except Exception as err:
                _LOGGER.debug("Reconnection failed: %s", err)
            
            await asyncio.sleep(RECONNECT_INTERVAL_SECONDS)

    def _handle_notification(self, height: float, collision: bool, moving: bool) -> None:
        """Handle notification from the desk."""
        # Update coordinator data immediately
        self.async_set_updated_data({
            "height_cm": height,
            "collision_detected": collision,
            "is_moving": moving,
            "is_connected": True,
        })

    def _handle_disconnect(self) -> None:
        """Handle disconnection from the desk."""
        self.async_set_updated_data({
            "height_cm": self._device.height_cm if self._device else 0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": False,
        })

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        self._shutdown = True
        
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        
        if self._device:
            await self._device.disconnect()