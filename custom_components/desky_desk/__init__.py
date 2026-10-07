"""The Desky Desk integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .services import async_setup_services

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

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Desky Desk actions, whether or not any desk is loaded."""
    async_setup_services(hass)
    return True


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
