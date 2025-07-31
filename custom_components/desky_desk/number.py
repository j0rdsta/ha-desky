"""Number platform for Desky Desk height sensor."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_HEIGHT, DOMAIN, MAX_HEIGHT, MIN_HEIGHT
from .coordinator import DeskUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk number entities based on a config entry."""
    coordinator: DeskUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DeskyHeightNumber(coordinator)])


class DeskyHeightNumber(CoordinatorEntity[DeskUpdateCoordinator], NumberEntity):
    """Representation of desk height as a number entity."""

    _attr_native_min_value = MIN_HEIGHT
    _attr_native_max_value = MAX_HEIGHT
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_mode = NumberMode.BOX
    _attr_has_entity_name = True
    _attr_name = "Height"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the height number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_height"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.unique_id)},
            "name": coordinator.device.name if coordinator.device else "Desky Desk",
            "manufacturer": "Desky",
            "model": "Standing Desk",
        }

    @property
    def native_value(self) -> float | None:
        """Return the current height in cm."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("height_cm", DEFAULT_HEIGHT)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data.get("is_connected", False) if self.coordinator.data else False

    async def async_set_native_value(self, value: float) -> None:
        """Set the desk height to a specific value in cm."""
        if not self.coordinator.device:
            return
        
        # Use the move_to_height method for precise positioning
        await self.coordinator.device.move_to_height(value)
        
        # Request coordinator update to track movement
        await self.coordinator.async_request_refresh()