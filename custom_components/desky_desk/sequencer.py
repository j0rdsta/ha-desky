"""Write frames to the desk one at a time, and send timed sequences of them."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from itertools import groupby
import logging
from operator import itemgetter
import time

from .errors import DeskNotConnectedError

_LOGGER = logging.getLogger(__name__)

# A frame and when to write it, in seconds after its sequence starts
type Step = tuple[float, bytes]


class Clock:
    """Monotonic time and pauses for timed frames; tests use a virtual one."""

    def time(self) -> float:
        """Return the monotonic time in seconds."""
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        """Wait the given number of seconds."""
        await asyncio.sleep(seconds)


class _Cancel(Enum):
    """Why a sequence was cancelled."""

    SUPERSEDED = "superseded by a stop or a new movement command"
    DISCONNECTED = "the desk disconnected"


@dataclass(eq=False, slots=True)
class _Sequence:
    """A timed sequence being sent, and why it was cancelled, if it was."""

    task: asyncio.Task[None]
    cancelled_by: _Cancel | None = None

    def cancel(self, reason: _Cancel) -> None:
        """Cancel the sequence; a disconnect outranks being superseded."""
        if self.cancelled_by is not _Cancel.DISCONNECTED:
            self.cancelled_by = reason
        self.task.cancel(reason.value)


class Sequencer:
    """Write frames to the desk one at a time, and send timed sequences of them.

    A pause never holds the write lock, so a stop is never held up behind a
    sequence. The movement or stop frames still due are one motion sequence,
    which the next one replaces.
    """

    def __init__(
        self,
        write_frame: Callable[[bytes], Awaitable[None]],
        clock: Clock | None = None,
    ) -> None:
        """Write each frame with write_frame, timing sequences on the clock."""
        self._write_frame = write_frame
        self._clock = clock or Clock()
        # Frames go out one at a time, so concurrent callers never interleave
        self._lock = asyncio.Lock()
        self._running: dict[asyncio.Task[None], _Sequence] = {}
        self._motion: _Sequence | None = None

    @property
    def idle(self) -> bool:
        """Return if no sequence is being sent."""
        return not self._running

    async def write(self, *frames: bytes) -> None:
        """Write frames in order, with no other write in between.

        The lock is held only for the writes, never during a sequence's pauses.
        """
        async with self._lock:
            for frame in frames:
                await self._write_frame(frame)

    async def pause(self, seconds: float) -> None:
        """Wait on the sequencer's clock, without holding the write lock."""
        await self._clock.sleep(seconds)

    async def run_setting(self, steps: Iterable[Step]) -> None:
        """Send a sequence and wait for it to finish.

        A stop or a movement command does not cancel it. A disconnect does, and
        raises DeskNotConnectedError.
        """
        await self._wait(self._start(steps))

    async def run_motion(self, steps: Iterable[Step]) -> None:
        """Send movement or stop frames in place of those still due, and wait.

        Cut short by a stop or a new movement command, it returns quietly. Cut
        short by a disconnect, it raises DeskNotConnectedError.
        """
        await self._wait(self._start_motion(steps))

    def start_motion(self, steps: Iterable[Step]) -> None:
        """Send movement frames in the background, in place of those still due.

        A failed write ends them, and is only logged.
        """
        self._start_motion(steps)

    def cancel_motion(self) -> None:
        """Cancel the movement or stop frames still due."""
        if (sequence := self._motion) is not None:
            self._motion = None
            sequence.cancel(_Cancel.SUPERSEDED)

    def cancel_all(self) -> None:
        """Cancel every sequence, as the desk has disconnected."""
        self._motion = None
        for sequence in self._running.values():
            sequence.cancel(_Cancel.DISCONNECTED)

    async def wait_cancelled(self) -> None:
        """Wait until every cancelled sequence has finished."""
        await asyncio.gather(*self._running, return_exceptions=True)

    def _start(self, steps: Iterable[Step]) -> _Sequence:
        """Start sending a sequence in the background."""
        task = asyncio.create_task(self._send(steps))
        sequence = self._running[task] = _Sequence(task)
        task.add_done_callback(self._done)
        return sequence

    def _start_motion(self, steps: Iterable[Step]) -> _Sequence:
        """Start a motion sequence, cancelling the one it replaces."""
        self.cancel_motion()
        sequence = self._motion = self._start(steps)
        return sequence

    def _done(self, task: asyncio.Task[None]) -> None:
        """Forget a finished sequence; a failure was already raised or is logged."""
        sequence = self._running.pop(task)
        if self._motion is sequence:
            self._motion = None
        if not task.cancelled() and (err := task.exception()) is not None:
            _LOGGER.debug("Timed command sequence ended: %s", err)

    async def _send(self, steps: Iterable[Step]) -> None:
        """Write each frame at its time, never holding the write lock in a pause.

        Frames due at the same time go out together, so nothing else is written
        between a handshake and the command it wakes the desk for.
        """
        start = self._clock.time()
        for at, group in groupby(steps, key=itemgetter(0)):
            wait = start + at - self._clock.time()
            if wait > 0:
                await self._clock.sleep(wait)
            else:
                # Running late, as after a slow write: move the rest of the
                # sequence back rather than send its frames in a burst
                start -= wait
            await self.write(*(frame for _, frame in group))

    async def _wait(self, sequence: _Sequence) -> None:
        """Wait for a sequence, turning its cancellation into the caller's result."""
        try:
            await sequence.task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise  # the caller itself is being cancelled
            if sequence.cancelled_by is _Cancel.DISCONNECTED:
                raise DeskNotConnectedError("The desk disconnected") from None
            if sequence.cancelled_by is not _Cancel.SUPERSEDED:
                raise
