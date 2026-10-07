"""Test the Desky Desk config entry diagnostics."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from . import disconnect_desk

ADDRESS = "AA:BB:CC:DD:EE:FF"
SERIAL_NUMBER = "TEST123456"
HEADERS = ["f2 f2 01 03", "f2 f2 0e 01", "f2 f2 19 01"]


async def test_diagnostics_connected(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test diagnostics for a connected desk."""
    mock_desk.recent_notification_headers = HEADERS

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    assert diagnostics["connected"] is True
    assert diagnostics["stale"] is False
    assert diagnostics["recent_notification_headers"] == HEADERS
    assert diagnostics == snapshot


async def test_diagnostics_disconnected(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test diagnostics still download, marked stale, while the desk is away."""
    mock_desk.recent_notification_headers = HEADERS
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    assert diagnostics["connected"] is False
    assert diagnostics["stale"] is True
    assert diagnostics["state"]["height_cm"] == 80.0
    assert diagnostics == snapshot


async def test_diagnostics_redact_address_and_serial(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the address and serial number appear nowhere, even inside names."""
    mock_desk.recent_notification_headers = HEADERS
    # Some Bluetooth stacks name an unnamed device after its address
    mock_desk.name = ADDRESS.replace(":", "-")
    hass.config_entries.async_update_entry(
        init_integration, title=f"Desk {ADDRESS.lower()}"
    )

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    output = json.dumps(diagnostics).upper()
    for secret in (ADDRESS, ADDRESS.replace(":", "-"), ADDRESS.replace(":", "")):
        assert secret not in output
    assert SERIAL_NUMBER not in output
    assert diagnostics["entry"]["unique_id"] == "**REDACTED**"
    assert diagnostics["device"]["serial_number"] == "**REDACTED**"
