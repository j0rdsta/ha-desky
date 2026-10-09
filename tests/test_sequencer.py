"""Test the sequencer, which writes the desk's frames and times sequences of them."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import time
from typing import Any

import pytest

from custom_components.desky_desk.errors import DeskCommandError, DeskNotConnectedError
from custom_components.desky_desk.sequencer import Clock, Sequencer

from . import FakeClock

A = b"a"
B = b"b"
C = b"c"

Frames = list[tuple[float, bytes]]


class Desk:
    """A desk's write path that records each frame with its virtual time."""

    def __init__(self, clock: FakeClock) -> None:
        """Record frames on the clock; nothing fails until told to."""
        self.clock = clock
        self.frames: Frames = []
        self.fail: dict[int, Exception] = {}

    async def write_frame(self, frame: bytes, response: bool = True) -> None:
        """Record the frame, or fail it if this write is set to fail."""
        if (err := self.fail.get(len(self.frames))) is not None:
            self.frames.append((round(self.clock.now, 3), frame))
            raise err
        self.frames.append((round(self.clock.now, 3), frame))


@pytest.fixture
def desk() -> Desk:
    """Return a desk write path on a clock that holds each pause."""
    clock = FakeClock()
    clock.auto = False
    return Desk(clock)


@pytest.fixture
def sequencer(desk: Desk) -> Sequencer:
    """Return a sequencer writing to the desk."""
    return Sequencer(desk.write_frame, desk.clock)


async def _run(
    clock: FakeClock, command: Coroutine[Any, Any, None], seconds: float = 1.0
) -> None:
    """Run a command while the clock moves on past its pauses."""
    task = asyncio.create_task(command)
    await clock.advance(seconds)
    await task


async def test_clock_uses_monotonic_time_and_asyncio_sleep() -> None:
    """The real clock reads monotonic time and pauses with asyncio."""
    clock = Clock()
    before = time.monotonic()

    await clock.sleep(0)

    assert before <= clock.time() <= time.monotonic()


async def test_sequencer_uses_the_real_clock_by_default(desk: Desk) -> None:
    """Without a clock, the sequencer pauses in real time."""
    sequencer = Sequencer(desk.write_frame)

    await sequencer.run_setting([(0.0, A), (0.001, B)])

    assert [frame for _, frame in desk.frames] == [A, B]


async def test_sequence_writes_each_frame_at_its_time(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Frames go out at their times; frames due together go out back to back."""
    steps = [(0.0, A), (0.0, B), (0.25, C), (0.5, C)]

    await _run(desk.clock, sequencer.run_setting(steps))

    assert desk.frames == [(0.0, A), (0.0, B), (0.25, C), (0.5, C)]
    assert sequencer.idle


async def test_late_frames_are_not_sent_in_a_burst(
    sequencer: Sequencer, desk: Desk
) -> None:
    """After a slow write the rest of the sequence moves back, keeping its spacing."""
    times: list[float] = []

    async def _write(frame: bytes, response: bool = True) -> None:
        times.append(round(desk.clock.now, 3))
        if len(times) == 2:
            desk.clock.now += 0.35  # the second write takes 350 ms

    sequencer = Sequencer(_write, desk.clock)

    await _run(desk.clock, sequencer.run_setting([(n * 0.1, A) for n in range(5)]))

    assert times == [0.0, 0.1, 0.45, 0.55, 0.65]


async def test_pause_does_not_hold_the_write_lock(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Another write goes out during a sequence's pause, not after it."""
    sequence = asyncio.create_task(sequencer.run_setting([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    await sequencer.write(C)
    await desk.clock.advance(1.0)
    await sequence

    assert desk.frames == [(0.0, A), (0.1, C), (0.5, B)]


async def test_superseded_motion_returns_quietly(
    sequencer: Sequencer, desk: Desk
) -> None:
    """A motion sequence cut short by the next one ends without an error."""
    first = asyncio.create_task(sequencer.run_motion([(0.0, A), (0.5, A)]))
    await desk.clock.advance(0.1)

    await _run(desk.clock, sequencer.run_motion([(0.0, B)]))

    await first
    assert desk.frames == [(0.0, A), (0.1, B)]
    assert sequencer.idle


async def test_cancelled_motion_returns_quietly(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Cancelling the motion frames still due ends their caller without an error."""
    sequence = asyncio.create_task(sequencer.run_motion([(0.0, A), (0.5, A)]))
    await desk.clock.advance(0.1)

    sequencer.cancel_motion()
    await desk.clock.advance(1.0)

    await sequence
    assert desk.frames == [(0.0, A)]
    assert sequencer.idle


async def test_cancelling_motion_leaves_a_setting(
    sequencer: Sequencer, desk: Desk
) -> None:
    """A stop or a new movement does not cancel a setting being sent."""
    setting = asyncio.create_task(sequencer.run_setting([(0.0, A), (0.5, A)]))
    await desk.clock.advance(0.1)

    sequencer.cancel_motion()
    await desk.clock.advance(1.0)

    await setting
    assert desk.frames == [(0.0, A), (0.5, A)]


@pytest.mark.parametrize("motion", [False, True])
async def test_disconnect_cancels_a_sequence(
    sequencer: Sequencer, desk: Desk, motion: bool
) -> None:
    """A disconnect mid-sequence cancels it, and its caller hears."""
    run = sequencer.run_motion if motion else sequencer.run_setting
    sequence = asyncio.create_task(run([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    sequencer.cancel_all()
    with pytest.raises(DeskNotConnectedError):
        await sequence
    await desk.clock.advance(1.0)

    assert desk.frames == [(0.0, A)]
    assert sequencer.idle


async def test_disconnect_outranks_a_superseded_motion(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Motion cancelled by a stop and then by a disconnect reports the disconnect."""
    sequence = asyncio.create_task(sequencer.run_motion([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    sequencer.cancel_motion()
    sequencer.cancel_all()
    with pytest.raises(DeskNotConnectedError):
        await sequence


async def test_wait_cancelled_waits_for_every_sequence(
    sequencer: Sequencer, desk: Desk
) -> None:
    """After a disconnect, waiting returns once no sequence is left."""
    sequencer.start_repeat([(0.0, A), (0.5, B)])
    setting = asyncio.create_task(sequencer.run_setting([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    sequencer.cancel_all()
    await sequencer.wait_cancelled()

    assert sequencer.idle
    with pytest.raises(DeskNotConnectedError):
        await setting


async def test_cancelled_caller_cancels_its_sequence(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Cancelling the caller, as an unload does, cancels its sequence too."""
    sequence = asyncio.create_task(sequencer.run_setting([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    sequence.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sequence
    await desk.clock.advance(1.0)

    assert desk.frames == [(0.0, A)]
    assert sequencer.idle


async def test_failed_write_ends_the_sequence(sequencer: Sequencer, desk: Desk) -> None:
    """A write that fails after the first frame reaches the caller."""
    desk.fail[1] = DeskCommandError("busy")

    with pytest.raises(DeskCommandError, match="busy"):
        await _run(desk.clock, sequencer.run_setting([(0.0, A), (0.1, B), (0.2, C)]))

    assert desk.frames == [(0.0, A), (0.1, B)]


async def test_failed_background_motion_is_logged(
    sequencer: Sequencer, desk: Desk, caplog: pytest.LogCaptureFixture
) -> None:
    """Background movement frames whose write fails end, and it is logged at debug."""
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.sequencer")
    desk.fail[1] = DeskCommandError("busy")

    sequencer.start_repeat([(0.0, A), (0.1, A), (0.2, A)])
    await desk.clock.advance(1.0)

    assert desk.frames == [(0.0, A), (0.1, A)]
    assert "Timed command sequence ended: busy" in caplog.text
    assert sequencer.idle


async def test_sequence_cancelled_elsewhere_passes_the_cancel_on(
    sequencer: Sequencer, desk: Desk
) -> None:
    """A sequence cancelled for no reason of the sequencer's is not swallowed."""
    sequence = asyncio.create_task(sequencer.run_setting([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    next(iter(sequencer._running)).cancel()
    with pytest.raises(asyncio.CancelledError):
        await sequence


async def test_second_disconnect_keeps_the_reason(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Cancelling for a disconnect twice still reports the disconnect."""
    sequence = asyncio.create_task(sequencer.run_setting([(0.0, A), (0.5, B)]))
    await desk.clock.advance(0.1)

    sequencer.cancel_all()
    sequencer.cancel_all()
    with pytest.raises(DeskNotConnectedError):
        await sequence


async def test_cancel_waits_for_the_write_on_the_air(desk: Desk) -> None:
    """Movement cancelled mid-write finishes that write before the stop goes out.

    The radio rejects a write while another is still in progress, even when
    the caller of the first one was cancelled.
    """
    sent: Frames = []
    radio_free_at = 0.0

    async def _write(frame: bytes, response: bool = True) -> None:
        nonlocal radio_free_at
        if desk.clock.now < radio_free_at - 1e-9:
            raise DeskCommandError("InProgress")
        radio_free_at = desk.clock.now + 0.05  # each write takes 50 ms
        await desk.clock.sleep(0.05)
        sent.append((round(desk.clock.now, 3), frame))

    sequencer = Sequencer(_write, desk.clock)
    move = asyncio.create_task(sequencer.run_motion([(0.0, A), (0.1, A), (0.2, A)]))
    await desk.clock.advance(0.12)  # the second frame is on the air until 0.15

    await _run(desk.clock, sequencer.run_motion([(0.0, C), (0.05, C)]))

    await move
    assert sent == [(0.05, A), (0.15, A), (0.2, C), (0.25, C)]


async def test_cancelled_write_error_is_not_raised(desk: Desk) -> None:
    """A write that fails after its caller was cancelled ends in the cancel."""

    async def _write(frame: bytes, response: bool = True) -> None:
        await desk.clock.sleep(0.05)
        raise DeskCommandError("busy")

    sequencer = Sequencer(_write, desk.clock)
    write = asyncio.create_task(sequencer.write(A))
    await desk.clock.advance(0.01)

    write.cancel()
    await desk.clock.advance(0.01)
    write.cancel()  # a second cancel still waits for the radio
    await desk.clock.advance(1.0)

    with pytest.raises(asyncio.CancelledError):
        await write


async def test_hung_write_is_given_up_after_a_cancel(desk: Desk) -> None:
    """A cancelled write that never ends is waited for briefly, then given up."""
    started = asyncio.Event()
    finished = False

    async def _write(frame: bytes, response: bool = True) -> None:
        nonlocal finished
        if frame != A:
            return
        started.set()
        try:
            await asyncio.Event().wait()  # the link has hung
        finally:
            finished = True

    sequencer = Sequencer(_write, desk.clock)
    write = asyncio.create_task(sequencer.write(A))
    await started.wait()

    write.cancel()
    await desk.clock.advance(1.9)
    assert not write.done()  # still waiting for the radio
    await desk.clock.advance(0.1)
    with pytest.raises(asyncio.CancelledError):
        await write
    await asyncio.sleep(0)

    assert finished
    await sequencer.write(B)  # the lock is free again


async def test_write_cancelled_itself_after_a_cancel(desk: Desk) -> None:
    """A write that ends cancelled itself, as at shutdown, still ends the caller."""

    async def _write(frame: bytes, response: bool = True) -> None:
        await desk.clock.sleep(0.05)
        raise asyncio.CancelledError

    sequencer = Sequencer(_write, desk.clock)
    write = asyncio.create_task(sequencer.write(A))
    await desk.clock.advance(0.01)

    write.cancel()
    await desk.clock.advance(1.0)

    with pytest.raises(asyncio.CancelledError):
        await write


async def test_repeat_is_written_without_response_at_an_even_cadence(
    desk: Desk,
) -> None:
    """Repeats do not wait for acknowledgements, so a slow ack cannot space them out.

    A write with response here takes 350 ms; the repeats still go out every
    100 ms.
    """
    sent: list[tuple[float, bytes, bool]] = []

    async def _write(frame: bytes, response: bool = True) -> None:
        sent.append((round(desk.clock.now, 3), frame, response))
        if response:
            await desk.clock.sleep(0.35)

    sequencer = Sequencer(_write, desk.clock)
    sequencer.start_repeat([(n * 0.1, A) for n in range(1, 6)])
    assert sequencer.repeating
    await desk.clock.advance(1.0)

    assert sent == [(n / 10, A, False) for n in range(1, 6)]
    assert not sequencer.repeating
    assert sequencer.idle


async def test_motion_and_settings_wait_for_responses(
    sequencer: Sequencer, desk: Desk
) -> None:
    """Everything but a repeat waits for the desk's acknowledgement."""
    responses: list[bool] = []

    async def _write(frame: bytes, response: bool = True) -> None:
        responses.append(response)

    sequencer = Sequencer(_write, desk.clock)
    await _run(desk.clock, sequencer.run_motion([(0.0, A)]))
    await _run(desk.clock, sequencer.run_setting([(0.0, B)]))
    await sequencer.write(C)

    assert responses == [True, True, True]
    assert not sequencer.repeating
