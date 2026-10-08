"""Config flow for Desky Desk integration."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_last_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS, UnitOfLength
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import voluptuous as vol

from .bluetooth import DeskBLEDevice
from .const import (
    CONF_STANDING_THRESHOLD,
    DEFAULT_STANDING_THRESHOLD,
    DOMAIN,
    MAX_HEIGHT,
    MIN_HEIGHT,
)

_LOGGER = logging.getLogger(__name__)

_ADDRESS = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}")


class DeskyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Desky Desk."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DeskyOptionsFlow:
        """Return the options flow."""
        return DeskyOptionsFlow()

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        # Picker labels by address
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Discovered Desky desk: %s", discovery_info)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": _desk_name(discovery_info)}

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        assert self._discovery_info is not None  # set by async_step_bluetooth
        errors: dict[str, str] = {}
        if user_input is not None:
            if await _async_can_connect(self._discovery_info):
                return self._async_create_desk_entry(self._discovery_info)
            errors["base"] = "cannot_connect"

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            errors=errors,
            description_placeholders={
                "name": _desk_name(self._discovery_info),
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            address = _parse_address(user_input[CONF_ADDRESS])
            if address is None:
                return self._async_show_user_form({CONF_ADDRESS: "invalid_address"})
            if result := await self._async_add_desk(address):
                return result
            return self._async_show_user_form({"base": "cannot_connect"})

        # Offer the desks in range that are not set up yet
        configured = self._async_current_ids(include_ignore=False)
        self._discovered_devices = {
            info.address: f"{info.name} ({info.address})"
            for info in async_discovered_service_info(self.hass)
            if info.name.startswith("Desky") and info.address not in configured
        }

        if self._discovered_devices:
            return await self.async_step_pick_device()

        return self._async_show_user_form()

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle picking a device from a list."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if result := await self._async_add_desk(user_input[CONF_ADDRESS]):
                return result
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices),
                }
            ),
            errors=errors,
        )

    async def _async_add_desk(self, address: str) -> ConfigFlowResult | None:
        """Create the entry for a desk the user chose, or None if it does not answer.

        Its discovery card may be open; adding the desk here closes the card.
        """
        await self.async_set_unique_id(address, raise_on_progress=False)
        self._abort_if_unique_id_configured()

        discovery_info = async_last_service_info(self.hass, address)
        if discovery_info and await _async_can_connect(discovery_info):
            return self._async_create_desk_entry(discovery_info)
        return None

    def _async_show_user_form(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Show the form for entering a desk's address."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )

    def _async_create_desk_entry(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Create the entry for a desk that accepted a connection."""
        return self.async_create_entry(
            title=_desk_name(discovery_info),
            data={CONF_ADDRESS: discovery_info.address},
        )


class DeskyOptionsFlow(OptionsFlowWithReload):
    """Handle the options for a desk; saving them reloads the desk."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the standing threshold."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        threshold = self.config_entry.options.get(
            CONF_STANDING_THRESHOLD, DEFAULT_STANDING_THRESHOLD
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STANDING_THRESHOLD, default=threshold
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_HEIGHT,
                            max=MAX_HEIGHT,
                            step=1,
                            unit_of_measurement=UnitOfLength.CENTIMETERS,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )


async def _async_can_connect(discovery_info: BluetoothServiceInfoBleak) -> bool:
    """Return whether the desk accepts a connection, then disconnect again."""
    device = DeskBLEDevice(discovery_info.device)
    try:
        return await device.connect()
    finally:
        await device.disconnect()


def _desk_name(discovery_info: BluetoothServiceInfoBleak) -> str:
    """Return the name the desk advertises, or a generic one."""
    return discovery_info.name or "Desky Desk"


def _parse_address(text: str) -> str | None:
    """Return an entered address in the upper-case form discovery reports.

    Lower case, dashes and no separators are accepted. Returns None if the text
    is not a Bluetooth address.
    """
    address = format_mac(text.strip()).upper()
    return address if _ADDRESS.fullmatch(address) else None
