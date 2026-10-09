"""Test the desk's posture: sitting or standing, from where the desk stops."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.desky_desk.const import (
    CONF_STANDING_THRESHOLD,
    POSTURE_SETTLE_SECONDS,
    Posture,
    height_known,
)

from . import disconnect_desk, notify_desk

# Status frames arrive about every 200 ms while the desk moves
FRAME_SECONDS = 0.2


async def _advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move Home Assistant time forward and run whatever became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _move(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    desk: MagicMock,
    heights: list[float],
) -> None:
    """Report each height one frame apart, as a moving desk does."""
    for height in heights:
        notify_desk(desk, height_cm=height)
        await _advance(hass, freezer, FRAME_SECONDS)


async def _settle(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the desk stand still long enough for the posture to follow it."""
    await _advance(hass, freezer, POSTURE_SETTLE_SECONDS)


async def test_posture_follows_the_settled_height(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """Test the posture is known once the desk has stood still after setup."""
    coordinator = init_integration.runtime_data
    assert coordinator.data.posture is None

    await _settle(hass, freezer)

    assert coordinator.data.posture == Posture.SITTING
    assert coordinator.data.posture_changed_at is not None


async def test_desk_raised_to_standing_height(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a desk that stops at 110 cm is standing."""
    coordinator = init_integration.runtime_data
    await _settle(hass, freezer)

    await _move(hass, freezer, mock_desk, [85.0, 95.0, 105.0, 110.0])
    stopped_at = coordinator.data.posture_changed_at
    assert coordinator.data.posture == Posture.SITTING

    await _settle(hass, freezer)

    assert coordinator.data.posture == Posture.STANDING
    # The change is dated to when the desk stopped, not when it was confirmed
    assert coordinator.data.posture_changed_at is not None
    assert stopped_at is not None
    assert coordinator.data.posture_changed_at > stopped_at
    assert coordinator.data.posture_changed_at < (
        stopped_at + 4 * FRAME_SECONDS + POSTURE_SETTLE_SECONDS
    )


async def test_threshold_is_inclusive(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a desk stopped exactly at the threshold is standing."""
    await _move(hass, freezer, mock_desk, [95.0])
    await _settle(hass, freezer)

    assert init_integration.runtime_data.data.posture == Posture.STANDING


async def test_passing_through_the_threshold_mid_move(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a desk that rises past the threshold and comes back stays sitting."""
    coordinator = init_integration.runtime_data
    await _move(hass, freezer, mock_desk, [75.0])
    await _settle(hass, freezer)
    changed_at = coordinator.data.posture_changed_at

    up = [75.0 + step * 2.5 for step in range(1, 15)]  # to 110 cm
    await _move(hass, freezer, mock_desk, [*up, *reversed(up[:-1]), 75.0])
    await _settle(hass, freezer)

    assert coordinator.data.posture == Posture.SITTING
    assert coordinator.data.posture_changed_at == changed_at


async def test_posture_waits_for_a_commanded_move_to_end(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the posture does not change while the desk reports it is moving."""
    coordinator = init_integration.runtime_data
    await _settle(hass, freezer)

    notify_desk(mock_desk, height_cm=110.0, is_moving=True)
    await _settle(hass, freezer)
    await _settle(hass, freezer)
    assert coordinator.data.posture == Posture.SITTING

    notify_desk(mock_desk, is_moving=False)
    await _settle(hass, freezer)
    assert coordinator.data.posture == Posture.STANDING


async def test_posture_unknown_while_disconnected(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the posture is unknown while the desk is disconnected."""
    coordinator = init_integration.runtime_data
    await _settle(hass, freezer)

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert coordinator.data.posture is None

    # Back again, the posture is known once the desk has stood still
    mock_desk.is_connected = True
    notify_desk(mock_desk, height_cm=110.0)
    await hass.async_block_till_done()
    assert coordinator.data.posture is None
    await _settle(hass, freezer)
    assert coordinator.data.posture == Posture.STANDING


async def test_posture_unknown_before_the_first_height(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a desk that has not reported a height has no posture."""
    await _move(hass, freezer, mock_desk, [0.0])
    await _settle(hass, freezer)

    assert init_integration.runtime_data.data.posture is None


@pytest.mark.parametrize(
    ("threshold", "posture"), [(105, Posture.SITTING), (100, Posture.STANDING)]
)
async def test_posture_uses_the_configured_threshold(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
    threshold: int,
    posture: Posture,
) -> None:
    """Test the posture follows the threshold set in the options."""
    mock_desk.height_cm = 100.0
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_STANDING_THRESHOLD: threshold}
    )
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "homeassistant.components.bluetooth.async_ble_device_from_address",
            lambda *args, **kwargs: MagicMock(address="AA:BB:CC:DD:EE:FF"),
        )
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    await _settle(hass, freezer)

    assert mock_config_entry.runtime_data.data.posture == posture


async def test_unload_cancels_a_pending_posture_check(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """Test unloading before the desk settles leaves no posture check behind."""
    coordinator = init_integration.runtime_data
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    await _settle(hass, freezer)

    assert coordinator.data.posture is None


@pytest.mark.parametrize(
    ("height_cm", "known"), [(0.0, False), (-0.1, False), (0.1, True), (80.0, True)]
)
def test_height_known(height_cm: float, known: bool) -> None:
    """Test 0 cm, the placeholder before the desk reports a height, is not a height."""
    assert height_known(height_cm) is known
