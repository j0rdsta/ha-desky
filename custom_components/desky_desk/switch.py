"""Switch platform for Desky Desk."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1

SWITCH_DESCRIPTIONS = [
    SwitchEntityDescription(
        key="vibration",
        translation_key="vibration",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchEntityDescription(
        key="lock",
        translation_key="lock",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky switch platform."""
    async_add_entities(
        DeskSwitch(entry.runtime_data, description)
        for description in SWITCH_DESCRIPTIONS
    )


class DeskSwitch(DeskEntity, SwitchEntity):
    """Representation of a Desky desk switch."""

    def __init__(
        self, coordinator: DeskUpdateCoordinator, description: SwitchEntityDescription
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if self.entity_description.key == "vibration":
            return bool(self.coordinator.data.vibration_enabled)
        if self.entity_description.key == "lock":
            return self.coordinator.data.lock_status

        return False

    @desk_command
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self.entity_description.key == "vibration":
            await self._device.set_vibration(True)
            await self._device.get_vibration_status()
        elif self.entity_description.key == "lock":
            await self._device.set_lock_status(True)
            await self._device.get_lock_status()

    @desk_command
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self.entity_description.key == "vibration":
            await self._device.set_vibration(False)
            await self._device.get_vibration_status()
        elif self.entity_description.key == "lock":
            await self._device.set_lock_status(False)
            await self._device.get_lock_status()
