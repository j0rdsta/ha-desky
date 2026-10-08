"""Checks a desk command must pass before anything is sent to the desk."""

from __future__ import annotations

from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, MAX_HEIGHT, MIN_HEIGHT
from .coordinator import DeskData

LIMIT_UPPER = "upper"
LIMIT_LOWER = "lower"


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


def validate_move_to_height(data: DeskData, height: float) -> None:
    """Raise a translated validation error for a height the desk cannot move to.

    The range is the desk's limits, or 60-130 cm for a limit that is not set.
    The desk reports limits a few cm outside 60-130 cm, so they are clamped.
    """
    low = MIN_HEIGHT if data.height_limit_lower is None else data.height_limit_lower
    high = MAX_HEIGHT if data.height_limit_upper is None else data.height_limit_upper
    _check_height_in_range(height, _clamp(low), _clamp(high), "height_out_of_range")


def validate_height_limit(data: DeskData, limit: str, height: float) -> None:
    """Raise a translated validation error for a height limit the desk must not get.

    The limit must be within 60-130 cm. If the other limit is set, an upper
    limit must be above it and a lower limit below it.
    """
    _check_height_in_range(height, MIN_HEIGHT, MAX_HEIGHT, "limit_out_of_range")
    other = data.height_limit_lower if limit == LIMIT_UPPER else data.height_limit_upper
    if other is None:
        return
    if height <= other if limit == LIMIT_UPPER else height >= other:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=f"limit_inverted_{limit}",
            translation_placeholders={
                "height": f"{height:.1f}",
                "other": f"{other:.1f}",
            },
        )
