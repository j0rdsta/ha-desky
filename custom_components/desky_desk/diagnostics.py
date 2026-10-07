"""Diagnostics for Desky Desk."""

from __future__ import annotations

from dataclasses import asdict
import re
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .coordinator import DeskyConfigEntry

TO_REDACT = {CONF_ADDRESS, "unique_id", "serial_number"}

# Fields of the desk data that describe the device rather than its state
DEVICE_FIELDS = (
    "manufacturer_name",
    "model_number",
    "serial_number",
    "hardware_revision",
    "firmware_revision",
    "software_revision",
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DeskyConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    device = coordinator.device
    data = asdict(coordinator.data)
    connected = data.pop("is_connected")

    diagnostics = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
            "unique_id": entry.unique_id,
        },
        "device": {
            "name": device.name,
            **{field: data.pop(field) for field in DEVICE_FIELDS},
        },
        "connected": connected,
        # While disconnected the state is the last the desk reported
        "stale": not connected,
        "state": data,
        "recent_notification_headers": device.recent_notification_headers,
    }
    return _scrub_address(
        async_redact_data(diagnostics, TO_REDACT), entry.data[CONF_ADDRESS]
    )


def _scrub_address(value: Any, address: str) -> Any:
    """Redact the address wherever it appears in a string, such as a name.

    Some Bluetooth stacks name an unnamed device after its address, written
    with colons, dashes or no separator, in either case.
    """
    if isinstance(value, dict):
        return {key: _scrub_address(item, address) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_address(item, address) for item in value]
    if isinstance(value, str):
        pattern = "[:-]?".join(re.escape(part) for part in address.split(":"))
        return re.sub(pattern, REDACTED, value, flags=re.IGNORECASE)
    return value
