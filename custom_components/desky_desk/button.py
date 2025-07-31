"""Button platform for Desky Desk preset controls."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeskUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky Desk button entities based on a config entry."""
    coordinator: DeskUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    buttons = [
        DeskyPresetButton(coordinator, 1),
        DeskyPresetButton(coordinator, 2),
        DeskyPresetButton(coordinator, 3),
        DeskyPresetButton(coordinator, 4),
        DeskyMoveUpButton(coordinator),
        DeskyMoveDownButton(coordinator),
    ]
    
    async_add_entities(buttons)


class DeskyPresetButton(CoordinatorEntity[DeskUpdateCoordinator], ButtonEntity):
    """Representation of a desk preset button."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DeskUpdateCoordinator, preset_number: int) -> None:
        """Initialize the preset button."""
        super().__init__(coordinator)
        self._preset_number = preset_number
        self._attr_name = f"Preset {preset_number}"
        self._attr_unique_id = f"{coordinator.entry.unique_id}_preset_{preset_number}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.unique_id)},
            "name": coordinator.device.name if coordinator.device else "Desky Desk",
            "manufacturer": "Desky",
            "model": "Standing Desk",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data.get("is_connected", False) if self.coordinator.data else False

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.coordinator.device:
            _LOGGER.debug("Moving desk to preset %d", self._preset_number)
            await self.coordinator.device.move_to_preset(self._preset_number)


class DeskyMoveUpButton(CoordinatorEntity[DeskUpdateCoordinator], ButtonEntity):
    """Representation of a desk move up button."""

    _attr_has_entity_name = True
    _attr_name = "Move Up"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the move up button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_move_up"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.unique_id)},
            "name": coordinator.device.name if coordinator.device else "Desky Desk",
            "manufacturer": "Desky",
            "model": "Standing Desk",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data.get("is_connected", False) if self.coordinator.data else False

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.coordinator.device:
            _LOGGER.debug("Moving desk up")
            await self.coordinator.device.move_up()


class DeskyMoveDownButton(CoordinatorEntity[DeskUpdateCoordinator], ButtonEntity):
    """Representation of a desk move down button."""

    _attr_has_entity_name = True
    _attr_name = "Move Down"

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the move down button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_move_down"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.unique_id)},
            "name": coordinator.device.name if coordinator.device else "Desky Desk",
            "manufacturer": "Desky",
            "model": "Standing Desk",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data.get("is_connected", False) if self.coordinator.data else False

    async def async_press(self) -> None:
        """Handle the button press."""
        if self.coordinator.device:
            _LOGGER.debug("Moving desk down")
            await self.coordinator.device.move_down()