"""Test the Desky Desk height checks."""

from __future__ import annotations

from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.desky_desk.validation import validate_height_limit

from . import desk_data


def test_height_limit_accepts_a_plain_string() -> None:
    """Test the limit is compared by value, so "upper" is the upper limit."""
    data = desk_data(height_limit_upper=110.0, height_limit_lower=70.0)

    with pytest.raises(ServiceValidationError) as err:
        validate_height_limit(data, "upper", 65.0)  # type: ignore[arg-type]

    assert err.value.translation_key == "limit_inverted_upper"
    assert err.value.translation_placeholders == {"height": "65.0", "other": "70.0"}
