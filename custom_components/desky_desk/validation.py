"""Height checks for desk commands."""

from __future__ import annotations

from homeassistant.exceptions import ServiceValidationError

from .const import (
    CM_PER_INCH,
    DOMAIN,
    LIMIT_MAX_HEIGHT,
    LIMIT_MAX_HEIGHT_IN,
    LIMIT_MIN_HEIGHT,
    LIMIT_MIN_HEIGHT_IN,
    MAX_HEIGHT,
    MIN_HEIGHT,
    HeightLimit,
)
from .coordinator import DeskData

# The inch limit range in cm, rounded to 0.1 cm like decoded heights: 61.0-121.9
INCH_LIMIT_RANGE_CM = (
    round(LIMIT_MIN_HEIGHT_IN * CM_PER_INCH, 1),
    round(LIMIT_MAX_HEIGHT_IN * CM_PER_INCH, 1),
)

# The error for a limit on the wrong side of the other limit
INVERTED_LIMIT_KEYS = {
    HeightLimit.UPPER: "limit_inverted_upper",
    HeightLimit.LOWER: "limit_inverted_lower",
}


def _check_height_in_range(height: float, low: float, high: float, key: str) -> None:
    """Raise a translated validation error for a height outside low-high."""
    if not low <= height <= high:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders={
                "height": f"{height:.1f}",
                "min": f"{low:.1f}",
                "max": f"{high:.1f}",
            },
        )


def _clamp(height: float) -> float:
    """Return a height limited to the desk's physical range."""
    return min(max(height, MIN_HEIGHT), MAX_HEIGHT)


def allowed_move_range(data: DeskData) -> tuple[float, float]:
    """Return the lowest and highest height the desk may be moved to.

    The range is the desk's limits, or 60-130 cm for a limit that is not set.
    The desk reports limits a few cm outside 60-130 cm, so they are clamped.
    """
    low = MIN_HEIGHT if data.height_limit_lower is None else data.height_limit_lower
    high = MAX_HEIGHT if data.height_limit_upper is None else data.height_limit_upper
    return _clamp(low), _clamp(high)


def validate_move_to_height(data: DeskData, height: float) -> None:
    """Raise a translated validation error for a height the desk cannot move to."""
    low, high = allowed_move_range(data)
    _check_height_in_range(height, low, high, "height_out_of_range")


def limit_range(data: DeskData) -> tuple[float, float]:
    """Return the lowest and highest height limit the desk accepts, in cm.

    The desk takes limits in its display unit: 60-124 cm, or 24-48 in. A desk
    that has not reported its unit gets the cm range.
    """
    if data.unit_preference == "in":
        return INCH_LIMIT_RANGE_CM
    return LIMIT_MIN_HEIGHT, LIMIT_MAX_HEIGHT


def validate_height_limit(data: DeskData, limit: HeightLimit, height: float) -> None:
    """Raise a translated validation error for a height limit the desk must not get.

    The limit must be within limit_range(). If the other limit is set, an
    upper limit must be above it and a lower limit below it.
    """
    low, high = limit_range(data)
    _check_height_in_range(height, low, high, "limit_out_of_range")
    upper = limit == HeightLimit.UPPER
    other = data.height_limit_lower if upper else data.height_limit_upper
    if other is None:
        return
    if height <= other if upper else height >= other:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=INVERTED_LIMIT_KEYS[limit],
            translation_placeholders={
                "height": f"{height:.1f}",
                "other": f"{other:.1f}",
            },
        )
