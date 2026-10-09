"""Test the Desky Desk number platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.const import (
    DOMAIN,
    LIMIT_RANGE_CM,
    MAX_HEIGHT,
    MIN_HEIGHT,
    HeightLimit,
)
from custom_components.desky_desk.number import DeskHeightLimitNumber

from . import disconnect_desk, notify_desk, set_desk_state

HEIGHT = "number.desky_desk_height"
UPPER_LIMIT = "number.desky_desk_upper_height_limit"
LOWER_LIMIT = "number.desky_desk_lower_height_limit"
NUMBERS = [HEIGHT, UPPER_LIMIT, LOWER_LIMIT]


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Set a number through the number service."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def test_height_number(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the height number reports the desk height in centimetres."""
    state = hass.states.get(HEIGHT)
    assert state is not None
    assert state.state == "80.0"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Desky Desk Height"
    assert state.attributes[ATTR_MIN] == MIN_HEIGHT
    assert state.attributes[ATTR_MAX] == MAX_HEIGHT
    assert state.attributes[ATTR_STEP] == 0.1
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS

    notify_desk(mock_desk, height_cm=95.5)
    await hass.async_block_till_done()

    assert hass.states.get(HEIGHT).state == "95.5"


@pytest.mark.parametrize("height", [MIN_HEIGHT, 85.7, 100.0, MAX_HEIGHT])
async def test_set_height(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    height: float,
) -> None:
    """Test setting the height moves the desk there and polls it for progress."""
    # Without limits the whole 60-130 cm range is allowed
    await set_desk_state(
        hass, init_integration, height_limit_upper=None, height_limit_lower=None
    )
    mock_desk.get_status.reset_mock()

    await _set_value(hass, HEIGHT, height)

    mock_desk.move_to_height.assert_awaited_once_with(height)
    # The coordinator refresh asks the desk for its status
    mock_desk.get_status.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("entity_id", "friendly_name", "value", "unit", "step"),
    [
        (
            UPPER_LIMIT,
            "Desky Desk Upper height limit",
            "120.0",
            UnitOfLength.CENTIMETERS,
            1.0,
        ),
        (
            LOWER_LIMIT,
            "Desky Desk Lower height limit",
            "65.0",
            UnitOfLength.CENTIMETERS,
            1.0,
        ),
    ],
)
async def test_desk_number_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    friendly_name: str,
    value: str,
    unit: str,
    step: float,
) -> None:
    """Test the setting numbers report the desk's configured values."""
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == value
    assert state.attributes[ATTR_FRIENDLY_NAME] == friendly_name
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit
    assert state.attributes[ATTR_STEP] == step


@pytest.mark.parametrize(
    ("entity_id", "minimum", "maximum"),
    [
        (UPPER_LIMIT, *LIMIT_RANGE_CM["cm"]),
        (LOWER_LIMIT, *LIMIT_RANGE_CM["cm"]),
    ],
)
async def test_desk_number_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    minimum: float,
    maximum: float,
) -> None:
    """Test the limit numbers expose the range the desk accepts, 60-124 cm."""
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_MIN] == minimum
    assert state.attributes[ATTR_MAX] == maximum


@pytest.mark.parametrize("entity_id", [UPPER_LIMIT, LOWER_LIMIT])
async def test_limit_number_range_in_inches(
    hass: HomeAssistant, init_integration: MockConfigEntry, entity_id: str
) -> None:
    """Test a desk showing inches accepts 24-48 in, shown as 61.0-121.9 cm."""
    await set_desk_state(hass, init_integration, limit_range=LIMIT_RANGE_CM["in"])

    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_MIN] == 61.0
    assert state.attributes[ATTR_MAX] == 121.9


async def test_limit_number_above_the_range_rejected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test Home Assistant refuses an upper limit above 124 cm before it is sent."""
    mock_desk.reset_mock()

    with pytest.raises(ServiceValidationError) as err:
        await _set_value(hass, UPPER_LIMIT, 125.0)

    assert err.value.translation_key == "out_of_range"
    assert mock_desk.method_calls == []


@pytest.mark.parametrize(
    ("entity_id", "value", "setter", "sent", "getter"),
    [
        (
            UPPER_LIMIT,
            124.0,
            "set_height_limit",
            (HeightLimit.UPPER, 124.0),
            "get_limits",
        ),
        (
            LOWER_LIMIT,
            70.0,
            "set_height_limit",
            (HeightLimit.LOWER, 70.0),
            "get_limits",
        ),
        # Sent in whole centimetres, as the desk stores limits
        (
            LOWER_LIMIT,
            70.4,
            "set_height_limit",
            (HeightLimit.LOWER, 70.0),
            "get_limits",
        ),
    ],
)
async def test_set_desk_number(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    value: float,
    setter: str,
    sent: tuple[Any, ...],
    getter: str,
) -> None:
    """Test setting a value sends it to the desk and reads it back."""
    await _set_value(hass, entity_id, value)

    getattr(mock_desk, setter).assert_awaited_once_with(*sent)
    getattr(mock_desk, getter).assert_awaited_once_with()


@pytest.mark.parametrize(
    ("entity_id", "value", "key", "other", "message"),
    [
        (
            UPPER_LIMIT,
            70.0,
            "limit_inverted_upper",
            "70.0",
            "The upper limit of 70.0 cm must be above the lower limit of 70.0 cm",
        ),
        (
            UPPER_LIMIT,
            65.0,
            "limit_inverted_upper",
            "70.0",
            "The upper limit of 65.0 cm must be above the lower limit of 70.0 cm",
        ),
        # Rounded to 70 cm first, so it is not above the lower limit
        (
            UPPER_LIMIT,
            70.4,
            "limit_inverted_upper",
            "70.0",
            "The upper limit of 70.0 cm must be above the lower limit of 70.0 cm",
        ),
        (
            LOWER_LIMIT,
            110.0,
            "limit_inverted_lower",
            "110.0",
            "The lower limit of 110.0 cm must be below the upper limit of 110.0 cm",
        ),
        (
            LOWER_LIMIT,
            120.0,
            "limit_inverted_lower",
            "110.0",
            "The lower limit of 120.0 cm must be below the upper limit of 110.0 cm",
        ),
    ],
)
async def test_inverted_limit_rejected(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    value: float,
    key: str,
    other: str,
    message: str,
) -> None:
    """Test a limit number rejects an inverted limit, as the action does."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=110.0, height_limit_lower=70.0
    )
    mock_desk.reset_mock()

    with pytest.raises(ServiceValidationError) as err:
        await _set_value(hass, entity_id, value)

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == key
    # The message shows the rounded height that would have been sent
    assert err.value.translation_placeholders["other"] == other
    assert str(err.value) == message
    mock_desk.set_height_limit.assert_not_awaited()
    mock_desk.get_limits.assert_not_awaited()
    assert hass.states.get(UPPER_LIMIT).state == "110.0"
    assert hass.states.get(LOWER_LIMIT).state == "70.0"


@pytest.mark.parametrize(
    ("entity_id", "value", "limit"),
    [
        (UPPER_LIMIT, 61.0, HeightLimit.UPPER),
        (LOWER_LIMIT, 123.0, HeightLimit.LOWER),
    ],
)
async def test_limit_without_the_other_limit(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    value: float,
    limit: HeightLimit,
) -> None:
    """Test a limit is only checked against the other limit when that one is set."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=None, height_limit_lower=None
    )

    await _set_value(hass, entity_id, value)

    mock_desk.set_height_limit.assert_awaited_once_with(limit, value)


async def test_height_outside_limits_rejected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the Height number refuses a height outside the desk's limits, as the action does."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=110.0, height_limit_lower=70.0
    )
    mock_desk.reset_mock()

    with pytest.raises(ServiceValidationError) as err:
        await _set_value(hass, HEIGHT, 120.0)

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "height_out_of_range"
    assert err.value.translation_placeholders == {
        "height": "120.0",
        "min": "70.0",
        "max": "110.0",
    }
    mock_desk.move_to_height.assert_not_awaited()


async def test_height_inside_limits_moves(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a height inside the limits still moves the desk."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=110.0, height_limit_lower=70.0
    )

    await _set_value(hass, HEIGHT, 100.0)

    mock_desk.move_to_height.assert_awaited_once_with(100.0)


@pytest.mark.parametrize(
    ("entity_id", "suffix"),
    [
        (HEIGHT, "height"),
        (UPPER_LIMIT, "height_limit_upper"),
        (LOWER_LIMIT, "height_limit_lower"),
    ],
)
async def test_number_ids(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    entity_id: str,
    suffix: str,
) -> None:
    """Test the number entity IDs and unique IDs never change."""
    entry = entity_registry.async_get(entity_id)

    assert entry is not None
    assert entry.unique_id == f"{init_integration.unique_id}_{suffix}"


async def test_limit_number_accepts_a_plain_string(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a limit given as the plain string "upper" reads the upper limit."""
    entity = DeskHeightLimitNumber(init_integration.runtime_data, "upper")  # type: ignore[arg-type]

    assert entity.native_value == 120.0


async def test_desk_numbers_without_values(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test settings the desk has not reported show as unknown."""
    await set_desk_state(
        hass,
        init_integration,
        height_limit_upper=None,
        height_limit_lower=None,
    )

    assert hass.states.get(UPPER_LIMIT).state == STATE_UNKNOWN
    assert hass.states.get(LOWER_LIMIT).state == STATE_UNKNOWN
    assert hass.states.get(HEIGHT).state == "80.0"


async def test_numbers_follow_connection(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the numbers go unavailable on disconnect and come back on reconnect."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity_id).state == STATE_UNAVAILABLE for entity_id in NUMBERS
    )

    # Setting an unavailable number sends nothing to the desk
    await _set_value(hass, UPPER_LIMIT, 110.0)
    mock_desk.set_height_limit.assert_not_called()

    notify_desk(mock_desk, is_connected=True, height_cm=90.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEIGHT).state == "90.0"
    assert hass.states.get(UPPER_LIMIT).state == "120.0"
    assert hass.states.get(LOWER_LIMIT).state == "65.0"
