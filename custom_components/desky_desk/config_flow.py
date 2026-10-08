"""Config flow for Desky Desk integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS, UnitOfLength
from homeassistant.core import callback
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
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Discovered Desky desk: %s", discovery_info)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info

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
            # Discovery reports addresses in upper case
            address = user_input[CONF_ADDRESS].strip().upper()

            # Its discovery card may be open; adding it here closes the card
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            # Try to find the device
            discovery_info = await self._async_get_device(address)
            if discovery_info and await _async_can_connect(discovery_info):
                return self._async_create_desk_entry(discovery_info)

            return self._async_show_user_form({"base": "cannot_connect"})

        # Offer the desks in range that are not set up yet
        configured = self._async_current_ids(include_ignore=False)
        self._discovered_devices = {
            info.address: info
            for info in async_discovered_service_info(self.hass)
            if info.name and "Desky" in info.name and info.address not in configured
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
            address = user_input[CONF_ADDRESS]

            # Its discovery card may be open; adding it here closes the card
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            discovery_info = self._discovered_devices[address]
            if await _async_can_connect(discovery_info):
                return self._async_create_desk_entry(discovery_info)
            errors["base"] = "cannot_connect"

        devices = {
            address: f"{info.name} ({address})"
            for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(devices),
                }
            ),
            errors=errors,
        )

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

    async def _async_get_device(self, address: str) -> BluetoothServiceInfoBleak | None:
        """Get device by address."""
        for discovery_info in async_discovered_service_info(self.hass):
            if discovery_info.address == address:
                return discovery_info
        return None


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
