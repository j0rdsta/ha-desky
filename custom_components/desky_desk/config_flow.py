"""Config flow for Desky Desk integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .bluetooth import DeskBLEDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Desky Desk."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Discovered Desky desk: %s", discovery_info)
        
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        
        self._discovery_info = discovery_info
        
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name or "Desky Desk",
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                },
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovery_info.name or "Desky Desk",
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            
            # Check if already configured
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            
            # Try to find the device
            discovery_info = await self._async_get_device(address)
            if discovery_info:
                return self.async_create_entry(
                    title=discovery_info.name or "Desky Desk",
                    data={CONF_ADDRESS: address},
                )
            
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_ADDRESS): str,
                }),
                errors={"base": "cannot_connect"},
            )

        # Show list of discovered devices
        self._discovered_devices = {}
        for discovery_info in async_discovered_service_info(self.hass):
            if discovery_info.name and "Desky" in discovery_info.name:
                self._discovered_devices[discovery_info.address] = discovery_info

        if self._discovered_devices:
            return await self.async_step_pick_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): str,
            }),
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle picking a device from a list."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            
            discovery_info = self._discovered_devices[address]
            return self.async_create_entry(
                title=discovery_info.name or "Desky Desk",
                data={CONF_ADDRESS: address},
            )

        devices = {
            address: f"{info.name} ({address})"
            for address, info in self._discovered_devices.items()
        }
        
        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(devices),
            }),
        )

    async def _async_get_device(self, address: str) -> BluetoothServiceInfoBleak | None:
        """Get device by address."""
        for discovery_info in async_discovered_service_info(self.hass):
            if discovery_info.address == address:
                return discovery_info
        return None