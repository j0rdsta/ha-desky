"""Test the Desky Desk height checks."""

from __future__ import annotations

from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.desky_desk.validation import (
    allowed_move_range,
    limit_range,
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


@pytest.mark.parametrize(
    ("unit", "expected"),
    [("cm", (60.0, 124.0)), (None, (60.0, 124.0)), ("in", (61.0, 121.9))],
)
def test_limit_range(unit: str | None, expected: tuple[float, float]) -> None:
    """Test limits are 60-124 cm, or 24-48 in rounded inside to 0.1 cm."""
    assert limit_range(desk_data(unit_preference=unit)) == expected
