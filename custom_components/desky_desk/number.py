"""Number platform for Desky Desk height sensor."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_HEIGHT, MIN_HEIGHT
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command
from .validation import LIMIT_LOWER, LIMIT_UPPER, validate_height_limit

_LOGGER = logging.getLogger(__name__)

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1


NUMBER_DESCRIPTIONS = [
    NumberEntityDescription(
        key="height_limit_upper",
        translation_key="height_limit_upper",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        native_min_value=MIN_HEIGHT,
        native_max_value=MAX_HEIGHT,
        native_step=1.0,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    NumberEntityDescription(
        key="height_limit_lower",
        translation_key="height_limit_lower",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        native_min_value=MIN_HEIGHT,
        native_max_value=MAX_HEIGHT,
        native_step=1.0,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    NumberEntityDescription(
        key="vibration_intensity",
        translation_key="vibration_intensity",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk number entities based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        [
            DeskyHeightNumber(coordinator),
            *(
                DeskNumber(coordinator, description)
                for description in NUMBER_DESCRIPTIONS
            ),
        ]
    )


class DeskyHeightNumber(DeskEntity, NumberEntity):
    """Representation of desk height as a number entity."""

    _attr_native_min_value = MIN_HEIGHT
    _attr_native_max_value = MAX_HEIGHT
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfLength.CENTIMETERS
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "height"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the height number entity."""
        super().__init__(coordinator, "height")

    @property
    def native_value(self) -> float:
        """Return the current height in cm."""
        return self.coordinator.data.height_cm

    @desk_command
    async def async_set_native_value(self, value: float) -> None:
        """Set the desk height to a specific value in cm."""
        # Use the move_to_height method for precise positioning
        await self._device.move_to_height(value)

        # Request coordinator update to track movement
        await self.coordinator.async_request_refresh()


class DeskNumber(DeskEntity, NumberEntity):
    """Representation of additional Desky desk number entities."""

    def __init__(
        self, coordinator: DeskUpdateCoordinator, description: NumberEntityDescription
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        data = self.coordinator.data
        key = self.entity_description.key
        if key == "height_limit_upper":
            return data.height_limit_upper
        if key == "height_limit_lower":
            return data.height_limit_lower
        if key == "vibration_intensity":
            return data.vibration_intensity
        return None

    @desk_command
    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        if self.entity_description.key == "height_limit_upper":
            validate_height_limit(self.coordinator.data, LIMIT_UPPER, value)
            await self._device.set_height_limit_upper(value)
            await self._device.get_limits()
        elif self.entity_description.key == "height_limit_lower":
            validate_height_limit(self.coordinator.data, LIMIT_LOWER, value)
            await self._device.set_height_limit_lower(value)
            await self._device.get_limits()
        elif self.entity_description.key == "vibration_intensity":
            await self._device.set_vibration_intensity(int(value))
            await self._device.get_vibration_intensity()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        # Height limit entities report whether the limits are enabled
        if self.entity_description.key in ("height_limit_upper", "height_limit_lower"):
            return {"limits_enabled": self.coordinator.data.limits_enabled}
        return None
