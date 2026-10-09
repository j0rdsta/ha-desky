"""Binary sensor platform for Desky Desk collision detection."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity

# State comes from the coordinator, so there are no updates to limit
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Desky Desk binary sensor entities based on a config entry."""
    async_add_entities([DeskyCollisionSensor(entry.runtime_data)])


class DeskyCollisionSensor(DeskEntity, BinarySensorEntity):
    """Representation of desk collision detection sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "collision"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the collision sensor."""
        super().__init__(coordinator, "collision")

    @property
    def is_on(self) -> bool:
        """Return true if collision is detected."""
        return self.coordinator.data.collision_detected
