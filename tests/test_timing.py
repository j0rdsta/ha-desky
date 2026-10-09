"""Test the desk's command timing, which follows the official Desky app."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.desky_desk.bluetooth import (
    Clock,
    DeskBLEDevice,
    DeskCommandError,
    DeskNotConnectedError,
)
from custom_components.desky_desk.const import (
    COMMAND_CLEAR_LIMITS,
    COMMAND_GET_STATUS,
    COMMAND_HANDSHAKE,
    COMMAND_MEMORY_2,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
)

from . import FakeClock, record_frames

H = COMMAND_HANDSHAKE.hex()
STATUS = COMMAND_GET_STATUS.hex()
STOP = COMMAND_STOP.hex()
UP = COMMAND_MOVE_UP.hex()
DOWN = COMMAND_MOVE_DOWN.hex()
PRESET_2 = COMMAND_MEMORY_2.hex()
CLEAR = COMMAND_CLEAR_LIMITS.hex()
TO_85_CM = "f1f11b020352727e"  # 850 mm
UPPER_120 = "f1f1210204b0d77e"
LOWER_65 = "f1f12202028ab07e"
PRESS_AND_HOLD = bytearray.fromhex("f2f21901011b7e")
ONE_PRESS = bytearray.fromhex("f2f21901001a7e")

Frames = list[tuple[float, str]]


def _status_frame(height_cm: float) -> bytearray:
    """Build a status frame (f2 f2 01 03 HH LL 07 CS 7e) for a height in cm."""
    raw = round(height_cm * 10)
    body = [0x01, 0x03, raw >> 8, raw & 0xFF, 0x07]
    return bytearray([0xF2, 0xF2, *body, sum(body) & 0xFF, 0x7E])


async def _run(
    clock: FakeClock, command: Coroutine[Any, Any, None], seconds: float = 1.0
) -> None:
    """Run a command while the clock moves on past its pauses."""
    task = asyncio.create_task(command)
    await clock.advance(seconds)
    await task


@pytest.fixture
def desk(mock_ble_device: MagicMock, mock_bleak_client: MagicMock) -> DeskBLEDevice:
    """Return a connected desk at 80 cm."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 80.0
    return device


@pytest.fixture
def frames(mock_bleak_client: MagicMock, clock: FakeClock) -> Frames:
    """Record every frame the desk is sent, with its virtual time."""
    return record_frames(mock_bleak_client, clock)


# The sequence runner


async def test_clock_uses_monotonic_time_and_asyncio_sleep() -> None:
    """The real clock reads monotonic time and pauses with asyncio."""
    clock = Clock()
    before = time.monotonic()

    await clock.sleep(0)

    assert before <= clock.time() <= time.monotonic()


async def test_sequence_writes_each_frame_at_its_time(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """Frames go out at their times; frames due together go out back to back."""
    clock.auto = False
    steps = [
        (0.0, COMMAND_HANDSHAKE),
        (0.0, COMMAND_GET_STATUS),
        (0.25, COMMAND_STOP),
        (0.5, COMMAND_STOP),
    ]

    await _run(clock, desk._run_sequence(steps))

    assert frames == [(0.0, H), (0.0, STATUS), (0.25, STOP), (0.5, STOP)]
    assert not desk._sequences


async def test_late_frames_are_not_sent_in_a_burst(
    desk: DeskBLEDevice, clock: FakeClock, mock_bleak_client: MagicMock
) -> None:
    """After a slow write the rest of the sequence moves back, keeping its spacing."""
    clock.auto = False
    times: list[float] = []

    async def _write(_uuid: str, data: bytes) -> None:
        times.append(round(clock.now, 3))
        if len(times) == 2:
            clock.now += 0.35  # the second write takes 350 ms

    mock_bleak_client.write_gatt_char.side_effect = _write

    await _run(clock, desk._run_sequence([(n * 0.1, COMMAND_STOP) for n in range(5)]))

    assert times == [0.0, 0.1, 0.45, 0.55, 0.65]


async def test_pause_does_not_hold_the_write_lock(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """Another command goes out during a sequence's pause, not after it."""
    clock.auto = False
    sequence = asyncio.create_task(
        desk._run_sequence([(0.0, COMMAND_HANDSHAKE), (0.5, COMMAND_GET_STATUS)])
    )
    await clock.advance(0.1)

    await desk.get_status()
    await clock.advance(1.0)
    await sequence

    assert frames == [(0.0, H), (0.1, STATUS), (0.5, STATUS)]


async def test_cancelled_motion_sequence_returns_quietly(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A motion sequence cut short by the next command ends without an error."""
    clock.auto = False
    sequence = asyncio.create_task(
        desk._run_sequence([(0.0, COMMAND_STOP), (0.5, COMMAND_STOP)], motion=True)
    )
    await clock.advance(0.1)

    desk._cancel_motion()
    await clock.advance(1.0)

    await sequence
    assert frames == [(0.0, STOP)]
    assert not desk._sequences


@pytest.mark.parametrize("motion", [False, True])
async def test_disconnect_cancels_a_sequence(
    desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    motion: bool,
) -> None:
    """A disconnect mid-sequence cancels it: no write is tried, and the caller hears."""
    clock.auto = False
    sequence = asyncio.create_task(
        desk._run_sequence(
            [(0.0, COMMAND_HANDSHAKE), (0.5, COMMAND_GET_STATUS)], motion=motion
        )
    )
    await clock.advance(0.1)

    mock_bleak_client.is_connected = False
    desk._handle_disconnect(mock_bleak_client)
    with pytest.raises(DeskNotConnectedError):
        await sequence
    await clock.advance(1.0)

    assert frames == [(0.0, H)]
    assert mock_bleak_client.write_gatt_char.await_count == 1
    assert not desk._sequences


async def test_cancelled_caller_cancels_its_sequence(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """Cancelling the caller, as an unload does, cancels its sequence too."""
    clock.auto = False
    sequence = asyncio.create_task(
        desk._run_sequence([(0.0, COMMAND_HANDSHAKE), (0.5, COMMAND_GET_STATUS)])
    )
    await clock.advance(0.1)

    sequence.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sequence
    await clock.advance(1.0)

    assert frames == [(0.0, H)]
    assert not desk._sequences


async def test_failed_write_ends_the_sequence(
    desk: DeskBLEDevice, mock_bleak_client: MagicMock
) -> None:
    """A write that fails after the first frame still reaches the caller."""
    mock_bleak_client.write_gatt_char.side_effect = [None, Exception("busy")]

    with pytest.raises(DeskCommandError, match="busy"):
        await desk._run_sequence(
            [(0.0, COMMAND_HANDSHAKE), (0.1, COMMAND_STOP), (0.2, COMMAND_STOP)]
        )

    assert mock_bleak_client.write_gatt_char.await_count == 2
