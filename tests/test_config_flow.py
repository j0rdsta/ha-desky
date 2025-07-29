"""Test the Desky Desk config flow."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.desky_desk.const import DOMAIN


@pytest.mark.asyncio
async def test_bluetooth_discovery(hass: HomeAssistant, mock_service_info, enable_custom_integrations):
    """Test discovery via bluetooth."""
    # Mock bluetooth setup to prevent failures
    with patch(
        "homeassistant.components.bluetooth.async_setup", return_value=True
    ), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=mock_service_info,
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "confirm"
        
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Desky"
        assert result["data"] == {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}


@pytest.mark.asyncio
async def test_bluetooth_discovery_already_configured(
    hass: HomeAssistant, mock_service_info, mock_config_entry, enable_custom_integrations
):
    """Test discovery when already configured."""
    mock_config_entry.add_to_hass(hass)
    
    # Mock bluetooth setup to prevent failures
    with patch(
        "homeassistant.components.bluetooth.async_setup", return_value=True
    ), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=mock_service_info,
        )
        
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_user_flow_pick_device(
    hass: HomeAssistant, mock_discovered_service_info, enable_custom_integrations
):
    """Test user flow with device selection."""
    # Mock bluetooth setup to prevent failures
    with patch(
        "homeassistant.components.bluetooth.async_setup", return_value=True
    ), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "pick_device"
        
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
        )
        
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Desky"
        assert result["data"] == {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}


@pytest.mark.asyncio
async def test_user_flow_manual_entry_no_devices(hass: HomeAssistant, enable_custom_integrations):
    """Test user flow with manual entry when no devices discovered."""
    # Mock bluetooth setup to prevent failures
    with patch(
        "homeassistant.components.bluetooth.async_setup", return_value=True
    ), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ), patch(
        "custom_components.desky_desk.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        
        # Test invalid address
        with patch(
            "custom_components.desky_desk.config_flow.ConfigFlow._async_get_device",
            return_value=None,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}
            )
            
            assert result["type"] == FlowResultType.FORM
            assert result["errors"] == {"base": "cannot_connect"}
        
        # Test valid address
        mock_discovery = BluetoothServiceInfoBleak(
            name="Desky",
            address="FF:EE:DD:CC:BB:AA",
            rssi=-50,
            manufacturer_data={},
            service_data={},
            service_uuids=[],
            source="local",
            device=None,
            advertisement=None,
            connectable=True,
            time=0,
            tx_power=None,
        )
        
        with patch(
            "custom_components.desky_desk.config_flow.ConfigFlow._async_get_device",
            return_value=mock_discovery,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}
            )
            
            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["title"] == "Desky"
            assert result["data"] == {CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}


@pytest.mark.asyncio
async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry, mock_discovered_service_info, enable_custom_integrations
):
    """Test user flow when device is already configured."""
    mock_config_entry.add_to_hass(hass)
    
    # Mock bluetooth setup to prevent failures
    with patch(
        "homeassistant.components.bluetooth.async_setup", return_value=True
    ), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "pick_device"
        
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
        )
        
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"