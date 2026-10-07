"""Select platform for Desky Desk."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SENSITIVITY_LEVELS, TOUCH_MODES
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1

SELECT_DESCRIPTIONS = [
    SelectEntityDescription(
        key="sensitivity",
        translation_key="sensitivity",
        options=["High", "Medium", "Low"],
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="touch_mode",
        translation_key="touch_mode",
        options=["One press", "Press and hold"],
        entity_category=EntityCategory.CONFIG,
    ),
    SelectEntityDescription(
        key="unit",
        translation_key="unit",
        options=["cm", "in"],
        entity_category=EntityCategory.CONFIG,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky select platform."""
    async_add_entities(
        DeskSelect(entry.runtime_data, description)
        for description in SELECT_DESCRIPTIONS
    )


class DeskSelect(DeskEntity, SelectEntity):
    """Representation of a Desky desk select entity."""

    def __init__(
        self, coordinator: DeskUpdateCoordinator, description: SelectEntityDescription
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        data = self.coordinator.data

        if self.entity_description.key == "sensitivity":
            level = data.sensitivity_level
            if level and level in SENSITIVITY_LEVELS:
                return SENSITIVITY_LEVELS[level]
        elif self.entity_description.key == "touch_mode":
            mode = data.touch_mode
            if mode is not None and mode in TOUCH_MODES:
                return TOUCH_MODES[mode]
        elif self.entity_description.key == "unit":
            return data.unit_preference

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

            # The desk does not confirm a change, so read its settings back
            if mode is not None and await self._device.set_touch_mode(mode):
                await self._device.get_settings()

        elif self.entity_description.key == "unit":
            if option in ["cm", "in"] and await self._device.set_unit(option):
                await self._device.get_settings()
