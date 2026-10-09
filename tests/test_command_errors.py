"""Test entity commands fail with a translated error when the desk misses them."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.const import DOMAIN
from custom_components.desky_desk.errors import (
    DeskCommandError,
    DeskNotConnectedError,
    DeskSettingNotAppliedError,
)

# (domain, service, entity ID, service data, desk method the command calls)
COMMANDS = [
    (BUTTON_DOMAIN, SERVICE_PRESS, "button.desky_desk_preset_1", {}, "move_to_preset"),
    (BUTTON_DOMAIN, SERVICE_PRESS, "button.desky_desk_move_up", {}, "move_up"),
    (BUTTON_DOMAIN, SERVICE_PRESS, "button.desky_desk_move_down", {}, "move_down"),
    (COVER_DOMAIN, SERVICE_OPEN_COVER, "cover.desky_desk", {}, "move_up"),
    (COVER_DOMAIN, SERVICE_CLOSE_COVER, "cover.desky_desk", {}, "move_down"),
    (COVER_DOMAIN, SERVICE_STOP_COVER, "cover.desky_desk", {}, "stop"),
    (
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        "cover.desky_desk",
        {ATTR_POSITION: 50},
        "move_to_height",
    ),
    (
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        "number.desky_desk_height",
        {ATTR_VALUE: 100.0},
        "move_to_height",
    ),
    (
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        "number.desky_desk_upper_height_limit",
        {ATTR_VALUE: 110.0},
        "set_height_limit",
    ),
    (
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        "number.desky_desk_lower_height_limit",
        {ATTR_VALUE: 70.0},
        "set_height_limit",
    ),
    (
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        "light.desky_desk_led_strip",
        {ATTR_EFFECT: "Red"},
        "set_light_color",
    ),
    (
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        "light.desky_desk_led_strip",
        {ATTR_BRIGHTNESS: 128},
        "set_brightness",
    ),
    (
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        "light.desky_desk_led_strip",
        {},
        "set_lighting",
    ),
    (
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        "switch.desky_desk_vibration",
        {},
        "set_vibration",
    ),
    (SWITCH_DOMAIN, SERVICE_TURN_ON, "switch.desky_desk_lock", {}, "set_lock_status"),
    (
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        "select.desky_desk_collision_sensitivity",
        {ATTR_OPTION: "low"},
        "set_sensitivity",
    ),
    (
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        "select.desky_desk_touch_mode",
        {ATTR_OPTION: "press_and_hold"},
        "set_touch_mode",
    ),
    (
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        "select.desky_desk_display_unit",
        {ATTR_OPTION: "in"},
        "set_unit",
    ),
]
COMMAND_IDS = [f"{entity_id}-{method}" for _, _, entity_id, _, method in COMMANDS]


async def _call(
    hass: HomeAssistant, domain: str, service: str, entity_id: str, data: dict[str, Any]
) -> None:
    """Call an entity service and wait for it to finish."""
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "method"), COMMANDS, ids=COMMAND_IDS
)
async def test_command_while_the_connection_is_gone(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    domain: str,
    service: str,
    entity_id: str,
    data: dict[str, Any],
    method: str,
) -> None:
    """Test a command fails as not connected when the link dropped unnoticed.

    Home Assistant skips entities it already shows as unavailable, so this is
    the window between the connection dropping and the entity hearing of it.
    """
    getattr(mock_desk, method).side_effect = DeskNotConnectedError("gone")

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, domain, service, entity_id, data)

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "not_connected"
    assert str(err.value) == "The desk is not connected"


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "method"), COMMANDS, ids=COMMAND_IDS
)
async def test_command_write_failure(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    domain: str,
    service: str,
    entity_id: str,
    data: dict[str, Any],
    method: str,
) -> None:
    """Test a command whose write fails raises a translated error."""
    getattr(mock_desk, method).side_effect = DeskCommandError("write failed")
    before = hass.states.get(entity_id)

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, domain, service, entity_id, data)

    assert err.value.translation_key == "command_failed"
    assert str(err.value) == "Could not send the command to the desk: write failed"
    # A pressed button records the press itself; everything else is unchanged
    if domain != BUTTON_DOMAIN:
        after = hass.states.get(entity_id)
        assert (after.state, after.attributes) == (before.state, before.attributes)


@pytest.mark.parametrize(
    ("entity_id", "option", "method"),
    [
        ("select.desky_desk_touch_mode", "press_and_hold", "set_touch_mode"),
        ("select.desky_desk_display_unit", "in", "set_unit"),
    ],
)
async def test_setting_the_desk_did_not_apply(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    option: str,
    method: str,
) -> None:
    """Test a setting the desk ignored, even when sent again, is not shown as done."""
    getattr(mock_desk, method).side_effect = DeskSettingNotAppliedError("ignored")
    before = hass.states.get(entity_id).state

    with pytest.raises(HomeAssistantError) as err:
        await _call(
            hass, SELECT_DOMAIN, SERVICE_SELECT_OPTION, entity_id, {ATTR_OPTION: option}
        )

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "setting_not_applied"
    assert str(err.value) == "The desk did not apply the setting"
    assert hass.states.get(entity_id).state == before
