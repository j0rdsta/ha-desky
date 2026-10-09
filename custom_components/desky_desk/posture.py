"""Follow the desk's posture from the height it stops at."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import time

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .bluetooth import DeskBLEDevice
from .const import POSTURE_SETTLE_SECONDS, Posture, height_known


class PostureTracker:
    """Sitting or standing, from where the desk has stopped.

    The posture follows the height only once the desk has stood still for
    POSTURE_SETTLE_SECONDS with no commanded move in flight, so passing the
    threshold mid-move is not a posture change. It is unknown while the desk
    is disconnected or has not reported a height, so neither posture is
    counted for that time.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        standing_threshold: float,
        on_change: Callable[[], None],
    ) -> None:
        """Initialize the tracker; on_change runs when a settled posture changes."""
        self._hass = hass
        self.standing_threshold = standing_threshold
        self._on_change = on_change
        # Sitting or standing once the desk has stopped; None while unknown
        self.posture: Posture | None = None
        # time.monotonic() when the posture last changed, or None if it never has
        self.changed_at: float | None = None
        # The last height seen, and time.monotonic() when it was first seen
        self._last_height: float | None = None
        self._height_changed_at = 0.0
        self._device: DeskBLEDevice | None = None
        self._cancel_settle: CALLBACK_TYPE | None = None

    @callback
    def track(self, device: DeskBLEDevice) -> None:
        """Wait for the desk to stand still before the posture follows its height."""
        now = time.monotonic()
        self._device = device
        if not device.is_connected or not height_known(device.height_cm):
            self.cancel()
            self._last_height = None
            if self.posture is not None:
                self.posture = None
                self.changed_at = now
            return
        if device.height_cm != self._last_height:
            self._last_height = device.height_cm
            self._height_changed_at = now
        elif not device.is_moving:
            return
        self._schedule_settle()

    @callback
    def cancel(self) -> None:
        """Cancel a pending check of the posture."""
        if self._cancel_settle is not None:
            self._cancel_settle()
            self._cancel_settle = None

    @callback
    def _schedule_settle(self) -> None:
        """Check the posture once the desk has stood still long enough."""
        self.cancel()
        self._cancel_settle = async_call_later(
            self._hass, POSTURE_SETTLE_SECONDS, self._async_settle
        )

    @callback
    def _async_settle(self, _now: datetime) -> None:
        """Set the posture from the height the desk has stopped at."""
        self._cancel_settle = None
        device = self._device
        assert device is not None  # a check is scheduled only by track()
        if device.is_moving:
            self._schedule_settle()
            return
        posture = (
            Posture.STANDING
            if device.height_cm >= self.standing_threshold
            else Posture.SITTING
        )
        if posture == self.posture:
            return
        # A change between postures dates from when the desk stopped; a posture
        # that was unknown is known from now, so no unknown time is counted
        self.changed_at = (
            time.monotonic() if self.posture is None else self._height_changed_at
        )
        self.posture = posture
        self._on_change()
