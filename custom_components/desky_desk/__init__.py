"""The Desky Desk integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.COVER,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: DeskyConfigEntry) -> bool:
    """Set up Desky Desk from a config entry."""
    _LOGGER.debug("Setting up Desky Desk integration for %s", entry.unique_id)

    coordinator = DeskUpdateCoordinator(hass, entry)
    await coordinator.async_connect()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeskyConfigEntry) -> bool:
    """Unload a config entry.

    The coordinator shuts down and disconnects from the desk when the entry
    finishes unloading, and Home Assistant cancels its background tasks.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
