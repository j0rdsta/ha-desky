"""Snapshot the entities a fully set-up desk exposes.

The snapshot pins every entity's unique ID, entity ID and registry metadata
together with its state, so any change to them shows up as a snapshot diff.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.desky_desk.const import DOMAIN

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
    mock_coordinator_data: dict[str, Any],
    snapshot: SnapshotAssertion,
) -> None:
    """Test the registry entries and states of every desk entity."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator.async_set_updated_data(mock_coordinator_data)
    await hass.async_block_till_done()

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
