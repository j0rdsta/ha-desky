"""Light platform for Desky Desk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util.color import brightness_to_value, value_to_brightness

from .const import DOMAIN, OFF_COLORS
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import DeskEntity, desk_command

# Commands go to one BLE connection, so send them one at a time
PARALLEL_UPDATES = 1

# The desk takes brightness in % from 1 to 100
BRIGHTNESS_SCALE = (1, 100)


@dataclass(frozen=True)
class LedColor:
    """A colour the LED strip shows."""

    # Effect name
    name: str
    # Hue and saturation of a static colour; party mode has none
    hs: tuple[float, float] | None


COLOR_WHITE = 1

# The colours the LED shows by desk colour code, in effect list order. Every
# colour is an effect; the ones with a hue and saturation are static colours
LED_COLORS: dict[int, LedColor] = {
    COLOR_WHITE: LedColor("White", (0, 0)),
    2: LedColor("Red", (0, 100)),
    3: LedColor("Green", (120, 100)),
    4: LedColor("Blue", (240, 100)),
    5: LedColor("Yellow", (60, 100)),
    6: LedColor("Party mode", None),
}

EFFECT_TO_COLOR = {color.name: code for code, color in LED_COLORS.items()}

# A picked colour less saturated than this is White
MIN_SATURATION = 30


def _nearest_color(hs_color: tuple[float, float]) -> int:
    """Return the desk colour nearest to a hue and saturation."""
    hue, saturation = hs_color
    if saturation < MIN_SATURATION:
        return COLOR_WHITE

    def distance(color_hue: float) -> tuple[float, float]:
        # Nearest round the colour wheel; a tie goes to the colour below the hue
        offset = (hue - color_hue) % 360
        return min(offset, 360 - offset), offset

    hues = {
        code: color.hs[0]
        for code, color in LED_COLORS.items()
        if color.hs is not None and color.hs[1] == 100
    }
    return min(hues, key=lambda code: distance(hues[code]))


def _visible_color(color: int | None) -> LedColor | None:
    """Return the colour the LED shows, or None for an off or unknown code."""
    return None if color is None else LED_COLORS.get(color)


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
        # Only a static colour can be restored; party mode is an effect
        if (
            type(color) is not int
            or (led_color := LED_COLORS.get(color)) is None
            or led_color.hs is None
        ):
            return None
        return cls(last_static_color=color)


class DeskLight(DeskEntity, LightEntity, RestoreEntity):
    """Representation of a Desky desk LED strip."""

    _attr_translation_key = "desk_light"
    _attr_color_mode = ColorMode.HS
    # Colour temperature is supported only so that Home Assistant passes it on
    # instead of converting it to a hue: the desk has one white
    _attr_supported_color_modes = {ColorMode.HS, ColorMode.COLOR_TEMP}
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
        color = _visible_color(self.coordinator.data.light_color)
        return None if color is None else color.name

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation of the colour; party mode has none."""
        color = _visible_color(self.coordinator.data.light_color)
        return None if color is None else color.hs

    async def _async_set_color(self, color_code: int) -> None:
        """Set the light colour and remember it if it is a static colour."""
        await self._device.set_light_color(color_code)
        if LED_COLORS[color_code].hs is not None:
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

        # An effect wins over a colour, which snaps to the nearest desk colour
        if effect is not None:
            await self._async_set_color(EFFECT_TO_COLOR[effect])
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            await self._async_set_color(COLOR_WHITE)
        elif ATTR_HS_COLOR in kwargs:
            await self._async_set_color(_nearest_color(kwargs[ATTR_HS_COLOR]))
        elif _visible_color(self.coordinator.data.light_color) is None:
            # The LED is off or shows an unknown colour: turn on with the last
            # static colour
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
