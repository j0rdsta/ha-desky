"""Test the desk's command timing, which follows the official Desky app."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import time
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_STOP_COVER
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    LIMIT_LOWER_RESPONSE_HEADER,
    LIMIT_STATUS_RESPONSE_HEADER,
    LIMIT_UPPER_RESPONSE_HEADER,
    UNIT_RESPONSE_HEADER,
    HeightLimit,
)

from . import FakeClock, deliver_frame, desk_response, record_frames

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


# Settings


LOCKED = "f1f1b20101b47e"
VIBRATION_OFF = "f1f1b30100b47e"


@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        # Lock, vibration and lighting: the set at 200 and 400 ms
        ("set_lock_status", (True,), [(0.0, H), (0.2, LOCKED), (0.4, LOCKED)]),
        (
            "set_vibration",
            (False,),
            [(0.0, H), (0.2, VIBRATION_OFF), (0.4, VIBRATION_OFF)],
        ),
        (
            "set_lighting",
            (True,),
            [(0.0, H), (0.2, "f1f1b50101b77e"), (0.4, "f1f1b50101b77e")],
        ),
        # Sensitivity and touch mode: the set once at 500 ms
        ("set_sensitivity", (2,), [(0.0, H), (0.5, "f1f11d0102207e")]),
        ("set_touch_mode", (1,), [(0.0, H), (0.5, "f1f11901011b7e")]),
        # Colour and brightness: twice, 100 ms apart
        (
            "set_light_color",
            (2,),
            [(0.0, H), (0.0, "f1f1b40102b77e"), (0.1, "f1f1b40102b77e")],
        ),
        (
            "set_brightness",
            (75,),
            [(0.0, H), (0.0, "f1f1b6014b027e"), (0.1, "f1f1b6014b027e")],
        ),
        # Unit: three times, 100 ms apart
        (
            "set_unit",
            ("in",),
            [
                (0.0, H),
                (0.0, "f1f10e0101107e"),
                (0.1, "f1f10e0101107e"),
                (0.2, "f1f10e0101107e"),
            ],
        ),
        # Clearing the limits: twice, 200 ms apart
        ("clear_height_limits", (), [(0.0, H), (0.0, CLEAR), (0.2, CLEAR)]),
    ],
)
async def test_settings_follow_the_app_timing(
    desk: DeskBLEDevice,
    frames: Frames,
    method: str,
    args: tuple[Any, ...],
    expected: Frames,
) -> None:
    """Each setting goes out with the official app's repeats and spacing."""
    await getattr(desk, method)(*args)

    assert frames == expected


async def test_settings_sent_together_both_complete(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """Two settings changed at once both reach the desk; neither cancels the other."""
    clock.auto = False
    lock = asyncio.create_task(desk.set_lock_status(True))
    vibration = asyncio.create_task(desk.set_vibration(False))
    await clock.advance(1.0)
    await asyncio.gather(lock, vibration)

    assert frames == [
        (0.0, H),
        (0.0, H),
        (0.2, LOCKED),
        (0.2, VIBRATION_OFF),
        (0.4, LOCKED),
        (0.4, VIBRATION_OFF),
    ]


async def test_settings_read_back_half_a_second_after_sensitivity(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """As in the app, the settings are asked for 500 ms after the sensitivity set."""
    await desk.set_sensitivity(3)
    await desk.get_settings()

    assert frames == [
        (0.0, H),
        (0.5, "f1f11d0103217e"),
        (1.0, H),
        (1.0, STATUS),
    ]


# Height limits


@pytest.mark.parametrize(
    ("limit_status", "limit", "height", "expected"),
    [
        # Both set: clear twice, then upper and lower twice each, 50 ms apart
        (
            0x11,
            HeightLimit.UPPER,
            120.0,
            [
                (0.0, H),
                (0.0, CLEAR),
                (0.05, CLEAR),
                (0.1, UPPER_120),
                (0.15, UPPER_120),
                (0.2, LOWER_65),
                (0.25, LOWER_65),
            ],
        ),
        # None set: clear twice, then the new limit twice
        (
            0x00,
            HeightLimit.LOWER,
            65.0,
            [(0.0, H), (0.0, CLEAR), (0.05, CLEAR), (0.1, LOWER_65), (0.15, LOWER_65)],
        ),
        # Limits not reported yet: nothing is cleared that might be set
        (
            None,
            HeightLimit.UPPER,
            120.0,
            [(0.0, H), (0.0, UPPER_120), (0.05, UPPER_120)],
        ),
    ],
)
async def test_setting_a_limit_sends_the_other_again(
    desk: DeskBLEDevice,
    frames: Frames,
    limit_status: int | None,
    limit: HeightLimit,
    height: float,
    expected: Frames,
) -> None:
    """The app clears the limits and sets both, so the other limit is kept."""
    desk._handle_notification(None, bytearray.fromhex("f2f20e01000f7e"))  # cm
    if limit_status is not None:
        status = bytearray(
            [0xF2, 0xF2, 0x20, 0x01, limit_status, (0x21 + limit_status) & 0xFF, 0x7E]
        )
        desk._handle_notification(None, status)
        desk._handle_notification(None, bytearray.fromhex("f2f2210204b0d97e"))  # 120
        desk._handle_notification(None, bytearray.fromhex("f2f22202028ab07e"))  # 65
    frames.clear()

    await desk.set_height_limit(limit, height)

    assert frames == expected


async def test_limit_sent_again_uses_the_display_unit(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """While the desk shows inches, the limit sent again is in inches too."""
    for frame in (
        "f2f20e0101107e",  # inches
        "f2f2200111327e",  # both limits set
        "f2f2210201b8dc7e",  # upper 44.0 in
        "f2f2220201183d7e",  # lower 28.0 in
    ):
        desk._handle_notification(None, bytearray.fromhex(frame))
    frames.clear()

    await desk.set_height_limit(HeightLimit.UPPER, 120.0)

    upper = desk._create_command_with_word_param(0x21, 470).hex()  # a whole 47 in
    lower = desk._create_command_with_word_param(0x22, 280).hex()  # 28.0 in
    assert [frame for _, frame in frames[3:]] == [upper, upper, lower, lower]


def _report_limits(desk: DeskBLEDevice, upper: int | None, lower: int | None) -> None:
    """Have a cm desk report its limit status and limits, in tenths of a cm."""
    desk._handle_notification(None, desk_response(UNIT_RESPONSE_HEADER, 0x00))
    status = (0x01 if upper is not None else 0) | (0x10 if lower is not None else 0)
    desk._handle_notification(None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, status))
    if upper is not None:
        desk._handle_notification(
            None, desk_response(LIMIT_UPPER_RESPONSE_HEADER, upper >> 8, upper & 0xFF)
        )
    if lower is not None:
        desk._handle_notification(
            None, desk_response(LIMIT_LOWER_RESPONSE_HEADER, lower >> 8, lower & 0xFF)
        )


@pytest.mark.parametrize(
    ("limit", "height", "upper", "lower"),
    [
        # Upper 110 to 124, lower 65 kept
        (HeightLimit.UPPER, 124.0, "f1f1210204d8ff7e", LOWER_65),
        # Lower 65 to 62, upper 110 kept
        (HeightLimit.LOWER, 62.0, "f1f12102044c737e", "f1f12202026c927e"),
    ],
)
async def test_loosening_a_limit_clears_it_first(
    desk: DeskBLEDevice,
    frames: Frames,
    limit: HeightLimit,
    height: float,
    upper: str,
    lower: str,
) -> None:
    """The desk ignores a looser limit while one is set, so both are cleared first."""
    _report_limits(desk, upper=1100, lower=650)
    frames.clear()

    await desk.set_height_limit(limit, height)

    assert frames == [
        (0.0, H),
        (0.0, CLEAR),
        (0.05, CLEAR),
        (0.1, upper),
        (0.15, upper),
        (0.2, lower),
        (0.25, lower),
    ]


async def test_limit_not_cleared_while_the_other_is_unread(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """A set limit whose value has not arrived yet is not cleared, so it is kept."""
    _report_limits(desk, upper=1100, lower=None)
    desk._handle_notification(None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, 0x11))
    frames.clear()

    await desk.set_height_limit(HeightLimit.UPPER, 120.0)

    assert frames == [(0.0, H), (0.0, UPPER_120), (0.05, UPPER_120)]


# Stop and move to height


async def test_stop_is_sent_twice(desk: DeskBLEDevice, frames: Frames) -> None:
    """Stop goes out twice, 50 ms apart, without waking the desk."""
    await desk.stop()

    assert frames == [(0.0, STOP), (0.05, STOP)]


async def test_move_to_height_follows_the_app_timing(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """Move to height wakes the desk, stops it, then sends the target twice."""
    await desk.move_to_height(85.0)

    assert frames == [(0.0, H), (0.0, STOP), (0.2, TO_85_CM), (0.3, TO_85_CM)]


async def test_stop_cuts_into_a_move_to_height(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A stop during the pause goes out at once, and the target never follows."""
    clock.auto = False
    move = asyncio.create_task(desk.move_to_height(85.0))
    await clock.advance(0.1)

    await _run(clock, desk.stop())

    await move  # cut short quietly
    assert frames == [(0.0, H), (0.0, STOP), (0.1, STOP), (0.15, STOP)]
    assert desk._movement is None


async def test_new_command_cuts_into_a_move_to_height(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A new movement command cancels what a move to height still has to send."""
    clock.auto = False
    move = asyncio.create_task(desk.move_to_height(85.0))
    await clock.advance(0.1)

    await desk.move_down()
    await clock.advance(1.0)

    await move
    assert frames == [(0.0, H), (0.0, STOP), (0.1, H), (0.1, DOWN)]
    assert desk.movement_direction == "down"


async def test_stop_does_not_wait_for_a_setting(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A stop goes out during a setting's pause, and the setting still completes."""
    clock.auto = False
    lock = asyncio.create_task(desk.set_lock_status(True))
    await clock.advance(0.1)

    await _run(clock, desk.stop())

    await lock
    assert frames == [
        (0.0, H),
        (0.1, STOP),
        (0.15, STOP),
        (0.2, LOCKED),
        (0.4, LOCKED),
    ]


async def test_disconnect_during_a_move_to_height(
    desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
) -> None:
    """A move to height cut short by a disconnect fails and sends nothing more."""
    clock.auto = False
    move = asyncio.create_task(desk.move_to_height(85.0))
    await clock.advance(0.1)

    mock_bleak_client.is_connected = False
    desk._handle_disconnect(mock_bleak_client)
    with pytest.raises(DeskNotConnectedError):
        await move
    await clock.advance(1.0)

    assert frames == [(0.0, H), (0.0, STOP)]
    assert desk._movement is None


# Hold-repeat in press-and-hold touch mode


@pytest.fixture
def held_desk(desk: DeskBLEDevice, clock: FakeClock) -> DeskBLEDevice:
    """Return the desk in press-and-hold touch mode, with pauses held."""
    clock.auto = False
    desk._handle_notification(None, PRESS_AND_HOLD)
    return desk


MOVEMENTS = [
    ("move_up", (), UP),
    ("move_down", (), DOWN),
    ("move_to_preset", (2,), PRESET_2),
]


@pytest.mark.parametrize("touch_mode", [None, ONE_PRESS])
@pytest.mark.parametrize(("method", "args", "frame"), MOVEMENTS)
async def test_one_frame_unless_press_and_hold(
    desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    touch_mode: bytearray | None,
    method: str,
    args: tuple[Any, ...],
    frame: str,
) -> None:
    """In one-press mode, or while the touch mode is unknown, one frame is sent."""
    clock.auto = False
    if touch_mode is not None:
        desk._handle_notification(None, touch_mode)

    await getattr(desk, method)(*args)
    await clock.advance(2.0)

    assert frames == [(0.0, H), (0.0, frame)]


@pytest.mark.parametrize(("method", "args", "frame"), MOVEMENTS)
async def test_press_and_hold_repeats_until_stop(
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    method: str,
    args: tuple[Any, ...],
    frame: str,
) -> None:
    """In press-and-hold mode the frame repeats every 100 ms until a stop."""
    await getattr(held_desk, method)(*args)
    await clock.advance(0.35)

    await _run(clock, held_desk.stop())

    assert frames == [
        (0.0, H),
        (0.0, frame),
        (0.1, frame),
        (0.2, frame),
        (0.3, frame),
        (0.35, STOP),
        (0.4, STOP),
    ]
    assert not held_desk._sequences


@patch("time.time")
@pytest.mark.parametrize(
    ("method", "args", "frame"),
    [("move_up", (), UP), ("move_to_preset", (2,), PRESET_2)],
)
async def test_press_and_hold_ends_when_the_desk_stops(
    mock_time: MagicMock,
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    method: str,
    args: tuple[Any, ...],
    frame: str,
) -> None:
    """The repeat ends once the height is unchanged for three readings."""
    mock_time.return_value = 0.0
    await getattr(held_desk, method)(*args)
    readings = [(0.5, 82.0), (1.0, 90.0), (1.5, 95.0), (2.0, 95.0), (2.5, 95.0)]
    for when, height in readings:
        await clock.advance(0.5)
        mock_time.return_value = when
        held_desk._handle_notification(None, _status_frame(height))
    assert held_desk._movement is not None  # two unchanged readings so far

    await clock.advance(0.5)
    mock_time.return_value = 3.0
    held_desk._handle_notification(None, _status_frame(95.0))  # the third
    sent = len(frames)
    await clock.advance(2.0)

    assert held_desk._movement is None
    assert len(frames) == sent
    assert frames[-1] == (3.0, frame)
    assert not held_desk._sequences


@patch("time.time")
async def test_press_and_hold_ends_on_a_bounce(
    mock_time: MagicMock,
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
) -> None:
    """A collision bounce ends the movement, so the frame stops repeating."""
    mock_time.return_value = 0.0
    await held_desk.move_down()
    for when, height in [(0.5, 78.0), (1.0, 76.0), (1.2, 77.0)]:  # back up 1 cm
        await clock.advance(0.2)
        mock_time.return_value = when
        held_desk._handle_notification(None, _status_frame(height))
    sent = len(frames)
    await clock.advance(2.0)

    assert held_desk.collision_detected is True
    assert len(frames) == sent
    held_desk._set_collision_detected(False)  # cancel the auto-clear


@patch("time.time")
async def test_press_and_hold_ends_when_the_desk_never_moves(
    mock_time: MagicMock,
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
) -> None:
    """A desk that does not move within the expiry time stops getting the frame."""
    mock_time.return_value = 0.0
    await held_desk.move_up()
    await clock.advance(1.0)
    mock_time.return_value = 6.0  # past the five-second expiry
    held_desk._handle_notification(None, _status_frame(80.0))
    sent = len(frames)
    await clock.advance(2.0)

    assert held_desk._movement is None
    assert len(frames) == sent


async def test_press_and_hold_stops_at_sixty_seconds(
    held_desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """The repeat never runs longer than 60 seconds."""
    await held_desk.move_up()
    await clock.advance(70.0)

    repeats = [at for at, frame in frames if frame == UP]
    assert len(repeats) == 601  # the first frame, then 600 repeats
    assert repeats[-1] == 60.0
    assert not held_desk._sequences


async def test_press_and_hold_ends_on_disconnect(
    held_desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
) -> None:
    """A disconnect cancels the repeat before its next write."""
    await held_desk.move_up()
    await clock.advance(0.25)
    sent = mock_bleak_client.write_gatt_char.await_count

    await held_desk.disconnect()
    await clock.advance(2.0)

    assert mock_bleak_client.write_gatt_char.await_count == sent
    assert not held_desk._sequences


async def test_new_command_replaces_the_repeat(
    held_desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A new movement command repeats its own frame instead."""
    await held_desk.move_up()
    await clock.advance(0.15)

    await held_desk.move_down()
    await clock.advance(0.25)
    await _run(clock, held_desk.stop())

    assert frames == [
        (0.0, H),
        (0.0, UP),
        (0.1, UP),
        (0.15, H),
        (0.15, DOWN),
        (0.25, DOWN),
        (0.35, DOWN),
        (0.4, STOP),
        (0.45, STOP),
    ]


async def test_move_to_height_is_not_held(
    held_desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A move to height is sent as in the app, even in press-and-hold mode."""
    await _run(clock, held_desk.move_to_height(85.0), 2.0)

    assert frames == [(0.0, H), (0.0, STOP), (0.2, TO_85_CM), (0.3, TO_85_CM)]


async def test_failed_repeat_ends_quietly(
    held_desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A repeat whose write fails ends, and the failure is only logged at debug."""
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.bluetooth")
    # The handshake and the first frame go out; the first repeat fails
    mock_bleak_client.write_gatt_char.side_effect = [None, None, Exception("busy")]

    await held_desk.move_up()
    await clock.advance(0.5)

    assert mock_bleak_client.write_gatt_char.await_count == 3
    assert "Timed command sequence ended: busy" in caplog.text
    assert not held_desk._sequences


async def test_movement_ended_during_its_first_frame_is_not_held(
    held_desk: DeskBLEDevice, clock: FakeClock, mock_bleak_client: MagicMock
) -> None:
    """A movement that ends while its first frame goes out does not repeat."""

    async def _write(_uuid: str, data: bytes) -> None:
        held_desk._end_movement()  # as a bounce reported meanwhile would

    mock_bleak_client.write_gatt_char.side_effect = _write

    await held_desk.move_up()
    await clock.advance(1.0)

    assert mock_bleak_client.write_gatt_char.await_count == 2  # handshake, frame
    assert not held_desk._sequences


async def test_preset_button_repeats_in_press_and_hold_mode(
    hass: HomeAssistant, desk_client: MagicMock, clock: FakeClock
) -> None:
    """Pressing Preset 2 in press-and-hold mode repeats it until the cover stops."""
    clock.auto = False
    deliver_frame(desk_client, PRESS_AND_HOLD)
    frames = record_frames(desk_client, clock)

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_preset_2"},
        blocking=True,
    )
    await clock.advance(0.25)
    stop = hass.async_create_task(
        hass.services.async_call(
            COVER_DOMAIN,
            SERVICE_STOP_COVER,
            {ATTR_ENTITY_ID: "cover.desky_desk"},
            blocking=True,
        )
    )
    await clock.advance(1.0)
    await stop

    start = frames[0][0]
    assert [(round(at - start, 3), frame) for at, frame in frames] == [
        (0.0, H),
        (0.0, PRESET_2),
        (0.1, PRESET_2),
        (0.2, PRESET_2),
        (0.25, STOP),
        (0.3, STOP),
    ]


async def test_unload_ends_a_held_movement(
    hass: HomeAssistant,
    desk_client: MagicMock,
    mock_config_entry: MockConfigEntry,
    clock: FakeClock,
) -> None:
    """Unloading the entry cancels a hold-repeat; nothing is written afterwards."""
    clock.auto = False
    deliver_frame(desk_client, PRESS_AND_HOLD)
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_move_up"},
        blocking=True,
    )
    await clock.advance(0.25)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    sent = desk_client.write_gatt_char.await_count
    await clock.advance(2.0)

    assert desk_client.write_gatt_char.await_count == sent
