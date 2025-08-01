"""Binary sensor platform for Desky Desk collision detection."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeskUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk binary sensor entities based on a config entry."""
    coordinator: DeskUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DeskyCollisionSensor(coordinator)])


class DeskyCollisionSensor(CoordinatorEntity[DeskUpdateCoordinator], BinarySensorEntity):
    """Representation of desk collision detection sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_name = "Collision Detected"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the collision sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_collision"
        
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return self.coordinator.get_device_info()

    @property
    def is_on(self) -> bool | None:
        """Return true if collision is detected."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("collision_detected", False)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data.get("is_connected", False) if self.coordinator.data else False