"""Test the Desky Desk actions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.bluetooth import DeskCommandError
from custom_components.desky_desk.const import DOMAIN

from . import notify_desk, set_desk_state

COVER = "cover.desky_desk"
UPPER_LIMIT = "number.desky_desk_upper_height_limit"
LOWER_LIMIT = "number.desky_desk_lower_height_limit"

# (action, data, desk method the action calls)
ACTIONS = [
    ("move_to_height", {"height": 100}, "move_to_height"),
    ("set_height_limit", {"limit": "upper", "height": 125}, "set_height_limit_upper"),
    ("clear_height_limits", {}, "clear_height_limits"),
]
COMMANDS = (
    "move_to_height",
    "set_height_limit_upper",
    "set_height_limit_lower",
    "clear_height_limits",
)


async def _call(
    hass: HomeAssistant, action: str, data: dict[str, Any], target: Any = None
) -> None:
    await hass.services.async_call(
        DOMAIN,
        action,
        {**(target or {ATTR_ENTITY_ID: COVER}), **data},
        blocking=True,
    )


def _assert_nothing_sent(desk: MagicMock) -> None:
    for method in COMMANDS:
        getattr(desk, method).assert_not_awaited()


@pytest.mark.usefixtures("mock_bluetooth")
async def test_actions_registered_without_a_loaded_desk(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the actions exist when every desk is disabled, and no others do."""
    mock_config_entry.disabled_by = ConfigEntryDisabler.USER
    mock_config_entry.add_to_hass(hass)

    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert set(hass.services.async_services_for_domain(DOMAIN)) == {
        "move_to_height",
        "set_height_limit",
        "clear_height_limits",
    }


async def test_move_to_height(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a height inside the effective range moves the desk."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=None, height_limit_lower=None
    )

    await _call(hass, "move_to_height", {"height": 110})

    mock_desk.move_to_height.assert_awaited_once_with(110.0)


@pytest.mark.parametrize(
    ("height", "upper", "lower", "low", "high"),
    [
        (130.5, None, None, "60.0", "130.0"),
        (59.0, None, None, "60.0", "130.0"),
        (125.0, 120.0, 65.0, "65.0", "120.0"),
        (62.0, 120.0, 65.0, "65.0", "120.0"),
    ],
)
async def test_move_to_height_out_of_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    height: float,
    upper: float | None,
    lower: float | None,
    low: str,
    high: str,
) -> None:
    """Test a height outside the limits, or 60-130 cm without them, is rejected."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=upper, height_limit_lower=lower
    )

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "move_to_height", {"height": height})

    assert err.value.translation_key == "height_out_of_range"
    assert err.value.translation_placeholders == {
        "height": f"{height:.1f}",
        "min": low,
        "max": high,
    }
    _assert_nothing_sent(mock_desk)


@pytest.mark.parametrize(
    ("limit", "height", "command"),
    [
        ("upper", 120, "set_height_limit_upper"),
        ("lower", 70, "set_height_limit_lower"),
    ],
)
async def test_set_height_limit(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    limit: str,
    height: float,
    command: str,
) -> None:
    """Test setting a limit sends it and shows the limit the desk reports."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=125.0, height_limit_lower=65.0
    )

    await _call(hass, "set_height_limit", {"limit": limit, "height": height})

    getattr(mock_desk, command).assert_awaited_once_with(float(height))
    mock_desk.get_limits.assert_awaited_once()

    # The desk answers the limit query
    notify_desk(mock_desk, **{f"height_limit_{limit}": float(height)})
    await hass.async_block_till_done()
    entity_id = UPPER_LIMIT if limit == "upper" else LOWER_LIMIT
    assert float(hass.states.get(entity_id).state) == height


@pytest.mark.parametrize(
    ("limit", "height", "other"),
    [
        ("upper", 70, "70.0"),
        ("upper", 65, "70.0"),
        ("lower", 110, "110.0"),
        ("lower", 120, "110.0"),
    ],
)
async def test_inverted_height_limit_rejected(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    limit: str,
    height: float,
    other: str,
) -> None:
    """Test an upper limit at or below the lower one, or the reverse, is rejected."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=110.0, height_limit_lower=70.0
    )

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "set_height_limit", {"limit": limit, "height": height})

    assert err.value.translation_key == f"limit_inverted_{limit}"
    assert err.value.translation_placeholders == {
        "height": f"{height:.1f}",
        "other": other,
    }
    _assert_nothing_sent(mock_desk)


async def test_height_limit_out_of_range(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a limit outside 60-130 cm is rejected."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "set_height_limit", {"limit": "upper", "height": 135})

    assert err.value.translation_key == "limit_out_of_range"
    _assert_nothing_sent(mock_desk)


async def test_clear_height_limits(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test clearing the limits, after which the limit entities show none."""
    await _call(hass, "clear_height_limits", {})

    mock_desk.clear_height_limits.assert_awaited_once()
    mock_desk.get_limits.assert_awaited_once()

    notify_desk(
        mock_desk,
        height_limit_upper=None,
        height_limit_lower=None,
        limits_enabled=False,
    )
    await hass.async_block_till_done()
    for entity_id in (UPPER_LIMIT, LOWER_LIMIT):
        state = hass.states.get(entity_id)
        assert state.state == "unknown"
        assert state.attributes["limits_enabled"] is False


async def test_target_by_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test an action can target the desk's device."""
    device = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )[0]

    await _call(hass, "clear_height_limits", {}, {ATTR_DEVICE_ID: device.id})

    mock_desk.clear_height_limits.assert_awaited_once()


@pytest.mark.parametrize(("action", "data", "command"), ACTIONS)
async def test_action_on_unloaded_desk(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    action: str,
    data: dict[str, Any],
    command: str,
) -> None:
    """Test an action on a desk whose entry is not loaded fails, naming the desk."""
    await hass.config_entries.async_unload(init_integration.entry_id)
    mock_desk.reset_mock()

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, action, data)

    assert err.value.translation_key == "desk_not_loaded"
    assert err.value.translation_placeholders == {"desk": "Desky Desk"}
    _assert_nothing_sent(mock_desk)


async def test_action_without_a_desk(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test an action that targets no desk fails."""
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "clear_height_limits", {}, {ATTR_ENTITY_ID: "light.other"})

    assert err.value.translation_key == "no_desk_targeted"
    _assert_nothing_sent(mock_desk)


@pytest.mark.parametrize(("action", "data", "command"), ACTIONS)
async def test_action_on_disconnected_desk(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    action: str,
    data: dict[str, Any],
    command: str,
) -> None:
    """Test an action on a disconnected desk fails instead of doing nothing."""
    await set_desk_state(hass, init_integration, is_connected=False)

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, action, data)

    assert err.value.translation_key == "not_connected"
    _assert_nothing_sent(mock_desk)


@pytest.mark.parametrize(("action", "data", "command"), ACTIONS)
async def test_action_write_fails(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    action: str,
    data: dict[str, Any],
    command: str,
) -> None:
    """Test a failed write fails the action and leaves the entities unchanged."""
    getattr(mock_desk, command).side_effect = DeskCommandError("write failed")
    before = {state.entity_id: state.state for state in hass.states.async_all()}

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, action, data)

    assert err.value.translation_key == "command_failed"
    assert err.value.translation_placeholders == {"error": "write failed"}
    mock_desk.get_limits.assert_not_awaited()
    assert {s.entity_id: s.state for s in hass.states.async_all()} == before
