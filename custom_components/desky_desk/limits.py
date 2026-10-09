"""The desk's height limits, as it last reported them or was sent them."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .const import HeightLimit


@dataclass(frozen=True, slots=True)
class LimitValue:
    """A height limit as the desk takes it, and in centimetres."""

    raw: int  # tenths of the unit below, as sent to the desk
    unit: str  # "cm" or "in"
    cm: float


@dataclass(frozen=True, slots=True)
class HeightLimits:
    """Which height limits are set, and their values."""

    # Whether each limit is set; None until the desk reports its limit status
    upper_set: bool | None = None
    lower_set: bool | None = None
    upper: LimitValue | None = None
    lower: LimitValue | None = None

    def is_set(self, limit: HeightLimit) -> bool | None:
        """Return if a limit is set, or None before the desk has said."""
        return self.upper_set if limit is HeightLimit.UPPER else self.lower_set

    def value(self, limit: HeightLimit) -> LimitValue | None:
        """Return a limit's value, or None when it is not set or not reported."""
        if self.is_set(limit) is False:
            return None
        return self.upper if limit is HeightLimit.UPPER else self.lower

    @property
    def any_set(self) -> bool:
        """Return if any limit is set."""
        return bool(self.upper_set or self.lower_set)

    @property
    def fully_known(self) -> bool:
        """Return if the desk has said which limits are set, and each set one's value."""
        return all(
            (is_set := self.is_set(limit)) is not None
            and (not is_set or self.value(limit) is not None)
            for limit in HeightLimit
        )

    def with_status(self, *, upper_set: bool, lower_set: bool) -> HeightLimits:
        """Return the limits with the desk's report of which are set."""
        return replace(self, upper_set=upper_set, lower_set=lower_set)

    def with_value(self, limit: HeightLimit, value: LimitValue) -> HeightLimits:
        """Return the limits with a limit's value as the desk reported it."""
        if limit is HeightLimit.UPPER:
            return replace(self, upper=value)
        return replace(self, lower=value)

    def with_limit(self, limit: HeightLimit, value: LimitValue) -> HeightLimits:
        """Return the limits with a limit set to a value, as it was just sent."""
        if limit is HeightLimit.UPPER:
            return replace(self, upper_set=True, upper=value)
        return replace(self, lower_set=True, lower=value)
