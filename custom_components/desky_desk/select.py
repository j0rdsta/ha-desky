"""Select platform for Desky Desk."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SENSITIVITY_LEVELS, TOUCH_MODES
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

SELECT_DESCRIPTIONS = [
    SelectEntityDescription(
        key="sensitivity",
        translation_key="sensitivity",
        name="Collision Sensitivity",
        icon="mdi:car-brake-alert",
        options=["High", "Medium", "Low"],
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="touch_mode",
        translation_key="touch_mode",
        name="Touch Mode",
        icon="mdi:gesture-tap",
        options=["One press", "Press and hold"],
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="unit",
        translation_key="unit",
        name="Display Unit",
        icon="mdi:ruler",
        options=["cm", "in"],
        entity_category=EntityCategory.CONFIG,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky select platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for description in SELECT_DESCRIPTIONS:
        entities.append(DeskSelect(coordinator, config_entry, description))
    
    async_add_entities(entities)


class DeskSelect(DeskEntity, SelectEntity):
    """Representation of a Desky desk select entity."""

    def __init__(self, coordinator, config_entry, description: SelectEntityDescription):
        """Initialize the select entity."""
        super().__init__(coordinator, config_entry)
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.unique_id}_{description.key}"
        self._attr_name = description.name
        self._attr_options = description.options

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        if not self.available:
            return None
        
        if self.entity_description.key == "sensitivity":
            level = self.coordinator.data.get("sensitivity_level")
            if level and level in SENSITIVITY_LEVELS:
                return SENSITIVITY_LEVELS[level]
        elif self.entity_description.key == "touch_mode":
            mode = self.coordinator.data.get("touch_mode")
            if mode is not None and mode in TOUCH_MODES:
                return TOUCH_MODES[mode]
        elif self.entity_description.key == "unit":
            return self.coordinator.data.get("unit_preference")
        
        return None

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        if not self.available or not self._device:
            return

        if self.entity_description.key == "sensitivity":
            # Find the level key for the selected option
            level = None
            for key, value in SENSITIVITY_LEVELS.items():
                if value == option:
                    level = key
                    break
            
            if level:
                await self._device.set_sensitivity(level)
                await self._device.get_sensitivity()
                
        elif self.entity_description.key == "touch_mode":
            # Find the mode key for the selected option
            mode = None
            for key, value in TOUCH_MODES.items():
                if value == option:
                    mode = key
                    break
            
            if mode is not None:
                await self._device.set_touch_mode(mode)
                # Note: There's no get_touch_mode command in the Android app
                
        elif self.entity_description.key == "unit":
            if option in ["cm", "in"]:
                await self._device.set_unit(option)
                # Note: Unit preference is auto-detected from height value