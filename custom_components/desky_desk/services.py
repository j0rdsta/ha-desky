"""Actions for Desky Desk."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids
import voluptuous as vol

from .const import DOMAIN, HeightLimit
from .coordinator import DeskUpdateCoordinator, DeskyConfigEntry
from .entity import translate_desk_errors
from .validation import checked_height_limit, validate_move_to_height

SERVICE_MOVE_TO_HEIGHT = "move_to_height"
SERVICE_SET_HEIGHT_LIMIT = "set_height_limit"
SERVICE_CLEAR_HEIGHT_LIMITS = "clear_height_limits"

ATTR_HEIGHT = "height"
ATTR_LIMIT = "limit"

MOVE_TO_HEIGHT_SCHEMA = cv.make_entity_service_schema(
    {vol.Required(ATTR_HEIGHT): vol.Coerce(float)}
)
SET_HEIGHT_LIMIT_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_LIMIT): vol.Coerce(HeightLimit),
        vol.Required(ATTR_HEIGHT): vol.Coerce(float),
    }
)
CLEAR_HEIGHT_LIMITS_SCHEMA = cv.make_entity_service_schema({})


def _desks(call: ServiceCall, entry_ids: set[str]) -> list[DeskUpdateCoordinator]:
    """Return the coordinators of the targeted desks, which must all be connected.

    These are plain actions rather than entity actions: Home Assistant skips
    unavailable entities in entity actions, and a call must not succeed
    silently against a desk that is not loaded or not connected.
    """
    entries: list[DeskyConfigEntry] = [
        entry
        for entry_id in sorted(entry_ids)
        if (entry := call.hass.config_entries.async_get_entry(entry_id)) is not None
        and entry.domain == DOMAIN
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_desk_targeted"
        )
    for entry in entries:
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="desk_not_loaded",
                translation_placeholders={"desk": entry.title},
            )
    coordinators = [entry.runtime_data for entry in entries]
    for coordinator in coordinators:
        if not coordinator.data.is_connected:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_connected"
            )
    return coordinators


async def _async_get_desks(call: ServiceCall) -> list[DeskUpdateCoordinator]:
    """Return the coordinators of the desks an action targets."""
    return _desks(call, await async_extract_config_entry_ids(call))


async def _async_move_to_height(call: ServiceCall) -> None:
    """Move the targeted desks to a height in cm."""
    height: float = call.data[ATTR_HEIGHT]
    desks = await _async_get_desks(call)
    # Check every desk before moving any
    for coordinator in desks:
        validate_move_to_height(coordinator.data, height)
    for coordinator in desks:
        with translate_desk_errors():
            await coordinator.device.move_to_height(height)
        await coordinator.async_request_refresh()


async def _async_set_height_limit(call: ServiceCall) -> None:
    """Set the upper or lower height limit of the targeted desks."""
    limit: HeightLimit = call.data[ATTR_LIMIT]
    height: float = call.data[ATTR_HEIGHT]
    # Check every desk before sending to any
    limits = [
        (
            coordinator,
            checked_height_limit(coordinator.data, coordinator.device, limit, height),
        )
        for coordinator in await _async_get_desks(call)
    ]
    for coordinator, rounded in limits:
        device = coordinator.device
        with translate_desk_errors():
            await device.set_height_limit(limit, rounded)
            # The desk may adjust the limit, so show what it reports
            await device.get_limits()


async def _async_clear_height_limits(call: ServiceCall) -> None:
    """Clear both height limits of the targeted desks."""
    for coordinator in await _async_get_desks(call):
        device = coordinator.device
        with translate_desk_errors():
            await device.clear_height_limits()
            await device.get_limits()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the desk actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_MOVE_TO_HEIGHT, _async_move_to_height, MOVE_TO_HEIGHT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HEIGHT_LIMIT,
        _async_set_height_limit,
        SET_HEIGHT_LIMIT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_HEIGHT_LIMITS,
        _async_clear_height_limits,
        CLEAR_HEIGHT_LIMITS_SCHEMA,
    )
