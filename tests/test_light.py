"""Test the Desky Desk LED strip light."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
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
from custom_components.desky_desk.const import (
    BRIGHTNESS_RESPONSE_HEADER,
    DOMAIN,
    LIGHT_COLOR_RESPONSE_HEADER,
    LIGHTING_RESPONSE_HEADER,
    WRITE_CHARACTERISTIC_UUID,
)
from custom_components.desky_desk.light import DeskLight, _nearest_color

from . import deliver_frame, desk_response, set_desk_state

ENTITY_ID = "light.desky_desk_led_strip"

COLOR_OFF = 7
# The official app turns the LED off by setting colour 0
COLOR_APP_OFF = 0

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


@pytest.mark.parametrize(
    ("hs_color", "color"),
    [
        # Saturation below 30 is White, whatever the hue
        ((0, 0), 1),
        ((200, 29), 1),
        ((200, 29.9), 1),
        ((200, 30), 4),
        ((0, 100), 2),
        # A tie goes to the colour below the hue
        ((30, 100), 2),
        ((31, 100), 5),
        ((60, 100), 5),
        ((90, 100), 5),
        ((91, 100), 3),
        ((120, 100), 3),
        ((180, 100), 3),
        ((181, 100), 4),
        ((240, 100), 4),
        ((300, 100), 4),
        ((301, 100), 2),
        ((359, 100), 2),
        ((360, 100), 2),
    ],
)
def test_nearest_color(hs_color: tuple[float, float], color: int) -> None:
    """Test a hue and saturation snap to the nearest desk colour."""
    assert _nearest_color(hs_color) == color


async def test_light_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the light reports the desk's lighting state."""
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 128  # 50%
    assert state.attributes[ATTR_EFFECT] == "White"


async def test_light_effect_list(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the effects are the desk's colours except Off, in the desk's order."""
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EFFECT_LIST] == [
        "White",
        "Red",
        "Green",
        "Blue",
        "Yellow",
        "Party mode",
    ]


@pytest.mark.parametrize(("effect", "color"), EFFECTS)
async def test_light_reports_color(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    effect: str,
    color: int,
) -> None:
    """Test each colour the desk reports is shown as an effect."""
    await set_desk_state(hass, init_integration, light_color=color)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_EFFECT] == effect


@pytest.mark.parametrize(
    ("changes", "expected_state"),
    [
        ({"light_color": COLOR_OFF}, STATE_OFF),
        ({"light_color": COLOR_APP_OFF}, STATE_OFF),
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
    """Test a missing or unknown colour has no effect."""
    await set_desk_state(hass, init_integration, light_color=light_color)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_EFFECT] is None


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
    # Off is the lighting command; colour 0 is never sent
    mock_desk.set_light_color.assert_not_called()


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


@pytest.mark.parametrize("light_color", [COLOR_OFF, COLOR_APP_OFF, None])
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


@pytest.mark.parametrize("off_color", [COLOR_OFF, COLOR_APP_OFF])
async def test_light_remembers_static_color(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    off_color: int,
) -> None:
    """Test a static effect is remembered for turning on, and Party mode is not."""
    light = _light(hass)
    assert light.extra_restore_state_data.as_dict() == {"last_static_color": 1}

    await _turn_on(hass, **{ATTR_EFFECT: "Green"})
    assert light.extra_restore_state_data.as_dict() == {"last_static_color": 3}

    await _turn_on(hass, **{ATTR_EFFECT: "Party mode"})
    assert light.extra_restore_state_data.as_dict() == {"last_static_color": 3}

    # Turning the light back on from Off restores the remembered colour
    await set_desk_state(hass, init_integration, light_color=off_color)
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


async def test_light_turns_on_when_the_desk_confirms(
    hass: HomeAssistant, desk_client: MagicMock
) -> None:
    """Test the light shows on as soon as the desk confirms it, and not before."""
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await _turn_on(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    deliver_frame(desk_client, desk_response(LIGHTING_RESPONSE_HEADER, 0x01))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    deliver_frame(desk_client, desk_response(LIGHTING_RESPONSE_HEADER, 0x00))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_light_brightness_follows_the_desk_reply(
    hass: HomeAssistant, desk_client: MagicMock
) -> None:
    """Test the brightness changes only when the desk reports it."""
    deliver_frame(desk_client, desk_response(LIGHTING_RESPONSE_HEADER, 0x01))
    await hass.async_block_till_done()

    await _turn_on(hass, **{ATTR_BRIGHTNESS: 255})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS] is None

    deliver_frame(desk_client, desk_response(BRIGHTNESS_RESPONSE_HEADER, 100))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS] == 255


async def test_light_effect_follows_the_desk_reply(
    hass: HomeAssistant, desk_client: MagicMock
) -> None:
    """Test the colour changes only when the desk reports it."""
    deliver_frame(desk_client, desk_response(LIGHTING_RESPONSE_HEADER, 0x01))
    await hass.async_block_till_done()

    await _turn_on(hass, **{ATTR_EFFECT: "Red"})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[ATTR_EFFECT] is None

    deliver_frame(desk_client, desk_response(LIGHT_COLOR_RESPONSE_HEADER, 0x02))
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_EFFECT] == "Red"


async def test_light_off_by_color_turns_on_with_the_color_reply(
    hass: HomeAssistant, desk_client: MagicMock
) -> None:
    """Test a light whose colour is Off shows on only once the colour is back."""
    deliver_frame(desk_client, desk_response(LIGHT_COLOR_RESPONSE_HEADER, COLOR_OFF))
    deliver_frame(desk_client, desk_response(LIGHTING_RESPONSE_HEADER, 0x01))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await _turn_on(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    deliver_frame(desk_client, desk_response(LIGHT_COLOR_RESPONSE_HEADER, 0x01))
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_EFFECT] == "White"


async def test_light_colour_0_with_lighting_enabled(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test colour 0 shows off with no effect, and turning on sets a visible colour."""
    await set_desk_state(hass, init_integration, light_color=COLOR_APP_OFF)

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes.get(ATTR_EFFECT) is None

    await _turn_on(hass)

    mock_desk.set_light_color.assert_awaited_once_with(1)
    # Lighting is already enabled, so the colour alone turns the LEDs on
    mock_desk.set_lighting.assert_not_called()


async def test_light_turn_on_effect_from_colour_0(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test an effect chosen while the colour is 0 is the only colour sent."""
    await set_desk_state(hass, init_integration, light_color=COLOR_APP_OFF)

    await _turn_on(hass, **{ATTR_EFFECT: "Blue"})

    mock_desk.set_light_color.assert_awaited_once_with(4)


async def test_light_off_by_colour_0_turns_on_white(
    hass: HomeAssistant, desk_client: MagicMock
) -> None:
    """Test a desk reporting colour 0 is off, and turning on sends White."""
    deliver_frame(
        desk_client, desk_response(LIGHT_COLOR_RESPONSE_HEADER, COLOR_APP_OFF)
    )
    deliver_frame(desk_client, desk_response(LIGHTING_RESPONSE_HEADER, 0x01))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    desk_client.write_gatt_char.reset_mock()

    await _turn_on(hass)

    # Handshake, then set colour 1 (White): checksum 0xB4 + 0x01 + 0x01 = 0xB6
    assert call(WRITE_CHARACTERISTIC_UUID, bytes.fromhex("f1f1b40101b67e")) in (
        desk_client.write_gatt_char.call_args_list
    )
