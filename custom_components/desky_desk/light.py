"""Light platform for Desky Desk."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LIGHT_COLORS
from .entity import DeskEntity

_LOGGER = logging.getLogger(__name__)

# Map color names to simple colors for Home Assistant
COLOR_MAP = {
    1: "white",      # White
    2: "red",        # Red
    3: "green",      # Green
    4: "blue",       # Blue
    5: "yellow",     # Yellow
    6: None,         # Party mode (effect)
    7: None,         # Off
}

EFFECT_PARTY = "Party mode"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky light platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([DeskLight(coordinator, config_entry)])


class DeskLight(DeskEntity, LightEntity):
    """Representation of a Desky desk LED strip."""

    _attr_translation_key = "desk_light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator, config_entry):
        """Initialize the light."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.unique_id}_led_strip"
        self._attr_name = "LED Strip"
        self._attr_effect_list = [EFFECT_PARTY]

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        if not self.available:
            return False
        
        # Light is on if lighting is enabled and color is not "Off" (7)
        lighting_enabled = self.coordinator.data.get("lighting_enabled", False)
        light_color = self.coordinator.data.get("light_color")
        
        return lighting_enabled and light_color != 7

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        if not self.available:
            return None
        
        brightness_percent = self.coordinator.data.get("brightness")
        if brightness_percent is None:
            return None
        
        # Convert percentage (0-100) to Home Assistant brightness (0-255)
        return int((brightness_percent / 100) * 255)

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        if not self.available:
            return None
        
        light_color = self.coordinator.data.get("light_color")
        if light_color == 6:  # Party mode
            return EFFECT_PARTY
        
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        if not self.available or not self._device:
            return

        # Handle brightness change
        if ATTR_BRIGHTNESS in kwargs:
            # Convert Home Assistant brightness (0-255) to percentage (0-100)
            brightness_percent = int((kwargs[ATTR_BRIGHTNESS] / 255) * 100)
            await self._device.set_brightness(brightness_percent)
        
        # Handle effect
        if ATTR_EFFECT in kwargs:
            if kwargs[ATTR_EFFECT] == EFFECT_PARTY:
                await self._device.set_light_color(6)  # Party mode
        else:
            # If no specific effect requested and light is off, turn on with white
            current_color = self.coordinator.data.get("light_color")
            if current_color is None or current_color == 7:  # Off or unknown
                await self._device.set_light_color(1)  # White
        
        # Enable lighting if not already enabled
        if not self.coordinator.data.get("lighting_enabled", False):
            await self._device.set_lighting(True)
        
        # Request status update to get the new state
        await self._device.get_lighting_status()
        await self._device.get_light_color()
        await self._device.get_brightness()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        if not self.available or not self._device:
            return

        # Disable lighting
        await self._device.set_lighting(False)
        
        # Request status update
        await self._device.get_lighting_status()

    async def async_set_effect(self, effect: str) -> None:
        """Set the effect."""
        if not self.available or not self._device:
            return

        if effect == EFFECT_PARTY:
            await self._device.set_light_color(6)  # Party mode
            await self._device.get_light_color()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        
        # Add current color name if available
        light_color = self.coordinator.data.get("light_color")
        if light_color and light_color in LIGHT_COLORS:
            attrs["color_name"] = LIGHT_COLORS[light_color]
        
        return attrs