"""Test the automation blueprints shipped in blueprints/automation/desky_desk."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import timedelta
from pathlib import Path
import shutil
from typing import Any
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.components.automation.helpers import async_get_blueprints
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.desky_desk.const import POSTURE_SETTLE_SECONDS

from . import disconnect_desk, notify_desk

BLUEPRINT_DIR = (
    Path(__file__).parent.parent / "blueprints" / "automation" / "desky_desk"
)
BLUEPRINTS = sorted(path.name for path in BLUEPRINT_DIR.glob("*.yaml"))

POSTURE = "sensor.desky_desk_posture"
COLLISION = "binary_sensor.desky_desk_collision_detected"
COVER = "cover.desky_desk"
PRESET_2 = "button.desky_desk_preset_2"
PERSON = "person.alex"
NOTIFY = "notify.test"

# A Wednesday, in the test time zone (US/Pacific)
WEDNESDAY_MORNING = "2026-10-07 10:00:00-07:00"


@pytest.fixture(autouse=True)
async def blueprint_config(hass: HomeAssistant, tmp_path: Path) -> AsyncGenerator[None]:
    """Give Home Assistant a config dir holding this repository's blueprints."""
    hass.config.config_dir = str(tmp_path)
    shutil.copytree(
        BLUEPRINT_DIR, tmp_path / "blueprints" / "automation" / "desky_desk"
    )
    yield
    # Turning the automations off detaches their time triggers
    if hass.services.has_service(AUTOMATION_DOMAIN, SERVICE_TURN_OFF):
        await hass.services.async_call(
            AUTOMATION_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: "all"}, blocking=True
        )


async def _create_automation(
    hass: HomeAssistant, blueprint: str, inputs: dict[str, Any]
) -> None:
    """Instantiate an automation from one of the desk's blueprints."""
    assert await async_setup_component(
        hass,
        AUTOMATION_DOMAIN,
        {
            AUTOMATION_DOMAIN: {
                "alias": "Blueprint test",
                "use_blueprint": {
                    "path": f"desky_desk/{blueprint}",
                    "input": inputs,
                },
            }
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("automation.blueprint_test")
    assert state is not None
    assert state.state == STATE_ON


async def _advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta
) -> None:
    """Move time forward a minute at a time, running whatever became due."""
    remaining = delta
    while remaining > timedelta(0):
        step = min(remaining, timedelta(minutes=1))
        freezer.tick(step)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        remaining -= step


async def _settle(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the desk stand still long enough for the posture to follow it."""
    await _advance(hass, freezer, timedelta(seconds=POSTURE_SETTLE_SECONDS))


@pytest.mark.parametrize("blueprint", BLUEPRINTS)
async def test_blueprint_is_valid(hass: HomeAssistant, blueprint: str) -> None:
    """Test each blueprint passes Home Assistant's blueprint schema."""
    loaded = await async_get_blueprints(hass).async_get_blueprint(
        f"desky_desk/{blueprint}"
    )

    assert loaded.domain == AUTOMATION_DOMAIN
    assert loaded.name.startswith("Desky - ")
    assert loaded.metadata["source_url"].endswith(f"/desky_desk/{blueprint}")


def test_all_blueprints_are_tested() -> None:
    """Test the blueprint list is what these tests cover."""
    assert BLUEPRINTS == [
        "collision_alert.yaml",
        "scheduled_stand.yaml",
        "sit_stand_reminder.yaml",
    ]


def _reminder_inputs(**changes: Any) -> dict[str, Any]:
    return {
        "posture_sensor": POSTURE,
        "sitting_minutes": 60,
        "notify_action": NOTIFY,
        **changes,
    }


@pytest.mark.freeze_time(WEDNESDAY_MORNING)
@pytest.mark.usefixtures("init_integration")
async def test_reminder_after_sitting_too_long(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test one reminder once the desk has been sitting for longer than set."""
    calls = async_mock_service(hass, "notify", "test")
    await _create_automation(
        hass,
        "sit_stand_reminder.yaml",
        _reminder_inputs(start_time="09:00:00", end_time="17:00:00"),
    )
    await _settle(hass, freezer)
    assert hass.states.get(POSTURE).state == "sitting"

    await _advance(hass, freezer, timedelta(minutes=59))
    assert calls == []

    await _advance(hass, freezer, timedelta(minutes=2))
    assert len(calls) == 1
    assert calls[0].data == {
        "title": "Time to stand up",
        "message": "You have been sitting for 60 minutes.",
    }

    await _advance(hass, freezer, timedelta(minutes=90))
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("window", "weekdays"),
    [
        (("12:00:00", "17:00:00"), ["mon", "tue", "wed", "thu", "fri"]),
        (("09:00:00", "17:00:00"), ["sat", "sun"]),
    ],
    ids=["outside_time_window", "other_weekday"],
)
@pytest.mark.freeze_time(WEDNESDAY_MORNING)
@pytest.mark.usefixtures("init_integration")
async def test_no_reminder_outside_the_window(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    window: tuple[str, str],
    weekdays: list[str],
) -> None:
    """Test no reminder outside the time window or on other days."""
    calls = async_mock_service(hass, "notify", "test")
    await _create_automation(
        hass,
        "sit_stand_reminder.yaml",
        _reminder_inputs(start_time=window[0], end_time=window[1], weekdays=weekdays),
    )
    await _settle(hass, freezer)

    await _advance(hass, freezer, timedelta(minutes=61))

    assert calls == []


@pytest.mark.freeze_time(WEDNESDAY_MORNING)
async def test_unavailable_desk_does_not_count_as_sitting(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test sitting before and after an unavailable period is not added up."""
    calls = async_mock_service(hass, "notify", "test")
    await _create_automation(hass, "sit_stand_reminder.yaml", _reminder_inputs())
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=40))

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert hass.states.get(POSTURE).state == STATE_UNAVAILABLE
    await _advance(hass, freezer, timedelta(minutes=40))

    mock_desk.is_connected = True
    notify_desk(mock_desk)
    await _settle(hass, freezer)
    assert hass.states.get(POSTURE).state == "sitting"
    await _advance(hass, freezer, timedelta(minutes=40))
    assert calls == []

    # The timer started again when the desk came back
    await _advance(hass, freezer, timedelta(minutes=21))
    assert len(calls) == 1


def _stand_inputs(**changes: Any) -> dict[str, Any]:
    return {
        "desk": COVER,
        "times": ["10:30"],
        "weekdays": ["wed"],
        **changes,
    }


@pytest.mark.parametrize(
    ("inputs", "command", "args"),
    [
        ({"preset_button": PRESET_2}, "move_to_preset", (2,)),
        ({"height": 105.5}, "move_to_height", (105.5,)),
    ],
    ids=["preset", "height"],
)
@pytest.mark.freeze_time(WEDNESDAY_MORNING)
@pytest.mark.usefixtures("init_integration")
async def test_scheduled_stand_moves_the_desk(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_desk: MagicMock,
    inputs: dict[str, Any],
    command: str,
    args: tuple[Any, ...],
) -> None:
    """Test the desk moves to the preset or height at the set time."""
    hass.states.async_set(PERSON, "home")
    await _create_automation(
        hass, "scheduled_stand.yaml", _stand_inputs(person=PERSON, **inputs)
    )

    await _advance(hass, freezer, timedelta(minutes=29))
    getattr(mock_desk, command).assert_not_awaited()

    await _advance(hass, freezer, timedelta(minutes=1))
    getattr(mock_desk, command).assert_awaited_once_with(*args)


@pytest.mark.parametrize(
    ("weekdays", "person_state"),
    [(["wed"], "not_home"), (["mon", "tue"], "home")],
    ids=["person_away", "other_weekday"],
)
@pytest.mark.freeze_time(WEDNESDAY_MORNING)
@pytest.mark.usefixtures("init_integration")
async def test_scheduled_stand_does_not_move(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_desk: MagicMock,
    weekdays: list[str],
    person_state: str,
) -> None:
    """Test no command while the person is away, or on other days."""
    hass.states.async_set(PERSON, person_state)
    await _create_automation(
        hass,
        "scheduled_stand.yaml",
        _stand_inputs(preset_button=PRESET_2, weekdays=weekdays, person=PERSON),
    )

    await _advance(hass, freezer, timedelta(minutes=31))

    mock_desk.move_to_preset.assert_not_awaited()
    mock_desk.move_to_height.assert_not_awaited()


@pytest.mark.freeze_time(WEDNESDAY_MORNING)
@pytest.mark.usefixtures("init_integration")
async def test_scheduled_stand_without_a_person(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mock_desk: MagicMock
) -> None:
    """Test the desk moves whoever is home when no person is chosen."""
    await _create_automation(hass, "scheduled_stand.yaml", _stand_inputs())

    await _advance(hass, freezer, timedelta(minutes=30))

    mock_desk.move_to_height.assert_awaited_once_with(110)


@pytest.mark.usefixtures("init_integration")
async def test_collision_alert(hass: HomeAssistant, mock_desk: MagicMock) -> None:
    """Test one alert naming the desk when the collision sensor turns on."""
    calls = async_mock_service(hass, "notify", "test")
    await _create_automation(
        hass,
        "collision_alert.yaml",
        {"collision_sensor": COLLISION, "notify_action": NOTIFY},
    )

    notify_desk(mock_desk, collision_detected=True)
    await hass.async_block_till_done()

    assert hass.states.get(COLLISION).state == STATE_ON
    assert len(calls) == 1
    assert calls[0].data == {
        "title": "Desk collision",
        "message": "Desky Desk stopped early. Check what is under or above it.",
    }
