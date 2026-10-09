"""Select platform for Desky Desk."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bluetooth import DeskBLEDevice
from .const import DISPLAY_UNITS, SENSITIVITY_LEVELS, TOUCH_MODES
from .coordinator import DeskData, DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command

_LOGGER = logging.getLogger(__name__)

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1

# Protocol values by state key
SENSITIVITY_BY_OPTION = {option: level for level, option in SENSITIVITY_LEVELS.items()}
TOUCH_MODE_BY_OPTION = {option: mode for mode, option in TOUCH_MODES.items()}


@dataclass(frozen=True, kw_only=True)
class DeskSelectEntityDescription(SelectEntityDescription):
    """A desk select, how to read its option and how to set it on the desk."""

    current_fn: Callable[[DeskData], str | None]
    select_fn: Callable[[DeskBLEDevice, str], Awaitable[None]]


async def _set_sensitivity(device: DeskBLEDevice, option: str) -> None:
    """Set the collision sensitivity and read it back."""
    await device.set_sensitivity(SENSITIVITY_BY_OPTION[option])
    await device.get_sensitivity()


async def _set_touch_mode(device: DeskBLEDevice, option: str) -> None:
    """Set the touch mode; the desk does not confirm it, so read its settings back."""
    await device.set_touch_mode(TOUCH_MODE_BY_OPTION[option])
    await device.get_settings()


async def _set_unit(device: DeskBLEDevice, option: str) -> None:
    """Set the display unit; the desk does not confirm it, so read its settings back."""
    await device.set_unit(option)
    await device.get_settings()


SELECT_DESCRIPTIONS = [
    DeskSelectEntityDescription(
        key="sensitivity",
        translation_key="sensitivity",
        options=list(SENSITIVITY_LEVELS.values()),
        entity_category=EntityCategory.CONFIG,
        current_fn=lambda data: (
            None
            if data.sensitivity_level is None
            else SENSITIVITY_LEVELS.get(data.sensitivity_level)
        ),
        select_fn=_set_sensitivity,
    ),
    DeskSelectEntityDescription(
        key="touch_mode",
        translation_key="touch_mode",
        options=list(TOUCH_MODES.values()),
        entity_category=EntityCategory.CONFIG,
        current_fn=lambda data: (
            None if data.touch_mode is None else TOUCH_MODES.get(data.touch_mode)
        ),
        select_fn=_set_touch_mode,
    ),
    DeskSelectEntityDescription(
        key="unit",
        translation_key="unit",
        options=list(DISPLAY_UNITS.values()),
        entity_category=EntityCategory.CONFIG,
        current_fn=lambda data: data.unit_preference,
        select_fn=_set_unit,
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

    entity_description: DeskSelectEntityDescription

    def __init__(
        self,
        coordinator: DeskUpdateCoordinator,
        description: DeskSelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self.entity_description.current_fn(self.coordinator.data)

    @desk_command
    async def async_select_option(self, option: str) -> None:
        """Select an option; Home Assistant only passes one of the options."""
        await self.entity_description.select_fn(self._device, option)
