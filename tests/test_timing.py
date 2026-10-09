"""Test the desk's command timing, which follows the official Desky app."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Coroutine
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_STOP_COVER
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.bluetooth import DeskBLEDevice
from custom_components.desky_desk.const import (
    COMMAND_CLEAR_LIMITS,
    COMMAND_GET_BRIGHTNESS,
    COMMAND_GET_LIGHT_COLOR,
    COMMAND_GET_LIGHTING,
    COMMAND_GET_LIMITS,
    COMMAND_GET_LOCK_STATUS,
    COMMAND_GET_STATUS,
    COMMAND_GET_VIBRATION,
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
from custom_components.desky_desk.errors import (
    DeskCommandError,
    DeskNotConnectedError,
    DeskSettingNotAppliedError,
)
from custom_components.desky_desk.sequencer import _Kind

from . import (
    FakeClock,
    deliver_frame,
    desk_response,
    record_frames,
    record_writes,
    settle,
)

H = COMMAND_HANDSHAKE.hex()
STATUS = COMMAND_GET_STATUS.hex()
STOP = COMMAND_STOP.hex()
UP = COMMAND_MOVE_UP.hex()
DOWN = COMMAND_MOVE_DOWN.hex()
PRESET_2 = COMMAND_MEMORY_2.hex()
CLEAR = COMMAND_CLEAR_LIMITS.hex()
GET_LIMITS = COMMAND_GET_LIMITS.hex()
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
async def desk(
    mock_ble_device: MagicMock, mock_bleak_client: MagicMock, clock: FakeClock
) -> AsyncGenerator[DeskBLEDevice]:
    """Return a connected desk at 80 cm, timed on the virtual clock.

    Whatever it still sends when the test ends, such as a repeat, is cancelled.
    """
    device = DeskBLEDevice(mock_ble_device, clock=clock)
    device._client = mock_bleak_client
    device._height_cm = 80.0
    yield device
    device._sequencer.cancel_all()
    await device._sequencer.wait_cancelled()


@pytest.fixture
def frames(mock_bleak_client: MagicMock, clock: FakeClock) -> Frames:
    """Record every frame the desk is sent, with its virtual time."""
    return record_frames(mock_bleak_client, clock)


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
        # The settings are read back 500 ms after the last set, as the app does
        # for the sensitivity
        (
            "set_sensitivity",
            (2,),
            [(0.0, H), (0.5, "f1f11d0102207e"), (1.0, H), (1.0, STATUS)],
        ),
        (
            "set_touch_mode",
            (1,),
            [(0.0, H), (0.5, "f1f11901011b7e"), (1.0, H), (1.0, STATUS)],
        ),
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
                (0.7, H),
                (0.7, STATUS),
            ],
        ),
        # Clearing the limits: twice, 200 ms apart
        # Clearing the limits: twice, 200 ms apart, then they are read back
        (
            "clear_height_limits",
            (),
            [(0.0, H), (0.0, CLEAR), (0.2, CLEAR), (0.2, GET_LIMITS)],
        ),
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


@pytest.mark.parametrize(
    ("method", "args"),
    [("set_sensitivity", (3,)), ("set_touch_mode", (0,)), ("set_unit", ("cm",))],
)
async def test_setting_that_fails_is_not_read_back(
    desk: DeskBLEDevice,
    mock_bleak_client: MagicMock,
    method: str,
    args: tuple[Any, ...],
) -> None:
    """A setting whose write fails does not ask for the settings afterwards."""
    mock_bleak_client.write_gatt_char.side_effect = [None, Exception("busy")]

    with pytest.raises(DeskCommandError):
        await getattr(desk, method)(*args)

    # The handshake, then the setting that failed; no read-back
    assert mock_bleak_client.write_gatt_char.await_count == 2


# Height limits


@pytest.mark.parametrize(
    ("limit_status", "limit", "height", "expected"),
    [
        # Both set: clear twice, then upper and lower twice each, 50 ms apart;
        # the limits are read back with the last frame
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
                (0.25, GET_LIMITS),
            ],
        ),
        # None set: clear twice, then the new limit twice
        (
            0x00,
            HeightLimit.LOWER,
            65.0,
            [
                (0.0, H),
                (0.0, CLEAR),
                (0.05, CLEAR),
                (0.1, LOWER_65),
                (0.15, LOWER_65),
                (0.15, GET_LIMITS),
            ],
        ),
        # Limits not reported yet: nothing is cleared that might be set
        (
            None,
            HeightLimit.UPPER,
            120.0,
            [(0.0, H), (0.0, UPPER_120), (0.05, UPPER_120), (0.05, GET_LIMITS)],
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
    assert [frame for _, frame in frames[3:]] == [
        upper,
        upper,
        lower,
        lower,
        GET_LIMITS,
    ]


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
        (0.25, GET_LIMITS),
    ]


async def test_limit_not_cleared_while_the_other_is_unread(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """A set limit whose value has not arrived yet is not cleared, so it is kept."""
    _report_limits(desk, upper=1100, lower=None)
    desk._handle_notification(None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, 0x11))
    frames.clear()

    await desk.set_height_limit(HeightLimit.UPPER, 120.0)

    assert frames == [
        (0.0, H),
        (0.0, UPPER_120),
        (0.05, UPPER_120),
        (0.05, GET_LIMITS),
    ]


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
    await clock.advance(0.15)

    await move
    assert frames == [(0.0, H), (0.0, STOP), (0.1, H), (0.1, DOWN), (0.2, DOWN)]
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
async def test_preset_is_one_frame_unless_press_and_hold(
    desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    touch_mode: bytearray | None,
) -> None:
    """In one-press mode, or while the touch mode is unknown, a preset is one frame.

    One frame runs the desk all the way to the preset there.
    """
    clock.auto = False
    if touch_mode is not None:
        desk._handle_notification(None, touch_mode)

    await desk.move_to_preset(2)
    await clock.advance(2.0)

    assert frames == [(0.0, H), (0.0, PRESET_2)]


@pytest.mark.parametrize("touch_mode", [None, ONE_PRESS, PRESS_AND_HOLD])
@pytest.mark.parametrize(("method", "frame"), [("move_up", UP), ("move_down", DOWN)])
async def test_arrows_repeat_in_every_touch_mode(
    desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    touch_mode: bytearray | None,
    method: str,
    frame: str,
) -> None:
    """Move up and down repeat until stopped, whatever the touch mode, as the app's arrows.

    One frame only nudges the desk, about 0.8 cm.
    """
    clock.auto = False
    if touch_mode is not None:
        desk._handle_notification(None, touch_mode)
    writes = record_writes(mock_bleak_client, clock)

    await getattr(desk, method)()
    await clock.advance(0.35)
    await _run(clock, desk.stop())

    assert writes == [
        (0.0, H, True),
        (0.0, frame, True),
        (0.1, frame, False),
        (0.2, frame, False),
        (0.3, frame, False),
        (0.35, STOP, True),
        (0.4, STOP, True),
    ]
    assert desk._sequencer.idle


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
    assert held_desk._sequencer.idle


@patch("time.time")
@pytest.mark.parametrize(
    ("touch_mode", "method", "args", "frame"),
    [
        (PRESS_AND_HOLD, "move_up", (), UP),
        (PRESS_AND_HOLD, "move_to_preset", (2,), PRESET_2),
        # Move up repeats in one-press mode too, until the end of travel
        (ONE_PRESS, "move_up", (), UP),
    ],
)
async def test_repeat_ends_when_the_desk_stops(
    mock_time: MagicMock,
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    touch_mode: bytearray,
    method: str,
    args: tuple[Any, ...],
    frame: str,
) -> None:
    """The repeat ends once the height is unchanged for three readings."""
    held_desk._handle_notification(None, touch_mode)
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
    assert held_desk._sequencer.idle


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


@patch("time.time", return_value=0.0)
async def test_press_and_hold_stops_at_sixty_seconds(
    mock_time: MagicMock,
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
) -> None:
    """The repeat never runs longer than 60 seconds, even while the desk moves."""
    await held_desk.move_up()
    for n in range(140):  # a reading every 500 ms, the height still changing
        held_desk._handle_notification(None, _status_frame(82.0 + n % 2 / 10))
        await clock.advance(0.5)

    repeats = [at for at, frame in frames if frame == UP]
    assert len(repeats) == 601  # the first frame, then 600 repeats
    assert repeats[-1] == 60.0
    assert held_desk._sequencer.idle


@pytest.mark.parametrize("touch_mode", [ONE_PRESS, PRESS_AND_HOLD])
async def test_held_movement_ends_when_readings_stop(
    held_desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    touch_mode: bytearray,
) -> None:
    """A held arrow stops repeating once the desk's height readings stop.

    Without readings a bounce or collision cannot be seen.
    """
    held_desk._handle_notification(None, touch_mode)
    notified = MagicMock()
    held_desk.register_notification_callback(notified)
    await held_desk.move_up()
    for height in (81.0, 82.0, 83.0):  # at 0.2, 0.4 and 0.6 s
        await clock.advance(0.2)
        held_desk._handle_notification(None, _status_frame(height))
    await clock.advance(5.0)

    repeats = [at for at, frame in frames if frame == UP]
    assert 1.6 <= repeats[-1] <= 1.7  # about a second after the last reading
    assert held_desk._movement is None
    assert held_desk._sequencer.idle
    assert notified.call_args.args[2] is False  # not moving


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
    assert held_desk._sequencer.idle


async def test_press_and_hold_ends_when_nothing_moves_within_the_expiry(
    held_desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """With no height reading at all, the repeat still ends after five seconds."""
    await held_desk.move_up()
    await clock.advance(10.0)

    repeats = [at for at, frame in frames if frame == UP]
    assert repeats[-1] == 5.0
    assert len(repeats) == 51  # the first frame, then 50 repeats
    assert held_desk._sequencer.idle


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


@pytest.mark.parametrize(
    ("target", "frame", "readings"),
    [
        # Up from 80 to 85: within the jitter band at 84.6
        (85.0, TO_85_CM, [81.0, 83.0, 84.6]),
        # Down from 80 to 75; a reading past the target counts as reached
        (75.0, "f1f11b0202ee0d7e", [79.0, 77.0, 74.8]),
    ],
)
async def test_move_to_height_repeats_in_press_and_hold_mode(
    held_desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    target: float,
    frame: str,
    readings: list[float],
) -> None:
    """In press-and-hold mode the target repeats, without response, until reached.

    One target frame only nudges the desk in this mode.
    """
    writes = record_writes(mock_bleak_client, clock)

    move = asyncio.create_task(held_desk.move_to_height(target))
    await clock.advance(0.45)
    await move
    for height in readings:
        held_desk._handle_notification(None, _status_frame(height))
        await clock.advance(0.2)
    sent = len(writes)
    await clock.advance(2.0)

    assert writes[:6] == [
        (0.0, H, True),
        (0.0, STOP, True),
        (0.2, frame, True),
        (0.3, frame, True),
        (0.4, frame, False),
        (0.5, frame, False),
    ]
    assert {(data, response) for _, data, response in writes[4:]} == {(frame, False)}
    assert len(writes) == sent  # nothing after the target was reached
    assert held_desk._sequencer.idle
    assert held_desk._movement is not None  # still tracked until the desk stops


async def test_stop_ends_a_held_move_to_height(
    held_desk: DeskBLEDevice, clock: FakeClock, mock_bleak_client: MagicMock
) -> None:
    """A stop ends the repeated target at once."""
    writes = record_writes(mock_bleak_client, clock)

    move = asyncio.create_task(held_desk.move_to_height(85.0))
    await clock.advance(0.55)
    await move
    await _run(clock, held_desk.stop())

    assert [(at, data) for at, data, _ in writes[-4:]] == [
        (0.4, TO_85_CM),
        (0.5, TO_85_CM),
        (0.55, STOP),
        (0.6, STOP),
    ]
    assert held_desk._sequencer.idle


async def test_failed_repeat_ends_quietly(
    held_desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A repeat whose write fails ends, and the failure is only logged at debug."""
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.sequencer")
    # The handshake and the first frame go out; the first repeat fails
    mock_bleak_client.write_gatt_char.side_effect = [None, None, Exception("busy")]

    await held_desk.move_up()
    await clock.advance(0.5)

    assert mock_bleak_client.write_gatt_char.await_count == 3
    assert "Timed command sequence ended: busy" in caplog.text
    assert held_desk._sequencer.idle


async def test_movement_ended_during_its_first_frame_is_not_held(
    held_desk: DeskBLEDevice, clock: FakeClock, mock_bleak_client: MagicMock
) -> None:
    """A movement that ends while its first frame goes out does not repeat."""

    async def _write(_uuid: str, data: bytes, response: bool = True) -> None:
        held_desk._end_movement()  # as a bounce reported meanwhile would

    mock_bleak_client.write_gatt_char.side_effect = _write

    await held_desk.move_up()
    await clock.advance(1.0)

    assert mock_bleak_client.write_gatt_char.await_count == 2  # handshake, frame
    assert held_desk._sequencer.idle


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


# Connecting


async def test_connect_spaces_the_queries(
    mock_ble_device: MagicMock,
    mock_establish_connection: MagicMock,
    frames: Frames,
) -> None:
    """Connecting wakes the desk and asks for its status, then queries 200 ms apart."""
    device = DeskBLEDevice(mock_ble_device)

    assert await device.connect() is True

    assert frames == [
        (0.0, H),
        (0.0, STATUS),  # after the handshake, this brings the settings block
        (0.2, COMMAND_GET_LIGHTING.hex()),
        (0.4, COMMAND_GET_LIGHT_COLOR.hex()),
        (0.6, COMMAND_GET_BRIGHTNESS.hex()),
        (0.8, COMMAND_GET_VIBRATION.hex()),
        (1.0, COMMAND_GET_LOCK_STATUS.hex()),
        (1.2, COMMAND_GET_LIMITS.hex()),
    ]


async def test_stop_waits_for_the_target_frame_on_the_air(
    desk: DeskBLEDevice, clock: FakeClock, mock_bleak_client: MagicMock
) -> None:
    """A stop pressed while a move's target frame is mid-write goes out after it.

    Interrupting the write would free the write lock while the radio is still
    busy, and the stop would fail with InProgress.
    """
    clock.auto = False
    sent: Frames = []
    radio_free_at = 0.0

    async def _write(_uuid: str, data: bytes, response: bool = True) -> None:
        nonlocal radio_free_at
        if clock.now < radio_free_at - 1e-9:
            raise RuntimeError("InProgress")
        radio_free_at = clock.now + 0.05  # each write takes 50 ms
        await clock.sleep(0.05)
        sent.append((round(clock.now, 3), bytes(data).hex()))

    mock_bleak_client.write_gatt_char.side_effect = _write
    move = asyncio.create_task(desk.move_to_height(85.0))
    await clock.advance(0.22)  # the first target frame is on the air until 0.25

    await _run(clock, desk.stop())

    await move  # cut short quietly; the second target frame never goes out
    assert sent == [
        (0.05, H),
        (0.1, STOP),
        (0.25, TO_85_CM),
        (0.3, STOP),
        (0.35, STOP),
    ]


SET_BOTH_120_70 = [
    H,
    CLEAR,
    CLEAR,
    UPPER_120,
    UPPER_120,
    "f1f1220202bce27e",  # lower 70
    "f1f1220202bce27e",
    GET_LIMITS,
]


async def test_limits_set_back_to_back_keep_the_first(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """A limit set straight after another sends the first one's new value."""
    _report_limits(desk, upper=1100, lower=650)

    await desk.set_height_limit(HeightLimit.UPPER, 120.0)
    assert (desk.height_limit_upper, desk.height_limit_lower) == (120.0, 65.0)
    frames.clear()
    await desk.set_height_limit(HeightLimit.LOWER, 70.0)

    assert [frame for _, frame in frames] == SET_BOTH_120_70
    assert (desk.height_limit_upper, desk.height_limit_lower) == (120.0, 70.0)


async def test_limits_set_at_the_same_time_do_not_interleave(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """Two limits set at once go out one sequence after the other, both kept."""
    _report_limits(desk, upper=1100, lower=650)
    frames.clear()

    await asyncio.gather(
        desk.set_height_limit(HeightLimit.UPPER, 120.0),
        desk.set_height_limit(HeightLimit.LOWER, 70.0),
    )

    assert [frame for _, frame in frames] == [
        H,
        CLEAR,
        CLEAR,
        UPPER_120,
        UPPER_120,
        LOWER_65,
        LOWER_65,
        GET_LIMITS,
        *SET_BOTH_120_70,
    ]


async def test_limit_set_after_a_clear_does_not_bring_back_the_other(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """After clearing, setting one limit leaves the other cleared."""
    _report_limits(desk, upper=1100, lower=650)
    notified = MagicMock()
    desk.register_notification_callback(notified)

    await desk.clear_height_limits()
    assert (desk.height_limit_upper, desk.height_limit_lower) == (None, None)
    assert desk.limits_enabled is False
    notified.assert_called_once()
    frames.clear()
    await desk.set_height_limit(HeightLimit.LOWER, 65.0)

    assert [frame for _, frame in frames] == [
        H,
        CLEAR,
        CLEAR,
        LOWER_65,
        LOWER_65,
        GET_LIMITS,
    ]
    assert (desk.height_limit_upper, desk.height_limit_lower) == (None, 65.0)
    assert desk.limits_enabled is True


async def test_limit_from_before_a_unit_change_is_sent_in_the_new_unit(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """A limit the desk reported in inches is re-sent in cm once it shows cm."""
    for frame in (
        "f2f20e0101107e",  # inches
        "f2f2200110317e",  # only the lower limit set
        "f2f2220201183d7e",  # lower 28.0 in, 71.1 cm
        "f2f20e01000f7e",  # now cm
    ):
        desk._handle_notification(None, bytearray.fromhex(frame))
    desk._handle_notification(None, _status_frame(80.0))
    frames.clear()

    await desk.set_height_limit(HeightLimit.UPPER, 120.0)

    lower = desk._create_command_with_word_param(0x22, 711).hex()
    assert [frame for _, frame in frames] == [
        H,
        CLEAR,
        CLEAR,
        UPPER_120,
        UPPER_120,
        lower,
        lower,
        GET_LIMITS,
    ]


async def test_failed_limit_write_keeps_the_known_limits(
    desk: DeskBLEDevice, mock_bleak_client: MagicMock
) -> None:
    """A limit that could not be sent leaves the known limits as they were."""
    _report_limits(desk, upper=1100, lower=650)
    mock_bleak_client.write_gatt_char.side_effect = Exception("busy")

    with pytest.raises(DeskCommandError):
        await desk.set_height_limit(HeightLimit.UPPER, 120.0)

    assert (desk.height_limit_upper, desk.height_limit_lower) == (110.0, 65.0)


async def test_late_limit_reply_does_not_undo_a_newer_change(
    desk: DeskBLEDevice, frames: Frames, clock: FakeClock
) -> None:
    """A limit change reads the limits back itself, and a late reply is overwritten.

    The read-back of one change can arrive while the next change is being
    sent; the next change still keeps both of its limits.
    """
    _report_limits(desk, upper=1100, lower=650)
    await desk.set_height_limit(HeightLimit.UPPER, 120.0)
    assert frames[-1] == (frames[-2][0], GET_LIMITS)  # with the last limit frame

    clock.auto = False
    second = asyncio.create_task(desk.set_height_limit(HeightLimit.LOWER, 70.0))
    await clock.advance(0.05)
    _report_limits(desk, upper=1200, lower=650)  # the first change's reply, late
    await clock.advance(1.0)
    await second
    assert (desk.height_limit_upper, desk.height_limit_lower) == (120.0, 70.0)

    clock.auto = True
    frames.clear()
    await desk.set_height_limit(HeightLimit.UPPER, 115.0)
    upper_115 = "f1f12102047ea57e"
    assert [frame for _, frame in frames] == [
        H,
        CLEAR,
        CLEAR,
        upper_115,
        upper_115,
        "f1f1220202bce27e",  # lower 70
        "f1f1220202bce27e",
        GET_LIMITS,
    ]


async def test_disconnect_forgets_the_limits(
    desk: DeskBLEDevice, frames: Frames, mock_bleak_client: MagicMock
) -> None:
    """After a reconnect, limits from the last connection are not relied on.

    They can change on the hand controller meanwhile, so until the desk
    reports them again nothing is cleared and only the new limit is sent.
    """
    _report_limits(desk, upper=1100, lower=650)

    desk._handle_disconnect(mock_bleak_client)
    assert (desk.height_limit_upper, desk.height_limit_lower) == (None, None)
    assert desk.limits_enabled is False

    desk._client = mock_bleak_client  # connected again
    desk._handle_notification(None, desk_response(UNIT_RESPONSE_HEADER, 0x00))
    frames.clear()
    await desk.set_height_limit(HeightLimit.UPPER, 120.0)

    assert [frame for _, frame in frames] == [H, UPPER_120, UPPER_120, GET_LIMITS]


async def test_stop_waits_at_most_the_write_timeout_behind_a_hung_write(
    desk: DeskBLEDevice, mock_bleak_client: MagicMock
) -> None:
    """A write the desk never confirms fails after the timeout, and the stop follows."""
    sent: list[str] = []

    async def _write(_uuid: str, data: bytes, response: bool = True) -> None:
        if data == COMMAND_MOVE_UP:
            await asyncio.Event().wait()  # never confirmed
        sent.append(bytes(data).hex())

    mock_bleak_client.write_gatt_char.side_effect = _write
    with patch("custom_components.desky_desk.bluetooth.WRITE_TIMEOUT_SECONDS", 0.01):
        move = asyncio.create_task(desk.move_up())
        await asyncio.sleep(0)
        stop = asyncio.create_task(desk.stop())

        with pytest.raises(DeskCommandError, match="TimeoutError"):
            await move
        await stop

    assert sent == [H, STOP, STOP]
    assert desk._movement is None


async def test_failed_move_to_height_leaves_a_stop_that_took_over(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """A move to height whose write fails after a stop took over keeps that stop."""

    async def _stopped_then_failed(steps: Any) -> None:
        # The target write fails just as a stop replaces the movement
        desk._end_movement()
        stop = [(0.0, COMMAND_STOP), (0.05, COMMAND_STOP)]
        desk._sequencer._start_motion(stop, _Kind.MOTION)
        raise DeskCommandError("busy")

    with (
        patch.object(desk._sequencer, "run_motion", side_effect=_stopped_then_failed),
        pytest.raises(DeskCommandError),
    ):
        await desk.move_to_height(85.0)
    await settle()

    assert frames == [(0.0, STOP), (0.05, STOP)]


async def test_failed_move_to_height_ends_its_movement(
    desk: DeskBLEDevice, mock_bleak_client: MagicMock
) -> None:
    """A move to height whose write fails is no longer tracked as a movement."""
    mock_bleak_client.write_gatt_char.side_effect = [None, None, Exception("busy")]

    with pytest.raises(DeskCommandError, match="busy"):
        await desk.move_to_height(85.0)

    assert desk._movement is None


async def test_only_the_repeats_skip_the_response(
    held_desk: DeskBLEDevice, clock: FakeClock, mock_bleak_client: MagicMock
) -> None:
    """The first frame and the stops wait for the desk; the repeats do not."""
    writes = record_writes(mock_bleak_client, clock)

    await held_desk.move_to_preset(2)
    await clock.advance(0.25)
    await _run(clock, held_desk.stop())

    assert writes == [
        (0.0, H, True),
        (0.0, PRESET_2, True),
        (0.1, PRESET_2, False),
        (0.2, PRESET_2, False),
        (0.25, STOP, True),
        (0.3, STOP, True),
    ]


# Settings the desk does not confirm, checked after they are sent

TOUCH_PRESS_AND_HOLD = "f1f11901011b7e"
UNIT_IN = "f1f10e0101107e"
CHECKED_SETTINGS = [
    # method, argument, the report of each value, the frames of one attempt
    (
        "set_touch_mode",
        1,
        {0: ONE_PRESS, 1: PRESS_AND_HOLD},
        [(0.0, H), (0.5, TOUCH_PRESS_AND_HOLD), (1.0, H), (1.0, STATUS)],
    ),
    (
        "set_unit",
        "in",
        {
            "cm": bytearray.fromhex("f2f20e01000f7e"),
            "in": bytearray.fromhex("f2f20e0101107e"),
        },
        [
            (0.0, H),
            (0.0, UNIT_IN),
            (0.1, UNIT_IN),
            (0.2, UNIT_IN),
            (0.7, H),
            (0.7, STATUS),
        ],
    ),
]


def _answer_status(
    desk: DeskBLEDevice,
    mock_bleak_client: MagicMock,
    clock: FakeClock,
    reports: list[bytearray],
) -> Frames:
    """Record frames, and answer each status request with the next report."""
    frames: Frames = []

    async def _write(_uuid: str, data: bytes, *, response: bool) -> None:
        frames.append((round(clock.now, 3), bytes(data).hex()))
        if bytes(data) == COMMAND_GET_STATUS and reports:
            desk._handle_notification(None, reports.pop(0))

    mock_bleak_client.write_gatt_char.side_effect = _write
    return frames


def _later(attempt: Frames, seconds: float) -> Frames:
    """Return an attempt's frames, sent the given seconds later."""
    return [(round(at + seconds, 3), frame) for at, frame in attempt]


@pytest.mark.parametrize(("method", "value", "report", "attempt"), CHECKED_SETTINGS)
async def test_checked_setting_applied_first_time(
    desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    method: str,
    value: Any,
    report: dict[Any, bytearray],
    attempt: Frames,
) -> None:
    """A setting the desk reports as applied is sent once."""
    frames = _answer_status(desk, mock_bleak_client, clock, [report[value]])

    await getattr(desk, method)(value)

    assert frames == attempt


@pytest.mark.parametrize(("method", "value", "report", "attempt"), CHECKED_SETTINGS)
async def test_checked_setting_applied_on_the_retry(
    desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    method: str,
    value: Any,
    report: dict[Any, bytearray],
    attempt: Frames,
) -> None:
    """A setting the desk ignored once is sent again, and applies."""
    old = next(report[other] for other in report if other != value)
    frames = _answer_status(desk, mock_bleak_client, clock, [old, report[value]])

    await getattr(desk, method)(value)

    end = attempt[-1][0]
    assert frames == attempt + _later(attempt, end)


@pytest.mark.parametrize(("method", "value", "report", "attempt"), CHECKED_SETTINGS)
async def test_checked_setting_never_applied_raises(
    desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    method: str,
    value: Any,
    report: dict[Any, bytearray],
    attempt: Frames,
) -> None:
    """A setting the desk still reports unchanged after the retry fails."""
    old = next(report[other] for other in report if other != value)
    frames = _answer_status(desk, mock_bleak_client, clock, [old, old])

    with pytest.raises(DeskSettingNotAppliedError):
        await getattr(desk, method)(value)

    assert len(frames) == 2 * len(attempt)  # sent twice, nothing more
    assert not any(desk._report_waiters.values())


@pytest.mark.parametrize(("method", "value", "report", "attempt"), CHECKED_SETTINGS)
async def test_checked_setting_without_a_report_is_sent_once(
    desk: DeskBLEDevice,
    frames: Frames,
    clock: FakeClock,
    method: str,
    value: Any,
    report: dict[Any, bytearray],
    attempt: Frames,
) -> None:
    """A desk that does not report the setting cannot be checked; it is not resent."""
    clock.auto = False
    task = asyncio.create_task(getattr(desk, method)(value))
    await clock.advance(attempt[-1][0] + 1.9)
    assert not task.done()  # still waiting for the report

    await clock.advance(0.1)
    await task

    assert frames == attempt


@pytest.mark.parametrize("touch_mode", [ONE_PRESS, PRESS_AND_HOLD])
async def test_move_to_height_waits_for_the_first_reading(
    desk: DeskBLEDevice,
    clock: FakeClock,
    mock_bleak_client: MagicMock,
    touch_mode: bytearray,
) -> None:
    """Before the desk has reported a height, it is asked for one first.

    The direction comes from the reply, not from the 0.0 height before it.
    """
    desk._handle_notification(None, touch_mode)
    desk._height_cm = 0.0  # no reading since connecting
    sent: list[str] = []

    async def _write(_uuid: str, data: bytes, *, response: bool) -> None:
        sent.append(bytes(data).hex())
        if bytes(data) == COMMAND_GET_STATUS:
            desk._handle_notification(None, _status_frame(80.0))

    mock_bleak_client.write_gatt_char.side_effect = _write

    await desk.move_to_height(75.0)

    assert sent[:5] == [STATUS, H, STOP, "f1f11b0202ee0d7e", "f1f11b0202ee0d7e"]
    assert desk.movement_direction == "down"


async def test_move_to_height_without_a_reading_fails(
    desk: DeskBLEDevice, frames: Frames
) -> None:
    """A desk that does not report its height is not moved blind."""
    desk._height_cm = 0.0

    with pytest.raises(DeskCommandError, match="has not reported its height"):
        await desk.move_to_height(75.0)

    assert frames == [(0.0, STATUS)]
    assert desk._movement is None
