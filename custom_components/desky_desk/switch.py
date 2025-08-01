"""Switch platform for Desky Desk."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

SWITCH_DESCRIPTIONS = [
    SwitchEntityDescription(
        key="vibration",
        translation_key="vibration",
        name="Vibration",
        icon="mdi:vibrate",
    ),
    SwitchEntityDescription(
        key="lock",
        translation_key="lock",
        name="Lock",
        icon="mdi:lock",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky switch platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for description in SWITCH_DESCRIPTIONS:
        entities.append(DeskSwitch(coordinator, config_entry, description))
    
    async_add_entities(entities)


class DeskSwitch(DeskEntity, SwitchEntity):
    """Representation of a Desky desk switch."""

    def __init__(self, coordinator, config_entry, description: SwitchEntityDescription):
        """Initialize the switch."""
        super().__init__(coordinator, config_entry)
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.unique_id}_{description.key}"
        self._attr_name = description.name

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        if not self.available:
            return False
        
        if self.entity_description.key == "vibration":
            return self.coordinator.data.get("vibration_enabled", False)
        elif self.entity_description.key == "lock":
            return self.coordinator.data.get("lock_status", False)
        
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if not self.available or not self._device:
            return

        if self.entity_description.key == "vibration":
            await self._device.set_vibration(True)
            await self._device.get_vibration_status()
        elif self.entity_description.key == "lock":
            await self._device.set_lock_status(True)
            await self._device.get_lock_status()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if not self.available or not self._device:
            return

        if self.entity_description.key == "vibration":
            await self._device.set_vibration(False)
            await self._device.get_vibration_status()
        elif self.entity_description.key == "lock":
            await self._device.set_lock_status(False)
            await self._device.get_lock_status()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        
        # Add vibration intensity for vibration switch
        if self.entity_description.key == "vibration":
            intensity = self.coordinator.data.get("vibration_intensity")
            if intensity is not None:
                attrs["intensity"] = intensity
        
        return attrs