"""Test the Desky Desk LED strip light."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_EFFECT,
    DOMAIN as LIGHT_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import async_get_platforms
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.desky_desk.bluetooth import DeskCommandError
from custom_components.desky_desk.const import DOMAIN
from custom_components.desky_desk.light import DeskLight

from . import set_desk_state

ENTITY_ID = "light.desky_desk_led_strip"

COLOR_OFF = 7

# Effect name and the colour code the desk uses for it
EFFECTS = [
    ("White", 1),
    ("Red", 2),
    ("Green", 3),
    ("Blue", 4),
    ("Yellow", 5),
    ("Party mode", 6),
]


def _light(hass: HomeAssistant) -> DeskLight:
    """Return the LED strip entity object."""
    platform = next(
        platform
        for platform in async_get_platforms(hass, DOMAIN)
        if platform.domain == LIGHT_DOMAIN
    )
    return platform.entities[ENTITY_ID]


async def _setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration, for tests that seed state before setup."""
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address="AA:BB:CC:DD:EE:FF"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def _turn_on(hass: HomeAssistant, **data: Any) -> None:
    """Call light.turn_on on the LED strip."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )


async def test_light_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the light reports the desk's lighting state."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 128  # 50%
    assert state.attributes[ATTR_EFFECT] == "White"
    assert state.attributes["color_name"] == "White"


@pytest.mark.parametrize(("effect", "color"), EFFECTS)
async def test_light_reports_color(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    effect: str,
    color: int,
) -> None:
    """Test each colour the desk reports is shown as an effect and colour name."""
    await set_desk_state(hass, init_integration, light_color=color)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_EFFECT] == effect
    assert state.attributes["color_name"] == effect


@pytest.mark.parametrize(
    ("changes", "expected_state"),
    [
        ({"light_color": COLOR_OFF}, STATE_OFF),
        ({"lighting_enabled": False}, STATE_OFF),
        ({"lighting_enabled": None}, STATE_OFF),
        ({"light_color": None}, STATE_ON),
    ],
)
async def test_light_on_off_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    changes: dict[str, Any],
    expected_state: str,
) -> None:
    """Test the light is off when lighting is disabled or the colour is Off."""
    await set_desk_state(hass, init_integration, **changes)

    assert hass.states.get(ENTITY_ID).state == expected_state


@pytest.mark.parametrize("light_color", [None, 99])
async def test_light_unknown_color(
    hass: HomeAssistant, init_integration: MockConfigEntry, light_color: int | None
) -> None:
    """Test a missing or unknown colour has no effect and no colour name."""
    await set_desk_state(hass, init_integration, light_color=light_color)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_EFFECT] is None
    assert "color_name" not in state.attributes


async def test_light_brightness_unknown(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the light has no brightness when the desk has not reported one."""
    await set_desk_state(hass, init_integration, brightness=None)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] is None


async def test_light_unavailable_when_disconnected(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the light becomes unavailable when the desk disconnects."""
    await set_desk_state(hass, init_integration, is_connected=False)

    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


async def test_light_turn_off(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test turning the light off disables lighting and requests its status."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )

    mock_desk.set_lighting.assert_awaited_once_with(False)
    mock_desk.get_lighting_status.assert_awaited_once()


async def test_light_turn_on_keeps_current_color(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test turning on a lit light only refreshes its state."""
    await _turn_on(hass)

    mock_desk.set_light_color.assert_not_called()
    mock_desk.set_lighting.assert_not_called()
    mock_desk.set_brightness.assert_not_called()
    mock_desk.get_lighting_status.assert_awaited_once()
    mock_desk.get_light_color.assert_awaited_once()
    mock_desk.get_brightness.assert_awaited_once()


async def test_light_turn_on_enables_lighting(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test turning on a light with lighting disabled enables it."""
    await set_desk_state(hass, init_integration, lighting_enabled=False)

    await _turn_on(hass)

    mock_desk.set_lighting.assert_awaited_once_with(True)
    mock_desk.set_light_color.assert_not_called()


@pytest.mark.parametrize(
    ("brightness", "percent"), [(1, 1), (2, 1), (128, 50), (191, 75), (255, 100)]
)
async def test_light_turn_on_brightness(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    brightness: int,
    percent: int,
) -> None:
    """Test brightness is sent as the nearest percentage, and never as 0 %."""
    await _turn_on(hass, **{ATTR_BRIGHTNESS: brightness})

    mock_desk.set_brightness.assert_awaited_once_with(percent)
    mock_desk.get_brightness.assert_awaited_once()


async def test_light_brightness_percent_round_trip(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test every percentage set in Home Assistant reaches the desk unchanged."""
    for percent in range(1, 101):
        mock_desk.set_brightness.reset_mock()

        await _turn_on(hass, **{ATTR_BRIGHTNESS_PCT: percent})

        mock_desk.set_brightness.assert_awaited_once_with(percent)
        # The desk reports it back, and Home Assistant shows the same percentage
        await set_desk_state(hass, init_integration, brightness=percent)
        brightness = hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS]
        assert round(brightness / 255 * 100) == percent


@pytest.mark.parametrize(
    ("percent", "brightness"), [(0, 1), (1, 3), (50, 128), (75, 191), (100, 255)]
)
async def test_light_reports_brightness(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    percent: int,
    brightness: int,
) -> None:
    """Test the desk's percentage is shown as a Home Assistant brightness."""
    await set_desk_state(hass, init_integration, brightness=percent)

    assert hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS] == brightness


@pytest.mark.parametrize(("effect", "color"), EFFECTS)
async def test_light_turn_on_effect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    effect: str,
    color: int,
) -> None:
    """Test each effect sends its colour code to the desk."""
    await _turn_on(hass, **{ATTR_EFFECT: effect})

    mock_desk.set_light_color.assert_awaited_once_with(color)
    mock_desk.get_light_color.assert_awaited_once()


async def test_light_turn_on_unknown_effect_rejected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test an effect the desk does not have fails and sends nothing."""
    mock_desk.reset_mock()

    with pytest.raises(ServiceValidationError) as err:
        await _turn_on(hass, **{ATTR_EFFECT: "Purple", ATTR_BRIGHTNESS: 200})

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "unknown_effect"
    assert err.value.translation_placeholders == {
        "effect": "Purple",
        "effects": "White, Red, Green, Blue, Yellow, Party mode",
    }
    assert str(err.value) == (
        "The LED strip has no effect called Purple. Use one of: "
        "White, Red, Green, Blue, Yellow, Party mode"
    )
    assert mock_desk.method_calls == []
    assert _light(hass).extra_restore_state_data.as_dict() == {"last_static_color": 1}


@pytest.mark.parametrize("light_color", [COLOR_OFF, None])
async def test_light_turn_on_defaults_to_white(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    light_color: int | None,
) -> None:
    """Test turning on an off or unknown colour light uses White by default."""
    await set_desk_state(
        hass, init_integration, light_color=light_color, lighting_enabled=False
    )

    await _turn_on(hass)

    mock_desk.set_light_color.assert_awaited_once_with(1)
    mock_desk.set_lighting.assert_awaited_once_with(True)
    mock_desk.get_lighting_status.assert_awaited_once()
    mock_desk.get_light_color.assert_awaited_once()
    mock_desk.get_brightness.assert_awaited_once()


async def test_light_remembers_static_color(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a static effect is remembered for turning on, and Party mode is not."""
    light = _light(hass)
    assert light.extra_restore_state_data.as_dict() == {"last_static_color": 1}

    await _turn_on(hass, **{ATTR_EFFECT: "Green"})
    assert light.extra_restore_state_data.as_dict() == {"last_static_color": 3}

    await _turn_on(hass, **{ATTR_EFFECT: "Party mode"})
    assert light.extra_restore_state_data.as_dict() == {"last_static_color": 3}

    # Turning the light back on from Off restores the remembered colour
    await set_desk_state(hass, init_integration, light_color=COLOR_OFF)
    mock_desk.set_light_color.reset_mock()
    await _turn_on(hass)
    mock_desk.set_light_color.assert_awaited_once_with(3)


async def test_light_commands_skipped_when_unavailable(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test Home Assistant sends nothing to the light while the desk is disconnected."""
    await set_desk_state(hass, init_integration, is_connected=False)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_EFFECT: "Red"},
        blocking=True,
    )

    mock_desk.set_light_color.assert_not_called()
    mock_desk.set_lighting.assert_not_called()


async def test_failed_color_change_is_not_remembered(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a colour the desk never received is not restored on the next turn on."""
    mock_desk.set_light_color.side_effect = DeskCommandError("write failed")

    with pytest.raises(HomeAssistantError):
        await _turn_on(hass, **{ATTR_EFFECT: "Red"})

    assert _light(hass).extra_restore_state_data.as_dict() == {"last_static_color": 1}


async def test_light_restores_last_static_color(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the last static colour is restored after a restart."""
    mock_restore_cache_with_extra_data(
        hass, [(State(ENTITY_ID, STATE_OFF), {"last_static_color": 3})]
    )
    mock_desk.light_color = COLOR_OFF
    await _setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await _turn_on(hass)

    mock_desk.set_light_color.assert_awaited_once_with(3)
    assert _light(hass).extra_restore_state_data.as_dict() == {"last_static_color": 3}


@pytest.mark.parametrize("stored_color", [6, 7, 99, "3", None, True])
async def test_light_ignores_invalid_restored_color(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
    stored_color: Any,
) -> None:
    """Test restored data that is not a static colour falls back to White."""
    mock_restore_cache_with_extra_data(
        hass, [(State(ENTITY_ID, STATE_OFF), {"last_static_color": stored_color})]
    )
    mock_desk.light_color = COLOR_OFF
    await _setup_integration(hass, mock_config_entry)

    await _turn_on(hass)

    mock_desk.set_light_color.assert_awaited_once_with(1)


async def test_light_keeps_static_color_across_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the remembered colour survives the entity being removed and re-added."""
    await _turn_on(hass, **{ATTR_EFFECT: "Yellow"})

    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    await set_desk_state(hass, init_integration, light_color=COLOR_OFF)
    mock_desk.set_light_color.reset_mock()

    await _turn_on(hass)

    mock_desk.set_light_color.assert_awaited_once_with(5)
