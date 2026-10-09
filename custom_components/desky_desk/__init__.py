"""The Desky Desk integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
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

# Sensors removed in 2.0.0 because they only repeated other entities, by unique
# ID suffix
REMOVED_SENSORS = ("led_color", "vibration_intensity_display")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Desky Desk actions, whether or not any desk is loaded."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DeskyConfigEntry) -> bool:
    """Set up Desky Desk from a config entry."""
    _LOGGER.debug("Setting up Desky Desk integration for %s", entry.unique_id)

    _async_remove_retired_sensors(hass, entry)

    coordinator = DeskUpdateCoordinator(hass, entry)
    await coordinator.async_connect()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


@callback
def _async_remove_retired_sensors(hass: HomeAssistant, entry: DeskyConfigEntry) -> None:
    """Delete the registry entries of entities earlier releases created."""
    entity_registry = er.async_get(hass)
    for key in REMOVED_SENSORS:
        if entity_id := entity_registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, f"{entry.unique_id}_{key}"
        ):
            entity_registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: DeskyConfigEntry) -> bool:
    """Unload a config entry.

    The coordinator shuts down and disconnects from the desk when the entry
    finishes unloading, and Home Assistant cancels its background tasks.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
