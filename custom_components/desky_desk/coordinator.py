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
from homeassistant.helpers import device_registry as dr
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
    
    def get_device_info(self) -> dict[str, Any]:
        """Return device information for Home Assistant device registry."""
        # Get device information from coordinator data with fallbacks
        data = self.data or {}
        
        # Use device information from BLE Device Information Service if available
        manufacturer = data.get("manufacturer_name") or "Desky"
        model = data.get("model_number") or "Standing Desk"
        
        device_info = {
            "identifiers": {(DOMAIN, self.entry.unique_id)},
            "name": self.device.name if self.device else "Desky Desk",
            "manufacturer": manufacturer,
            "model": model,
        }
        
        # Add optional device information fields if available
        if data.get("serial_number"):
            device_info["serial_number"] = data["serial_number"]
        if data.get("hardware_revision"):
            device_info["hw_version"] = data["hardware_revision"]
        if data.get("firmware_revision"):
            device_info["sw_version"] = data["firmware_revision"]
        
        return device_info
    
    async def async_update_device_registry(self) -> None:
        """Update device registry with information from BLE Device Information Service."""
        if not self._device or not self.data:
            return
            
        # Only update if we have actual device information from BLE
        if not any([
            self.data.get("manufacturer_name"),
            self.data.get("model_number"),
            self.data.get("serial_number"),
            self.data.get("firmware_revision"),
            self.data.get("hardware_revision"),
            self.data.get("software_revision")
        ]):
            return
            
        try:
            device_registry = dr.async_get(self.hass)
            
            # Find the device by identifiers
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self.entry.unique_id)}
            )
            
            if device:
                # Prepare update kwargs - only include non-None values
                update_kwargs = {}
                
                if self.data.get("manufacturer_name"):
                    # Only update if it's not the generic placeholder
                    if self.data["manufacturer_name"] != "Manufacturer Name":
                        update_kwargs["manufacturer"] = self.data["manufacturer_name"]
                    
                if self.data.get("model_number"):
                    update_kwargs["model"] = self.data["model_number"]
                    
                if self.data.get("serial_number"):
                    # Only update if it's not the generic placeholder
                    if self.data["serial_number"] != "Serial Number":
                        update_kwargs["serial_number"] = self.data["serial_number"]
                    
                if self.data.get("hardware_revision"):
                    # Only update if it's not the generic placeholder
                    if self.data["hardware_revision"] != "Hardware Revision":
                        update_kwargs["hw_version"] = self.data["hardware_revision"]
                    
                if self.data.get("firmware_revision"):
                    update_kwargs["sw_version"] = self.data["firmware_revision"]
                
                if update_kwargs:
                    device_registry.async_update_device(
                        device.id,
                        **update_kwargs
                    )
                    _LOGGER.info(
                        "Updated device registry with BLE device information: %s",
                        update_kwargs
                    )
                    
        except Exception as err:
            _LOGGER.error("Failed to update device registry: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via BLE."""
        if self._device is None or not self._device.is_connected:
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect())
            raise UpdateFailed("Not connected to desk")

        # Request current status
        await self._device.get_status()
        
        # Build data dictionary
        data = {
            "height_cm": self._device.height_cm,
            "collision_detected": self._device.collision_detected,
            "is_moving": self._device.is_moving,
            "movement_direction": self._device.movement_direction,
            "is_connected": self._device.is_connected,
            # New device features
            "light_color": self._device.light_color,
            "brightness": self._device.brightness,
            "lighting_enabled": self._device.lighting_enabled,
            "vibration_enabled": self._device.vibration_enabled,
            "vibration_intensity": self._device.vibration_intensity,
            "lock_status": self._device.lock_status,
            "sensitivity_level": self._device.sensitivity_level,
            "height_limit_upper": self._device.height_limit_upper,
            "height_limit_lower": self._device.height_limit_lower,
            "limits_enabled": self._device.limits_enabled,
            "touch_mode": self._device.touch_mode,
            "unit_preference": self._device.unit_preference,
            # Device information from Device Information Service (0x180A)
            "manufacturer_name": self._device.manufacturer_name,
            "model_number": self._device.model_number,
            "serial_number": self._device.serial_number,
            "hardware_revision": self._device.hardware_revision,
            "firmware_revision": self._device.firmware_revision,
            "software_revision": self._device.software_revision,
        }
        
        # Log device info for debugging
        if any([self._device.manufacturer_name, self._device.model_number, self._device.serial_number]):
            _LOGGER.info(
                "Device info in coordinator - Manufacturer: %s, Model: %s, Serial: %s",
                self._device.manufacturer_name,
                self._device.model_number,
                self._device.serial_number
            )
        else:
            _LOGGER.debug("No device information available in coordinator")
        
        return data

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
            "movement_direction": None,
            "is_connected": False,
            # New device features with default values
            "light_color": None,
            "brightness": None,
            "lighting_enabled": None,
            "vibration_enabled": None,
            "vibration_intensity": None,
            "lock_status": False,
            "sensitivity_level": None,
            "height_limit_upper": None,
            "height_limit_lower": None,
            "limits_enabled": False,
            "touch_mode": None,
            "unit_preference": None,
            # Device information with default values
            "manufacturer_name": None,
            "model_number": None,
            "serial_number": None,
            "hardware_revision": None,
            "firmware_revision": None,
            "software_revision": None,
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
                        data = await self._async_update_data()
                        self.async_set_updated_data(data)
                        # Update device registry with BLE device information
                        await self.async_update_device_registry()
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
            "movement_direction": self._device.movement_direction if self._device else None,
            "is_connected": True,
            # Include all device attributes from current state
            "light_color": self._device.light_color if self._device else None,
            "brightness": self._device.brightness if self._device else None,
            "lighting_enabled": self._device.lighting_enabled if self._device else None,
            "vibration_enabled": self._device.vibration_enabled if self._device else None,
            "vibration_intensity": self._device.vibration_intensity if self._device else None,
            "lock_status": self._device.lock_status if self._device else False,
            "sensitivity_level": self._device.sensitivity_level if self._device else None,
            "height_limit_upper": self._device.height_limit_upper if self._device else None,
            "height_limit_lower": self._device.height_limit_lower if self._device else None,
            "limits_enabled": self._device.limits_enabled if self._device else False,
            "touch_mode": self._device.touch_mode if self._device else None,
            "unit_preference": self._device.unit_preference if self._device else None,
            # Include device information
            "manufacturer_name": self._device.manufacturer_name if self._device else None,
            "model_number": self._device.model_number if self._device else None,
            "serial_number": self._device.serial_number if self._device else None,
            "hardware_revision": self._device.hardware_revision if self._device else None,
            "firmware_revision": self._device.firmware_revision if self._device else None,
            "software_revision": self._device.software_revision if self._device else None,
        })

    def _handle_disconnect(self) -> None:
        """Handle disconnection from the desk."""
        self.async_set_updated_data({
            "height_cm": self._device.height_cm if self._device else 0,
            "collision_detected": False,
            "is_moving": False,
            "movement_direction": None,
            "is_connected": False,
            # Preserve last known values for device features
            "light_color": self._device.light_color if self._device else None,
            "brightness": self._device.brightness if self._device else None,
            "lighting_enabled": self._device.lighting_enabled if self._device else None,
            "vibration_enabled": self._device.vibration_enabled if self._device else None,
            "vibration_intensity": self._device.vibration_intensity if self._device else None,
            "lock_status": self._device.lock_status if self._device else False,
            "sensitivity_level": self._device.sensitivity_level if self._device else None,
            "height_limit_upper": self._device.height_limit_upper if self._device else None,
            "height_limit_lower": self._device.height_limit_lower if self._device else None,
            "limits_enabled": self._device.limits_enabled if self._device else False,
            "touch_mode": self._device.touch_mode if self._device else None,
            "unit_preference": self._device.unit_preference if self._device else None,
            # Preserve device information during disconnection
            "manufacturer_name": self._device.manufacturer_name if self._device else None,
            "model_number": self._device.model_number if self._device else None,
            "serial_number": self._device.serial_number if self._device else None,
            "hardware_revision": self._device.hardware_revision if self._device else None,
            "firmware_revision": self._device.firmware_revision if self._device else None,
            "software_revision": self._device.software_revision if self._device else None,
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