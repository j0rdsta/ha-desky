"""Write frames to the desk one at a time, and send timed sequences of them."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
import contextlib
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

# How long a cancelled write is waited for. A write with response takes about
# 70-130 ms through a Bluetooth proxy; one still running after this has hung.
WRITE_SETTLE_SECONDS = 2.0


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


class _Kind(Enum):
    """What a sequence sends."""

    SETTING = "setting"  # settings, limits and queries
    MOTION = "motion"  # movement and stop frames, each acknowledged
    REPEAT = "repeat"  # a held movement frame, repeated without response


@dataclass(eq=False, slots=True)
class _Sequence:
    """A timed sequence being sent, and why it was cancelled, if it was."""

    task: asyncio.Task[None]
    kind: _Kind
    cancelled_by: _Cancel | None = None

    def cancel(self, reason: _Cancel) -> None:
        """Cancel the sequence; a disconnect outranks being superseded."""
        if self.cancelled_by is not _Cancel.DISCONNECTED:
            self.cancelled_by = reason
        self.task.cancel(reason.value)


class Sequencer:
    """Write frames to the desk one at a time, and send timed sequences of them.

    A pause never holds the write lock, so a stop is never held up behind a
    sequence. A radio write is never interrupted: a cancel waits for it. The
    movement or stop frames still due are one motion sequence, which the next
    one replaces. Every write waits for the desk's acknowledgement, except a
    repeat's: write_frame(frame, response) is told which.
    """

    def __init__(
        self,
        write_frame: Callable[[bytes, bool], Awaitable[None]],
        clock: Clock | None = None,
    ) -> None:
        """Write each frame with write_frame, timing sequences on the clock."""
        self._write_frame = write_frame
        self._clock = clock or Clock()
        # Frames go out one at a time, so concurrent callers never interleave
        self._lock = asyncio.Lock()
        self._running: dict[asyncio.Task[None], _Sequence] = {}
        self._motion: _Sequence | None = None

    def now(self) -> float:
        """Return the time on the sequencer's clock, in seconds."""
        return self._clock.time()

    @property
    def idle(self) -> bool:
        """Return if no sequence is being sent."""
        return not self._running

    @property
    def repeating(self) -> bool:
        """Return if a movement frame is being repeated."""
        return self._motion is not None and self._motion.kind is _Kind.REPEAT

    async def write(self, *frames: bytes, response: bool = True) -> None:
        """Write frames in order, with no other write in between.

        The lock is held only for the writes, never during a sequence's pauses.
        A cancel waits for the frame on the air, then skips the rest. Without
        response, a write returns once the frame is queued, without waiting
        for the desk's acknowledgement.
        """
        async with self._lock:
            for frame in frames:
                await self._write_whole(frame, response)

    async def _write_whole(self, frame: bytes, response: bool) -> None:
        """Write a frame to its end, even when cancelled, then pass a cancel on.

        The desk's Bluetooth stack rejects a write while another is in progress
        (BlueZ: InProgress), so a write is not abandoned halfway: the write
        lock is released only once the radio is free. A cancelled write still
        running after WRITE_SETTLE_SECONDS has hung, as its link is being
        closed, and is given up. A write that fails after its caller was
        cancelled ends in the cancel; its error no longer matters.
        """
        pending = asyncio.ensure_future(self._write_frame(frame, response))
        try:
            # Unlike awaiting it, waiting does not pass a cancel on to the write
            await asyncio.wait([pending])
        except asyncio.CancelledError:
            settled = asyncio.ensure_future(self._clock.sleep(WRITE_SETTLE_SECONDS))
            try:
                while not (pending.done() or settled.done()):
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.wait(
                            [pending, settled], return_when=asyncio.FIRST_COMPLETED
                        )
            finally:
                settled.cancel()
            if not pending.done():
                pending.cancel()
            elif not pending.cancelled():
                pending.exception()  # retrieved, so it is not reported as unhandled
            raise
        pending.result()

    async def run_setting(self, steps: Iterable[Step]) -> None:
        """Send a sequence and wait for it to finish.

        A stop or a movement command does not cancel it. A disconnect does, and
        raises DeskNotConnectedError.
        """
        await self._wait(self._start(steps, _Kind.SETTING))

    async def run_motion(self, steps: Iterable[Step]) -> None:
        """Send movement or stop frames in place of those still due, and wait.

        Cut short by a stop or a new movement command, it returns quietly. Cut
        short by a disconnect, it raises DeskNotConnectedError.
        """
        await self._wait(self._start_motion(steps, _Kind.MOTION))

    def start_repeat(self, steps: Iterable[Step]) -> None:
        """Repeat a movement frame in the background, in place of those still due.

        The desk moves only while the frame keeps coming evenly, so a repeat is
        written without response: waiting for each acknowledgement through a
        Bluetooth proxy (70-700 ms) makes the stream uneven, and the desk then
        takes the button as released. A failed write ends the repeat, and is
        only logged.
        """
        self._start_motion(steps, _Kind.REPEAT)

    async def wait_for(self, done: asyncio.Future[None], seconds: float) -> bool:
        """Wait on the sequencer's clock until done completes or seconds pass.

        Return if it completed. The write lock is not held while waiting.
        """
        if not done.done():
            timer = asyncio.ensure_future(self._clock.sleep(seconds))
            try:
                await asyncio.wait([done, timer], return_when=asyncio.FIRST_COMPLETED)
            finally:
                timer.cancel()
        return done.done()

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

    def _start(self, steps: Iterable[Step], kind: _Kind) -> _Sequence:
        """Start sending a sequence in the background."""
        task = asyncio.create_task(self._send(steps, kind is not _Kind.REPEAT))
        sequence = self._running[task] = _Sequence(task, kind)
        task.add_done_callback(self._done)
        return sequence

    def _start_motion(self, steps: Iterable[Step], kind: _Kind) -> _Sequence:
        """Start a motion sequence, cancelling the one it replaces."""
        self.cancel_motion()
        sequence = self._motion = self._start(steps, kind)
        return sequence

    def _done(self, task: asyncio.Task[None]) -> None:
        """Forget a finished sequence; a failure was already raised or is logged."""
        sequence = self._running.pop(task)
        if self._motion is sequence:
            self._motion = None
        if not task.cancelled() and (err := task.exception()) is not None:
            _LOGGER.debug("Timed command sequence ended: %s", err)

    async def _send(self, steps: Iterable[Step], response: bool) -> None:
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
            await self.write(*(frame for _, frame in group), response=response)

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
