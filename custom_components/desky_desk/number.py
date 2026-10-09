"""Number platform for Desky Desk height sensor."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_HEIGHT, MIN_HEIGHT, HeightLimit
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command
from .validation import checked_height_limit, validate_move_to_height

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1


HEIGHT_LIMIT_DESCRIPTIONS = {
    HeightLimit.UPPER: NumberEntityDescription(
        key="height_limit_upper",
        translation_key="height_limit_upper",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        native_step=1.0,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    HeightLimit.LOWER: NumberEntityDescription(
        key="height_limit_lower",
        translation_key="height_limit_lower",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        native_step=1.0,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
}


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
            *(DeskHeightLimitNumber(coordinator, limit) for limit in HeightLimit),
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
        validate_move_to_height(self.coordinator.data, value)
        await self._device.move_to_height(value)

        # Request coordinator update to track movement
        await self.coordinator.async_request_refresh()


class DeskHeightLimitNumber(DeskEntity, NumberEntity):
    """The desk's upper or lower height limit."""

    def __init__(self, coordinator: DeskUpdateCoordinator, limit: HeightLimit) -> None:
        """Initialize the height limit entity."""
        description = HEIGHT_LIMIT_DESCRIPTIONS[limit]
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._limit = limit

    @property
    def native_min_value(self) -> float:
        """Return the lowest limit the desk accepts in its display unit, in cm."""
        return self.coordinator.data.limit_range[0]

    @property
    def native_max_value(self) -> float:
        """Return the highest limit the desk accepts in its display unit, in cm."""
        return self.coordinator.data.limit_range[1]

    @property
    def native_value(self) -> float | None:
        """Return the limit in cm, or None if it is not set."""
        data = self.coordinator.data
        if self._limit == HeightLimit.UPPER:
            return data.height_limit_upper
        return data.height_limit_lower

    @desk_command
    async def async_set_native_value(self, value: float) -> None:
        """Set the limit; the desk code then asks for the limits the desk reports."""
        value = checked_height_limit(
            self.coordinator.data, self._device, self._limit, value
        )
        await self._device.set_height_limit(self._limit, value)
