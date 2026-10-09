"""Test the Desky Desk select platform."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.select import (
    ATTR_OPTIONS,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
    SelectEntityDescription,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_OPTION,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.bluetooth import DeskCommandError
from custom_components.desky_desk.const import DOMAIN, SENSITIVITY_RESPONSE_HEADER
from custom_components.desky_desk.select import SELECT_DESCRIPTIONS, DeskSelect

from . import deliver_frame, desk_response, disconnect_desk, notify_desk, set_desk_state

SENSITIVITY = "select.desky_desk_collision_sensitivity"
TOUCH_MODE = "select.desky_desk_touch_mode"
UNIT = "select.desky_desk_display_unit"
STRINGS = Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"

DESCRIPTIONS = {description.key: description for description in SELECT_DESCRIPTIONS}


@pytest.mark.parametrize(
    ("entity_id", "unique_id_suffix", "state", "options"),
    [
        (SENSITIVITY, "sensitivity", "medium", ["high", "medium", "low"]),
        (TOUCH_MODE, "touch_mode", "one_press", ["one_press", "press_and_hold"]),
        (UNIT, "unit", "cm", ["cm", "in"]),
    ],
)
async def test_select_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    entity_id: str,
    unique_id_suffix: str,
    state: str,
    options: list[str],
) -> None:
    """Test each select is registered as configuration with the desk's option."""
    entry = entity_registry.async_get(entity_id)
    assert entry is not None
    assert entry.unique_id == f"{init_integration.unique_id}_{unique_id_suffix}"
    assert entry.entity_category is EntityCategory.CONFIG

    select_state = hass.states.get(entity_id)
    assert select_state is not None
    assert select_state.state == state
    assert select_state.attributes[ATTR_OPTIONS] == options


@pytest.mark.parametrize(
    ("entity_id", "field", "value", "expected"),
    [
        (SENSITIVITY, "sensitivity_level", 1, "high"),
        (SENSITIVITY, "sensitivity_level", 2, "medium"),
        (SENSITIVITY, "sensitivity_level", 3, "low"),
        (SENSITIVITY, "sensitivity_level", None, STATE_UNKNOWN),
        (SENSITIVITY, "sensitivity_level", 0, STATE_UNKNOWN),
        (SENSITIVITY, "sensitivity_level", 4, STATE_UNKNOWN),
        (TOUCH_MODE, "touch_mode", 0, "one_press"),
        (TOUCH_MODE, "touch_mode", 1, "press_and_hold"),
        (TOUCH_MODE, "touch_mode", None, STATE_UNKNOWN),
        (TOUCH_MODE, "touch_mode", 2, STATE_UNKNOWN),
        (UNIT, "unit_preference", "cm", "cm"),
        (UNIT, "unit_preference", "in", "in"),
        (UNIT, "unit_preference", None, STATE_UNKNOWN),
    ],
)
async def test_select_current_option(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    field: str,
    value: Any,
    expected: str,
) -> None:
    """Test each select maps the desk's reported value to an option."""
    await set_desk_state(hass, init_integration, **{field: value})

    assert hass.states.get(entity_id).state == expected


@pytest.mark.parametrize(
    ("entity_id", "option", "command", "argument", "follow_up"),
    [
        (SENSITIVITY, "high", "set_sensitivity", 1, "get_sensitivity"),
        (SENSITIVITY, "low", "set_sensitivity", 3, "get_sensitivity"),
        # The desk has no query for one setting, so all settings are read back
        (TOUCH_MODE, "press_and_hold", "set_touch_mode", 1, "get_settings"),
        (TOUCH_MODE, "one_press", "set_touch_mode", 0, "get_settings"),
        (UNIT, "in", "set_unit", "in", "get_settings"),
        (UNIT, "cm", "set_unit", "cm", "get_settings"),
    ],
)
async def test_select_option(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    option: str,
    command: str,
    argument: Any,
    follow_up: str | None,
) -> None:
    """Test selecting an option sends the matching command to the desk."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )

    getattr(mock_desk, command).assert_awaited_once_with(argument)
    if follow_up is None:
        mock_desk.get_sensitivity.assert_not_awaited()
    else:
        getattr(mock_desk, follow_up).assert_awaited_once_with()


async def test_select_state_follows_desk(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the option only changes once the desk reports the new value."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SENSITIVITY, ATTR_OPTION: "low"},
        blocking=True,
    )
    assert hass.states.get(SENSITIVITY).state == "medium"

    await set_desk_state(hass, init_integration, sensitivity_level=3)
    assert hass.states.get(SENSITIVITY).state == "low"


async def test_selects_unavailable_when_disconnected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the selects become unavailable and send nothing while disconnected."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    for entity_id in (SENSITIVITY, TOUCH_MODE, UNIT):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # Home Assistant skips unavailable entities
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: SENSITIVITY, ATTR_OPTION: "high"},
        blocking=True,
    )

    mock_desk.set_sensitivity.assert_not_awaited()
    mock_desk.get_sensitivity.assert_not_awaited()


@pytest.mark.parametrize(
    ("key", "option"),
    [
        ("sensitivity", "Extreme"),
        ("touch_mode", "Double tap"),
        ("unit", "mm"),
    ],
)
async def test_select_unknown_option_sends_nothing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    key: str,
    option: str,
) -> None:
    """Test an option outside the known mapping sends no command to the desk.

    Home Assistant rejects such options before they reach the entity, so this
    calls the entity directly.
    """
    entity = DeskSelect(init_integration.runtime_data, DESCRIPTIONS[key])

    await entity.async_select_option(option)

    mock_desk.set_sensitivity.assert_not_awaited()
    mock_desk.get_sensitivity.assert_not_awaited()
    mock_desk.set_touch_mode.assert_not_awaited()
    mock_desk.set_unit.assert_not_awaited()


async def test_select_unknown_key(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a select with an unrecognised key has no option and sends nothing."""
    entity = DeskSelect(
        init_integration.runtime_data,
        SelectEntityDescription(key="unknown", options=["a", "b"]),
    )

    assert entity.current_option is None

    await entity.async_select_option("a")

    mock_desk.set_sensitivity.assert_not_awaited()
    mock_desk.set_touch_mode.assert_not_awaited()
    mock_desk.set_unit.assert_not_awaited()


@pytest.mark.parametrize(
    ("entity_id", "field", "option", "reported"),
    [
        (UNIT, "unit_preference", "in", "in"),
        (TOUCH_MODE, "touch_mode", "press_and_hold", 1),
    ],
)
async def test_select_shows_the_desk_report_after_selecting(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    field: str,
    option: str,
    reported: Any,
) -> None:
    """After a change the select follows the desk's own report, not a guess."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )
    mock_desk.get_settings.assert_awaited_once_with()
    # Nothing changes until the desk reports the setting
    assert hass.states.get(entity_id).state != option

    notify_desk(mock_desk, **{field: reported})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == option


@pytest.mark.parametrize(
    ("entity_id", "option", "command"),
    [(UNIT, "in", "set_unit"), (TOUCH_MODE, "press_and_hold", "set_touch_mode")],
)
async def test_select_skips_read_back_when_the_write_fails(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    option: str,
    command: str,
) -> None:
    """A setting that could not be sent is not read back."""
    getattr(mock_desk, command).side_effect = DeskCommandError("write failed")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
            blocking=True,
        )

    mock_desk.get_settings.assert_not_awaited()


async def test_unreported_settings_show_no_option(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """A desk that has not reported a setting shows no option, and can still be set."""
    notify_desk(mock_desk, unit_preference=None, touch_mode=None)
    await hass.async_block_till_done()

    assert hass.states.get(UNIT).state == STATE_UNKNOWN
    assert hass.states.get(TOUCH_MODE).state == STATE_UNKNOWN

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: TOUCH_MODE, ATTR_OPTION: "one_press"},
        blocking=True,
    )
    mock_desk.set_touch_mode.assert_awaited_once_with(0)


async def test_settings_are_read_again_after_reconnecting(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """While disconnected the selects are unavailable; afterwards they show the new report."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert hass.states.get(UNIT).state == STATE_UNAVAILABLE
    assert hass.states.get(TOUCH_MODE).state == STATE_UNAVAILABLE

    # The unit was changed on the hand controller while disconnected
    mock_desk.is_connected = True
    notify_desk(mock_desk, unit_preference="in", touch_mode=0)
    await hass.async_block_till_done()

    assert hass.states.get(UNIT).state == "in"
    assert hass.states.get(TOUCH_MODE).state == "one_press"


async def test_sensitivity_follows_a_desk_report(
    hass: HomeAssistant, desk_client: MagicMock
) -> None:
    """Test the select shows a sensitivity report from the desk at once."""
    assert hass.states.get(SENSITIVITY).state == STATE_UNKNOWN

    deliver_frame(desk_client, desk_response(SENSITIVITY_RESPONSE_HEADER, 0x03))
    await hass.async_block_till_done()
    assert hass.states.get(SENSITIVITY).state == "low"


@pytest.mark.parametrize(
    ("key", "option", "label"),
    [
        ("sensitivity", "high", "High"),
        ("sensitivity", "medium", "Medium"),
        ("sensitivity", "low", "Low"),
        ("touch_mode", "one_press", "One press"),
        ("touch_mode", "press_and_hold", "Press and hold"),
        ("unit", "cm", "cm"),
        ("unit", "in", "in"),
    ],
)
async def test_select_states_show_the_same_labels(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    key: str,
    option: str,
    label: str,
) -> None:
    """Each state key is shown with the label the select used before it had keys."""
    translations = await async_get_translations(hass, "en", "entity", {DOMAIN})

    assert translations[f"component.{DOMAIN}.entity.select.{key}.state.{option}"] == (
        label
    )


async def test_select_options_match_translations() -> None:
    """Every option has a state translation, and no translation is left over."""
    strings = json.loads(STRINGS.read_text())["entity"]["select"]

    for description in SELECT_DESCRIPTIONS:
        assert description.options is not None
        assert set(description.options) == set(strings[description.key]["state"]), (
            description.key
        )


@pytest.mark.parametrize(
    ("entity_id", "label"),
    [(SENSITIVITY, "High"), (TOUCH_MODE, "Press and hold")],
)
async def test_select_rejects_old_labels(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    label: str,
) -> None:
    """An automation that still sets an English label gets an error, not a silent no-op."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: label},
            blocking=True,
        )

    mock_desk.set_sensitivity.assert_not_awaited()
    mock_desk.set_touch_mode.assert_not_awaited()
