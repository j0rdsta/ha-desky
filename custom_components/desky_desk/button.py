"""Button platform for Desky Desk preset controls."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk button entities based on a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        [
            *(DeskyPresetButton(coordinator, preset) for preset in range(1, 5)),
            DeskyMoveUpButton(coordinator),
            DeskyMoveDownButton(coordinator),
        ]
    )


class DeskyPresetButton(DeskEntity, ButtonEntity):
    """Representation of a desk preset button."""

    _attr_translation_key = "preset"

    def __init__(self, coordinator: DeskUpdateCoordinator, preset_number: int) -> None:
        """Initialize the preset button."""
        super().__init__(coordinator, f"preset_{preset_number}")
        self._preset_number = preset_number
        self._attr_translation_placeholders = {"number": str(preset_number)}

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._device:
            _LOGGER.debug("Moving desk to preset %d", self._preset_number)
            await self._device.move_to_preset(self._preset_number)


class DeskyMoveUpButton(DeskEntity, ButtonEntity):
    """Representation of a desk move up button."""

    _attr_translation_key = "move_up"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the move up button."""
        super().__init__(coordinator, "move_up")

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._device:
            _LOGGER.debug("Moving desk up")
            await self._device.move_up()


class DeskyMoveDownButton(DeskEntity, ButtonEntity):
    """Representation of a desk move down button."""

    _attr_translation_key = "move_down"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the move down button."""
        super().__init__(coordinator, "move_down")

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._device:
            _LOGGER.debug("Moving desk down")
            await self._device.move_down()
