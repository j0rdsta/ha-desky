"""Sensor platform for Desky Desk."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LIGHT_COLORS, SENSITIVITY_LEVELS
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="height_display",
        translation_key="height_display",
        name="Height Display",
        icon="mdi:arrow-expand-vertical",
    ),
    SensorEntityDescription(
        key="led_color",
        translation_key="led_color",
        name="LED Color",
        icon="mdi:palette",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="vibration_intensity_display",
        translation_key="vibration_intensity_display",
        name="Vibration Intensity Display",
        icon="mdi:vibrate",
        native_unit_of_measurement="%",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for description in SENSOR_DESCRIPTIONS:
        entities.append(DeskSensor(coordinator, config_entry, description))
    
    async_add_entities(entities)


class DeskSensor(DeskEntity, SensorEntity):
    """Representation of a Desky desk sensor."""

    def __init__(self, coordinator, config_entry, description: SensorEntityDescription):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.unique_id}_{description.key}"
        self._attr_name = description.name

    @property
    def native_value(self) -> str | int | None:
        """Return the state of the sensor."""
        if not self.available:
            return None
        
        if self.entity_description.key == "height_display":
            height = self.coordinator.data.get("height_cm")
            unit = self.coordinator.data.get("unit_preference", "cm")
            
            if height is None:
                return None
            
            if unit == "inch":
                # Convert cm to inches
                height_in = height / 2.54
                self._attr_native_unit_of_measurement = UnitOfLength.INCHES
                return f"{height_in:.1f}"
            else:
                self._attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
                return f"{height:.1f}"
                
        elif self.entity_description.key == "led_color":
            color = self.coordinator.data.get("light_color")
            if color and color in LIGHT_COLORS:
                return LIGHT_COLORS[color]
            return "Unknown"
            
        elif self.entity_description.key == "vibration_intensity_display":
            intensity = self.coordinator.data.get("vibration_intensity")
            return intensity if intensity is not None else 0
        
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        
        if self.entity_description.key == "height_display":
            # Add raw height value
            attrs["height_cm"] = self.coordinator.data.get("height_cm")
            # Add height limits if enabled
            if self.coordinator.data.get("limits_enabled"):
                attrs["upper_limit_cm"] = self.coordinator.data.get("height_limit_upper")
                attrs["lower_limit_cm"] = self.coordinator.data.get("height_limit_lower")
                
        elif self.entity_description.key == "led_color":
            # Add numeric color value
            attrs["color_value"] = self.coordinator.data.get("light_color")
            attrs["brightness"] = self.coordinator.data.get("brightness")
            attrs["lighting_enabled"] = self.coordinator.data.get("lighting_enabled")
            
        elif self.entity_description.key == "vibration_intensity_display":
            # Add whether vibration is enabled
            attrs["vibration_enabled"] = self.coordinator.data.get("vibration_enabled")
        
        return attrs