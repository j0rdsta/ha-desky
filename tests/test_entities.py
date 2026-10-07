"""Snapshot the entities a fully set-up desk exposes.

The snapshot pins every entity's unique ID, entity ID and registry metadata
together with its state, so any change to them shows up as a snapshot diff.
"""

from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.desky_desk.const import DOMAIN

from . import disconnect_desk, notify_desk

# State attributes Home Assistant added within the supported version range
VERSION_DEPENDENT_ATTRIBUTES = {"is_closed"}


def _plain(value: Any) -> Any:
    """Reduce a value to plain data so the snapshot reads the same on every pin."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_plain(item) for item in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, dict):
        return {
            _plain(key): _plain(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the registry entries and states of every desk entity."""
    entries = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )
    assert entries

    entities = {}
    for entry in sorted(entries, key=lambda entry: entry.entity_id):
        state = hass.states.get(entry.entity_id)
        entities[entry.entity_id] = {
            "unique_id": entry.unique_id,
            "platform": entry.platform,
            "original_name": entry.original_name,
            "translation_key": entry.translation_key,
            "original_device_class": _plain(entry.original_device_class),
            "entity_category": _plain(entry.entity_category),
            "disabled_by": _plain(entry.disabled_by),
            "state": state.state if state else None,
            "attributes": _plain(
                {
                    key: value
                    for key, value in state.attributes.items()
                    if key not in VERSION_DEPENDENT_ATTRIBUTES
                }
            )
            if state
            else None,
        }

    assert entities == snapshot


# Every entity a v1.0.x install registered, by platform and unique ID suffix
V1_ENTITIES = {
    ("binary_sensor", "collision"),
    ("button", "move_down"),
    ("button", "move_up"),
    ("button", "preset_1"),
    ("button", "preset_2"),
    ("button", "preset_3"),
    ("button", "preset_4"),
    ("cover", "cover"),
    ("light", "led_strip"),
    ("number", "height"),
    ("number", "height_limit_lower"),
    ("number", "height_limit_upper"),
    ("number", "vibration_intensity"),
    ("select", "sensitivity"),
    ("select", "touch_mode"),
    ("select", "unit"),
    ("sensor", "height_display"),
    ("sensor", "led_color"),
    ("sensor", "vibration_intensity_display"),
    ("switch", "lock"),
    ("switch", "vibration"),
}

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / DOMAIN


async def test_entity_ids_survive_upgrade(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test entities registered by v1.0.x keep their entity IDs after upgrading."""
    mock_config_entry.add_to_hass(hass)
    unique_id_prefix = mock_config_entry.unique_id
    # Object IDs no fresh install would generate, as if the desk had been renamed
    registered = {
        f"{unique_id_prefix}_{key}": entity_registry.async_get_or_create(
            platform,
            DOMAIN,
            f"{unique_id_prefix}_{key}",
            suggested_object_id=f"standing_desk_{key}",
            config_entry=mock_config_entry,
        ).entity_id
        for platform, key in V1_ENTITIES
    }

    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address="AA:BB:CC:DD:EE:FF"),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert {entry.unique_id: entry.entity_id for entry in entries} == registered
    for entity_id in registered.values():
        assert hass.states.get(entity_id) is not None


async def test_unique_ids_unchanged(
    entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """Test a fresh install registers exactly the v1.0.x unique IDs."""
    entries = er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    )
    assert {(entry.domain, entry.unique_id) for entry in entries} == {
        (platform, f"{init_integration.unique_id}_{key}")
        for platform, key in V1_ENTITIES
    }


async def test_entity_names_follow_device_name(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the cover takes the device name and other entities are prefixed by it."""
    mock_desk.name = "Office Desk"
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address="AA:BB:CC:DD:EE:FF"),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    def friendly_name(platform: str, key: str) -> str:
        entity_id = entity_registry.async_get_entity_id(
            platform, DOMAIN, f"{mock_config_entry.unique_id}_{key}"
        )
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        return state.attributes["friendly_name"]

    assert friendly_name("cover", "cover") == "Office Desk"
    assert friendly_name("number", "height") == "Office Desk Height"
    assert [friendly_name("button", f"preset_{n}") for n in range(1, 5)] == [
        f"Office Desk Preset {n}" for n in range(1, 5)
    ]


async def test_translations_and_icons_resolve(
    entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """Test every translation key has a name and an icon, and none are unused."""
    strings = json.loads((INTEGRATION_DIR / "strings.json").read_text())["entity"]
    icons = json.loads((INTEGRATION_DIR / "icons.json").read_text())["entity"]

    used: set[tuple[str, str]] = set()
    for entry in er.async_entries_for_config_entry(
        entity_registry, init_integration.entry_id
    ):
        assert entry.translation_key, entry.entity_id
        used.add((entry.domain, entry.translation_key))
        # Entities with a device class get their icon from it
        if entry.original_device_class is None:
            assert entry.translation_key in icons[entry.domain], entry.entity_id
        if entry.domain == "cover":
            # The desk cover is named after the device
            assert entry.original_name is None
        else:
            assert entry.translation_key in strings[entry.domain], entry.entity_id
            assert entry.original_name

    translated = {(platform, key) for platform, keys in strings.items() for key in keys}
    with_icons = {(platform, key) for platform, keys in icons.items() for key in keys}
    assert translated == used - {("cover", "desk")}
    assert with_icons == used - {("binary_sensor", "collision")}


async def test_translation_files_match() -> None:
    """Test the English translation matches strings.json."""
    strings = json.loads((INTEGRATION_DIR / "strings.json").read_text())
    english = json.loads((INTEGRATION_DIR / "translations" / "en.json").read_text())
    assert english == strings


async def test_availability_follows_connection(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test every entity goes unavailable on disconnect and returns on reconnect."""
    entity_ids = [
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
    ]

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE, entity_id
        assert "connected" not in state.attributes

    mock_desk.is_connected = True
    notify_desk(mock_desk, height_cm=95.0)
    await hass.async_block_till_done()
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != STATE_UNAVAILABLE, entity_id
        assert "connected" not in state.attributes
    height = hass.states.get("number.desky_desk_height")
    assert height is not None
    assert height.state == "95.0"
