"""Sensor platform for Desky Desk."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LIGHT_COLORS
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

# State comes from the coordinator, so there are no updates to limit
PARALLEL_UPDATES = 0

CM_PER_INCH = 2.54

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key="height_display",
        translation_key="height_display",
    ),
    SensorEntityDescription(
        key="led_color",
        translation_key="led_color",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="vibration_intensity_display",
        translation_key="vibration_intensity_display",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky sensor platform."""
    async_add_entities(
        DeskSensor(entry.runtime_data, description)
        for description in SENSOR_DESCRIPTIONS
    )


class DeskSensor(DeskEntity, SensorEntity):
    """Representation of a Desky desk sensor."""

    def __init__(
        self, coordinator: DeskUpdateCoordinator, description: SensorEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        data = self.coordinator.data

        if self.entity_description.key == "height_display":
            if data.unit_preference == "in":
                return round(data.height_cm / CM_PER_INCH, 1)
            return round(data.height_cm, 1)

        if self.entity_description.key == "led_color":
            color = data.light_color
            if color and color in LIGHT_COLORS:
                return LIGHT_COLORS[color]
            return "Unknown"

        if self.entity_description.key == "vibration_intensity_display":
            intensity = data.vibration_intensity
            return intensity if intensity is not None else 0

        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, which follows the desk's display unit for the height."""
        if self.entity_description.key == "height_display":
            if self.coordinator.data.unit_preference == "in":
                return UnitOfLength.INCHES
            return UnitOfLength.CENTIMETERS
        return super().native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        data = self.coordinator.data

        if self.entity_description.key == "height_display":
            attrs: dict[str, Any] = {"height_cm": data.height_cm}
            # Add height limits if enabled
            if data.limits_enabled:
                attrs["upper_limit_cm"] = data.height_limit_upper
                attrs["lower_limit_cm"] = data.height_limit_lower
            return attrs

        if self.entity_description.key == "led_color":
            return {
                "color_value": data.light_color,
                "brightness": data.brightness,
                "lighting_enabled": data.lighting_enabled,
            }

        if self.entity_description.key == "vibration_intensity_display":
            return {"vibration_enabled": data.vibration_enabled}

        return None
