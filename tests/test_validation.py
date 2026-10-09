"""Test the Desky Desk height checks."""

from __future__ import annotations

from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.desky_desk.bluetooth import DeskBLEDevice
from custom_components.desky_desk.const import HeightLimit
from custom_components.desky_desk.validation import (
    allowed_move_range,
    checked_height_limit,
    validate_height_limit,
)

from . import desk_data


def test_height_limit_accepts_a_plain_string() -> None:
    """Test the limit is compared by value, so "upper" is the upper limit."""
    data = desk_data(height_limit_upper=110.0, height_limit_lower=70.0)

    with pytest.raises(ServiceValidationError) as err:
        validate_height_limit(data, "upper", 65.0)  # type: ignore[arg-type]

    assert err.value.translation_key == "limit_inverted_upper"
    assert err.value.translation_placeholders == {"height": "65.0", "other": "70.0"}


@pytest.mark.parametrize(
    ("upper", "lower", "allowed"),
    [
        (None, None, (60.0, 130.0)),
        (110.0, 70.0, (70.0, 110.0)),
        (133.0, 57.0, (60.0, 130.0)),
        (None, 132.0, (130.0, 130.0)),
        (57.0, None, (60.0, 60.0)),
    ],
)
def test_allowed_move_range(
    upper: float | None, lower: float | None, allowed: tuple[float, float]
) -> None:
    """Test the range is the desk's limits clamped to 60-130 cm, or 60-130 cm."""
    data = desk_data(height_limit_upper=upper, height_limit_lower=lower)

    assert allowed_move_range(data) == allowed


def test_checked_height_limit_returns_the_rounded_limit(mock_ble_device) -> None:
    """Test a limit is rounded to a whole unit, checked, and returned rounded."""
    data = desk_data(height_limit_upper=None, height_limit_lower=None)

    limit = checked_height_limit(
        data, DeskBLEDevice(mock_ble_device), HeightLimit.UPPER, 110.2
    )

    assert limit == 110.0


def test_checked_height_limit_checks_the_rounded_limit(mock_ble_device) -> None:
    """Test the rounded limit is what is checked: 70.4 cm is 70, not above 70."""
    data = desk_data(height_limit_upper=None, height_limit_lower=70.0)

    with pytest.raises(ServiceValidationError) as err:
        checked_height_limit(
            data, DeskBLEDevice(mock_ble_device), HeightLimit.UPPER, 70.4
        )

    assert err.value.translation_key == "limit_inverted_upper"
    assert err.value.translation_placeholders == {"height": "70.0", "other": "70.0"}
