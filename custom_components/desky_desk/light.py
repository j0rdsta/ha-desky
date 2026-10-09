"""Light platform for Desky Desk."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Self

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .const import DOMAIN, LIGHT_COLORS, OFF_COLORS
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command

_LOGGER = logging.getLogger(__name__)

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1

# The desk takes brightness in % from 1 to 100
BRIGHTNESS_SCALE = (1, 100)

COLOR_WHITE = 1
COLOR_PARTY = 6

# Map effect names to colour codes; every colour except Off is an effect
EFFECT_TO_COLOR = {
    name: code for code, name in LIGHT_COLORS.items() if code not in OFF_COLORS
}

# Map color codes to effect names
COLOR_TO_EFFECT = {v: k for k, v in EFFECT_TO_COLOR.items()}

# Colours that can be restored when the light turns on; party mode is an effect
STATIC_COLORS = frozenset(EFFECT_TO_COLOR.values()) - {COLOR_PARTY}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DeskyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Desky light platform."""
    async_add_entities([DeskLight(entry.runtime_data)])


@dataclass
class DeskLightExtraStoredData(ExtraStoredData):
    """Light state kept across restarts that the desk does not report."""

    last_static_color: int

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the stored data."""
        return {"last_static_color": self.last_static_color}

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Initialize the stored data from a dict, or None if it is invalid."""
        color = restored.get("last_static_color")
        if type(color) is not int or color not in STATIC_COLORS:
            return None
        return cls(last_static_color=color)


class DeskLight(DeskEntity, LightEntity, RestoreEntity):
    """Representation of a Desky desk LED strip."""

    _attr_translation_key = "desk_light"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(EFFECT_TO_COLOR)

    def __init__(self, coordinator: DeskUpdateCoordinator) -> None:
        """Initialize the light."""
        super().__init__(coordinator, "led_strip")
        # Static colour to restore when turning on from off; party mode is not static
        self._last_static_color = COLOR_WHITE

    async def async_added_to_hass(self) -> None:
        """Restore the last static colour when the entity is added."""
        await super().async_added_to_hass()
        if (last_extra_data := await self.async_get_last_extra_data()) and (
            stored := DeskLightExtraStoredData.from_dict(last_extra_data.as_dict())
        ):
            self._last_static_color = stored.last_static_color

    @property
    def extra_restore_state_data(self) -> DeskLightExtraStoredData:
        """Return the light state to keep across restarts."""
        return DeskLightExtraStoredData(self._last_static_color)

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        # The light is on if lighting is enabled and the colour is not an off colour
        data = self.coordinator.data
        return bool(data.lighting_enabled) and data.light_color not in OFF_COLORS

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        brightness_percent = self.coordinator.data.brightness
        if brightness_percent is None:
            return None

        return value_to_brightness(BRIGHTNESS_SCALE, brightness_percent)

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        light_color = self.coordinator.data.light_color
        return None if light_color is None else COLOR_TO_EFFECT.get(light_color)

    async def _async_set_color(self, color_code: int) -> None:
        """Set the light colour and remember it if it is a static colour."""
        await self._device.set_light_color(color_code)
        if color_code != COLOR_PARTY:
            self._last_static_color = color_code

    @desk_command
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        effect = kwargs.get(ATTR_EFFECT)
        # Home Assistant does not check the effect against the effect list
        if effect is not None and effect not in EFFECT_TO_COLOR:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_effect",
                translation_placeholders={
                    "effect": effect,
                    "effects": ", ".join(EFFECT_TO_COLOR),
                },
            )

        if ATTR_BRIGHTNESS in kwargs:
            # Round to the nearest %, but never send a light that is on as 0 %
            brightness_percent = max(
                1, round(brightness_to_value(BRIGHTNESS_SCALE, kwargs[ATTR_BRIGHTNESS]))
            )
            await self._device.set_brightness(brightness_percent)

        if effect is not None:
            await self._async_set_color(EFFECT_TO_COLOR[effect])
        else:
            # If no specific effect requested and light is off, turn on with the
            # last static colour
            current_color = self.coordinator.data.light_color
            if current_color is None or current_color in OFF_COLORS:
                await self._device.set_light_color(self._last_static_color)

        # Enable lighting if not already enabled
        if not self.coordinator.data.lighting_enabled:
            await self._device.set_lighting(True)

        # Request status update to get the new state
        await self._device.get_lighting_status()
        await self._device.get_light_color()
        await self._device.get_brightness()

    @desk_command
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        # Disable lighting
        await self._device.set_lighting(False)

        # Request status update
        await self._device.get_lighting_status()
