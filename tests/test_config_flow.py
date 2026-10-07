"""Test the Desky Desk config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.desky_desk.const import DOMAIN

from . import make_service_info


async def test_bluetooth_discovery(hass: HomeAssistant, mock_service_info):
    """Test discovery via bluetooth."""
    # Mock bluetooth setup to prevent failures
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
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


async def test_bluetooth_discovery_already_configured(
    hass: HomeAssistant,
    mock_service_info,
    mock_config_entry,
):
    """Test discovery when already configured."""
    mock_config_entry.add_to_hass(hass)

    # Mock bluetooth setup to prevent failures
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_BLUETOOTH},
            data=mock_service_info,
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


async def test_user_flow_pick_device(hass: HomeAssistant, mock_discovered_service_info):
    """Test user flow with device selection."""
    # Mock bluetooth setup to prevent failures
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
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


async def test_user_flow_manual_entry_no_devices(hass: HomeAssistant):
    """Test user flow with manual entry when no devices discovered."""
    # Mock bluetooth setup to prevent failures
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
        patch(
            "custom_components.desky_desk.config_flow.async_discovered_service_info",
            return_value=[],
        ),
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
        mock_discovery = make_service_info(address="FF:EE:DD:CC:BB:AA")

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


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_config_entry,
    mock_discovered_service_info,
):
    """Test user flow when device is already configured."""
    mock_config_entry.add_to_hass(hass)

    # Mock bluetooth setup to prevent failures
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
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


async def test_user_flow_ignores_non_desky_devices(hass: HomeAssistant):
    """Test only devices advertising a Desky name are offered for selection."""
    desky = make_service_info(address="AA:BB:CC:DD:EE:FF", name="Desky")
    other = make_service_info(address="11:22:33:44:55:66", name="Kettle")

    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
        patch(
            "custom_components.desky_desk.config_flow.async_discovered_service_info",
            return_value=[other, desky],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pick_device"
    address_field = result["data_schema"].schema[CONF_ADDRESS]
    assert address_field.container == {"AA:BB:CC:DD:EE:FF": "Desky (AA:BB:CC:DD:EE:FF)"}


async def test_user_flow_only_non_desky_devices_shows_manual_form(
    hass: HomeAssistant,
):
    """Test the manual address form is shown when no Desky device is discovered."""
    other = make_service_info(address="11:22:33:44:55:66", name="Kettle")

    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
        patch(
            "custom_components.desky_desk.config_flow.async_discovered_service_info",
            return_value=[other],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] is None


async def test_user_flow_manual_address_matches_discovered_device(
    hass: HomeAssistant,
):
    """Test a manually entered address is resolved against discovered devices."""
    other = make_service_info(address="11:22:33:44:55:66", name="Kettle")
    desky = make_service_info(address="FF:EE:DD:CC:BB:AA", name="Desky Pro")

    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
        patch(
            "custom_components.desky_desk.config_flow.async_discovered_service_info",
            return_value=[],
        ) as mock_discovered,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "user"

        mock_discovered.return_value = [other, desky]
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Desky Pro"
    assert result["data"] == {CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}


async def test_user_flow_manual_address_not_discovered(hass: HomeAssistant):
    """Test a manually entered address that no scanner has seen cannot connect."""
    other = make_service_info(address="11:22:33:44:55:66", name="Kettle")

    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
        patch(
            "custom_components.desky_desk.config_flow.async_discovered_service_info",
            return_value=[other],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}
