"""Number platform for Desky Desk height sensor."""
from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_HEIGHT, DOMAIN, MAX_HEIGHT, MIN_HEIGHT
from .coordinator import DeskUpdateCoordinator
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)


NUMBER_DESCRIPTIONS = [
    NumberEntityDescription(
        key="height_limit_upper",
        translation_key="height_limit_upper",
        name="Upper Height Limit",
        icon="mdi:arrow-up-bold",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        native_min_value=MIN_HEIGHT,
        native_max_value=MAX_HEIGHT,
        native_step=1.0,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key="height_limit_lower",
        translation_key="height_limit_lower",
        name="Lower Height Limit",
        icon="mdi:arrow-down-bold",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        native_min_value=MIN_HEIGHT,
        native_max_value=MAX_HEIGHT,
        native_step=1.0,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key="vibration_intensity",
        translation_key="vibration_intensity",
        name="Vibration Intensity",
        icon="mdi:vibrate",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk number entities based on a config entry."""
    coordinator: DeskUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [DeskyHeightNumber(coordinator)]
    
    # Add additional number entities
    for description in NUMBER_DESCRIPTIONS:
        entities.append(DeskNumber(coordinator, entry, description))
    
    async_add_entities(entities)


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
        
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return self.coordinator.get_device_info()

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


class DeskNumber(DeskEntity, NumberEntity):
    """Representation of additional Desky desk number entities."""

    def __init__(self, coordinator, config_entry, description: NumberEntityDescription):
        """Initialize the number entity."""
        super().__init__(coordinator, config_entry)
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.unique_id}_{description.key}"
        self._attr_name = description.name
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_mode = description.mode

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if not self.available:
            return None
        
        key = self.entity_description.key
        return self.coordinator.data.get(key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        if not self.available or not self._device:
            return

        if self.entity_description.key == "height_limit_upper":
            await self._device.set_height_limit_upper(value)
            await self._device.get_limits()
        elif self.entity_description.key == "height_limit_lower":
            await self._device.set_height_limit_lower(value)
            await self._device.get_limits()
        elif self.entity_description.key == "vibration_intensity":
            await self._device.set_vibration_intensity(int(value))
            await self._device.get_vibration_intensity()

    @property
    def extra_state_attributes(self) -> dict:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        
        # Add limits enabled status for height limit entities
        if self.entity_description.key in ["height_limit_upper", "height_limit_lower"]:
            attrs["limits_enabled"] = self.coordinator.data.get("limits_enabled", False)
        
        return attrs