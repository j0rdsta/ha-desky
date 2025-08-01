"""Base entity for Desky Desk integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeskUpdateCoordinator


class DeskEntity(CoordinatorEntity[DeskUpdateCoordinator]):
    """Base entity for all Desky desk entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeskUpdateCoordinator, config_entry) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(**self.coordinator.get_device_info())

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("is_connected", False)
    
    @property
    def _device(self):
        """Return the BLE device."""
        return self.coordinator.device

    @property
    def extra_state_attributes(self) -> dict:
        """Return common state attributes."""
        if self.coordinator.data is None:
            return {
                "connected": False,
            }
        return {
            "connected": self.coordinator.data.get("is_connected", False),
        }