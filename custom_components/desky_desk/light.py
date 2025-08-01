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

# Effects list
EFFECT_PARTY = "Party mode"
EFFECT_WHITE = "White"
EFFECT_RED = "Red"
EFFECT_GREEN = "Green"
EFFECT_BLUE = "Blue"
EFFECT_YELLOW = "Yellow"

# Map effect names to color codes
EFFECT_TO_COLOR = {
    EFFECT_WHITE: 1,
    EFFECT_RED: 2,
    EFFECT_GREEN: 3,
    EFFECT_BLUE: 4,
    EFFECT_YELLOW: 5,
    EFFECT_PARTY: 6,
}

# Map color codes to effect names
COLOR_TO_EFFECT = {v: k for k, v in EFFECT_TO_COLOR.items()}


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
        self._attr_effect_list = [
            EFFECT_WHITE,
            EFFECT_RED,
            EFFECT_GREEN,
            EFFECT_BLUE,
            EFFECT_YELLOW,
            EFFECT_PARTY,
        ]

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
        if light_color in COLOR_TO_EFFECT:
            return COLOR_TO_EFFECT[light_color]
        
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
        
        # Handle effect (color selection)
        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            if effect_name in EFFECT_TO_COLOR:
                color_code = EFFECT_TO_COLOR[effect_name]
                await self._device.set_light_color(color_code)
                
                # Store last static color (non-party mode) for persistence
                if color_code != 6:  # Not party mode
                    self.coordinator.data["last_static_color"] = color_code
        else:
            # If no specific effect requested and light is off, turn on with previous color or white
            current_color = self.coordinator.data.get("light_color")
            if current_color is None or current_color == 7:  # Off or unknown
                # Check if there's a stored last color from previous sessions
                last_color = self.coordinator.data.get("last_static_color", 1)  # Default to White
                await self._device.set_light_color(last_color)
        
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

        if effect in EFFECT_TO_COLOR:
            color_code = EFFECT_TO_COLOR[effect]
            await self._device.set_light_color(color_code)
            
            # Store last static color (non-party mode) for persistence
            if color_code != 6:  # Not party mode
                self.coordinator.data["last_static_color"] = color_code
            
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