"""Test the Desky Desk config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.const import (
    CONF_STANDING_THRESHOLD,
    DEFAULT_STANDING_THRESHOLD,
    DOMAIN,
)

from . import make_service_info


@pytest.fixture(autouse=True)
def mock_flow_desk() -> Generator[MagicMock]:
    """Patch the desk the flow test-connects to with one that answers."""
    with patch(
        "custom_components.desky_desk.config_flow.DeskBLEDevice", autospec=True
    ) as desk_class:
        desk = desk_class.return_value
        desk.connect.return_value = True
        yield desk


@pytest.fixture
def mock_bluetooth_setup(mock_bluetooth: None) -> None:
    """Skip setting up Home Assistant's Bluetooth stack for a flow."""


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
            "custom_components.desky_desk.config_flow.DeskyConfigFlow._async_get_device",
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
            "custom_components.desky_desk.config_flow.DeskyConfigFlow._async_get_device",
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


async def test_options_flow_sets_standing_threshold(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the options flow saves the threshold and reloads the desk with it."""
    coordinator = init_integration.runtime_data
    assert coordinator.posture_tracker.standing_threshold == DEFAULT_STANDING_THRESHOLD

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_STANDING_THRESHOLD: 105}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert init_integration.options == {CONF_STANDING_THRESHOLD: 105}
    assert init_integration.runtime_data is not coordinator
    assert init_integration.runtime_data.posture_tracker.standing_threshold == 105


async def test_options_flow_suggests_current_threshold(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry,
    mock_bluetooth: None,
) -> None:
    """Test the form starts from the saved threshold."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_STANDING_THRESHOLD: 100}
    )

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    schema = result["data_schema"].schema
    (key,) = schema
    assert key == CONF_STANDING_THRESHOLD
    assert key.default() == 100


@pytest.mark.parametrize("threshold", [59, 131, 140])
async def test_options_flow_rejects_out_of_range_threshold(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry,
    mock_bluetooth: None,
    threshold,
) -> None:
    """Test a threshold outside the desk's range is rejected and nothing is saved."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_STANDING_THRESHOLD: threshold}
        )

    assert mock_config_entry.options == {}


async def test_bluetooth_discovery_cannot_connect(
    hass: HomeAssistant,
    mock_bluetooth_setup: None,
    mock_service_info,
    mock_flow_desk: MagicMock,
) -> None:
    """Test confirming a discovered desk that does not answer shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=mock_service_info,
    )
    mock_flow_desk.connect.return_value = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["errors"] == {"base": "cannot_connect"}
    mock_flow_desk.disconnect.assert_awaited_once()

    mock_flow_desk.connect.return_value = True
    with patch("custom_components.desky_desk.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}


async def test_pick_device_cannot_connect(
    hass: HomeAssistant,
    mock_bluetooth_setup: None,
    mock_discovered_service_info,
    mock_flow_desk: MagicMock,
) -> None:
    """Test picking a desk that does not answer shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    mock_flow_desk.connect.return_value = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "pick_device"
    assert result["errors"] == {"base": "cannot_connect"}

    mock_flow_desk.connect.return_value = True
    with patch("custom_components.desky_desk.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_manual_address_cannot_connect(
    hass: HomeAssistant, mock_bluetooth_setup: None, mock_flow_desk: MagicMock
) -> None:
    """Test a manually entered desk that is seen but does not answer."""
    desky = make_service_info(address="FF:EE:DD:CC:BB:AA", name="Desky Pro")
    with patch(
        "custom_components.desky_desk.config_flow.async_discovered_service_info",
        return_value=[],
    ) as mock_discovered:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        mock_discovered.return_value = [desky]
        mock_flow_desk.connect.return_value = False
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: "FF:EE:DD:CC:BB:AA"}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_manual_address_is_normalised(
    hass: HomeAssistant, mock_bluetooth_setup: None, mock_config_entry
) -> None:
    """Test a lowercase address matches a desk already set up from discovery."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.desky_desk.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_ADDRESS: " aa:bb:cc:dd:ee:ff "}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
