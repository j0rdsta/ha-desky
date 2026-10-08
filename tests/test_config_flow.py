"""Test the Desky Desk config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

from bleak.exc import BleakError
from homeassistant import config_entries
from homeassistant.components.bluetooth import async_get_advertisement_callback
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.bluetooth import DeskBLEDevice
from custom_components.desky_desk.const import (
    CONF_STANDING_THRESHOLD,
    DEFAULT_STANDING_THRESHOLD,
    DOMAIN,
)

from . import make_service_info

DESK_ADDRESS = "AA:BB:CC:DD:EE:FF"
OTHER_DESK_ADDRESS = "11:22:33:44:55:66"
# A name discovery does not match, so no discovery card opens for it
UNMATCHED_NAME = "Standing desk"


@pytest.fixture(autouse=True)
def mock_flow_desk() -> Generator[MagicMock]:
    """Patch the desk the flow test-connects to with one that answers."""
    with patch(
        "custom_components.desky_desk.config_flow.DeskBLEDevice", autospec=True
    ) as desk_class:
        desk = desk_class.return_value
        desk.connect.return_value = True
        yield desk


async def advertise(
    hass: HomeAssistant, address: str = DESK_ADDRESS, name: str = "Desky"
) -> None:
    """Deliver a desk's advertisement to Home Assistant's Bluetooth stack.

    A name starting with Desky matches the manifest, so Home Assistant opens a
    discovery flow for it, as it does for a real desk in range.
    """
    async_get_advertisement_callback(hass)(make_service_info(address, name))
    # Home Assistant starts discovery flows as background tasks
    await hass.async_block_till_done(wait_background_tasks=True)


def discovery_flows(hass: HomeAssistant) -> list[dict]:
    """Return the open discovery flows, which the UI shows as cards."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == config_entries.SOURCE_BLUETOOTH
    ]


async def start_user_flow(hass: HomeAssistant):
    """Start the flow the way Add integration does."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_confirm_from_discovery_card(hass: HomeAssistant) -> None:
    """Test confirming a desk from its discovery card."""
    await advertise(hass)
    (flow,) = discovery_flows(hass)
    assert flow["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], user_input={}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Desky"
    assert result["data"] == {CONF_ADDRESS: DESK_ADDRESS}
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth")
async def test_discovery_of_configured_desk_aborts(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a desk that is already set up gets no discovery card."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=make_service_info(),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_discovery_card_cannot_connect_then_recovers(
    hass: HomeAssistant, mock_flow_desk: MagicMock
) -> None:
    """Test confirming a desk that does not answer, then answers."""
    await advertise(hass)
    (flow,) = discovery_flows(hass)

    mock_flow_desk.connect.return_value = False
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["errors"] == {"base": "cannot_connect"}
    mock_flow_desk.disconnect.assert_awaited_once()

    mock_flow_desk.connect.return_value = True
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], user_input={}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth")
async def test_probe_releases_the_link_when_the_handshake_fails(
    hass: HomeAssistant,
    mock_establish_connection: MagicMock,
    mock_bleak_client: MagicMock,
) -> None:
    """Test the connection probe leaves no link open when the handshake fails."""
    await advertise(hass)
    (flow,) = discovery_flows(hass)

    # The handshake is the first write, so it fails
    mock_bleak_client.write_gatt_char.side_effect = BleakError("write failed")
    # The real desk class, so the probe runs the real connect()
    with patch("custom_components.desky_desk.config_flow.DeskBLEDevice", DeskBLEDevice):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input={}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    mock_establish_connection.assert_awaited_once()
    mock_bleak_client.disconnect.assert_awaited_once()


@pytest.mark.usefixtures("enable_bluetooth")
async def test_configured_address_entered_by_hand(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test entering a configured desk's address, in any case, aborts."""
    mock_config_entry.add_to_hass(hass)
    result = await start_user_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: " aa:bb:cc:dd:ee:ff "}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_desk_out_of_range_then_in_range(hass: HomeAssistant) -> None:
    """Test an address no adapter can see fails, then works once it is seen."""
    result = await start_user_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}

    await advertise(hass, DESK_ADDRESS, UNMATCHED_NAME)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == UNMATCHED_NAME
    assert result["data"] == {CONF_ADDRESS: DESK_ADDRESS}
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_desk_in_range_refuses_then_accepts(
    hass: HomeAssistant, mock_flow_desk: MagicMock
) -> None:
    """Test an address that is seen but does not answer, then answers."""
    await advertise(hass, DESK_ADDRESS, UNMATCHED_NAME)
    result = await start_user_flow(hass)

    mock_flow_desk.connect.return_value = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_flow_desk.connect.return_value = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_pick_desk_that_has_discovery_card(hass: HomeAssistant) -> None:
    """Test picking a desk by hand while its discovery card is showing."""
    await advertise(hass)
    assert len(discovery_flows(hass)) == 1

    result = await start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick_device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Desky"
    assert result["data"] == {CONF_ADDRESS: DESK_ADDRESS}
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED
    assert discovery_flows(hass) == []
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_pick_desk_cannot_connect_then_recovers(
    hass: HomeAssistant, mock_flow_desk: MagicMock
) -> None:
    """Test picking a desk with a discovery card that does not answer, then answers."""
    await advertise(hass)
    result = await start_user_flow(hass)

    mock_flow_desk.connect.return_value = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick_device"
    assert result["errors"] == {"base": "cannot_connect"}

    mock_flow_desk.connect.return_value = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED
    assert discovery_flows(hass) == []


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_address_of_desk_that_has_discovery_card(hass: HomeAssistant) -> None:
    """Test entering a desk's address while its discovery card is showing."""
    result = await start_user_flow(hass)
    assert result["step_id"] == "user"
    await advertise(hass)
    assert len(discovery_flows(hass)) == 1

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED
    assert discovery_flows(hass) == []


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_picker_lists_only_desks_not_set_up(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the picker leaves out configured desks and devices that are not desks."""
    mock_config_entry.add_to_hass(hass)
    await advertise(hass, DESK_ADDRESS, "Desky")
    await advertise(hass, OTHER_DESK_ADDRESS, "Desky B")
    await advertise(hass, "22:33:44:55:66:77", "Kettle")

    result = await start_user_flow(hass)
    assert result["step_id"] == "pick_device"

    for address in (DESK_ADDRESS, "22:33:44:55:66:77"):
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={CONF_ADDRESS: address}
            )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: OTHER_DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Desky B"
    assert result["result"].unique_id == OTHER_DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth")
async def test_picker_needs_name_starting_with_desky(hass: HomeAssistant) -> None:
    """Test a device whose name only contains Desky is not offered."""
    await advertise(hass, OTHER_DESK_ADDRESS, "My Desky")
    assert discovery_flows(hass) == []

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.usefixtures("enable_bluetooth")
async def test_only_configured_desks_in_range(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the address form replaces the picker when every desk is set up."""
    mock_config_entry.add_to_hass(hass)
    await advertise(hass)

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] is None


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_desk_set_up_from_card_while_picker_open(hass: HomeAssistant) -> None:
    """Test submitting the picker after the desk was added from its card."""
    await advertise(hass)
    result = await start_user_flow(hass)
    assert result["step_id"] == "pick_device"

    (flow,) = discovery_flows(hass)
    await hass.config_entries.flow.async_configure(flow["flow_id"], user_input={})
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
async def test_ignored_desk_can_be_picked(hass: HomeAssistant) -> None:
    """Test a desk the user ignored is still offered, and adding it replaces the ignore."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=DESK_ADDRESS,
        source=config_entries.SOURCE_IGNORE,
        data={},
    ).add_to_hass(hass)
    await advertise(hass)

    result = await start_user_flow(hass)
    assert result["step_id"] == "pick_device"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.source == config_entries.SOURCE_USER


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
@pytest.mark.parametrize(
    "typed",
    ["AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "AA:BB:CC:DD:EE:FF:00", "desk", ""],
)
async def test_typo_in_address(hass: HomeAssistant, typed: str) -> None:
    """Test a mistyped address shows an error, and the corrected one works."""
    await advertise(hass, DESK_ADDRESS, UNMATCHED_NAME)
    result = await start_user_flow(hass)
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: typed}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_ADDRESS: "invalid_address"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DESK_ADDRESS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth", "mock_setup_entry")
@pytest.mark.parametrize(
    "typed",
    ["aa:bb:cc:dd:ee:ff", " AA:BB:CC:DD:EE:FF ", "AA-BB-CC-DD-EE-FF", "aabbccddeeff"],
)
async def test_address_formats_accepted(hass: HomeAssistant, typed: str) -> None:
    """Test common ways of writing an address all find the desk."""
    await advertise(hass, DESK_ADDRESS, UNMATCHED_NAME)
    result = await start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: typed}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: DESK_ADDRESS}
    assert result["result"].unique_id == DESK_ADDRESS
    assert result["result"].state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("enable_bluetooth")
async def test_two_desks_discovered(hass: HomeAssistant) -> None:
    """Test each discovery card names the desk it is for."""
    await advertise(hass, DESK_ADDRESS, "Desky A")
    await advertise(hass, OTHER_DESK_ADDRESS, "Desky B")

    names = {
        flow["context"]["title_placeholders"]["name"] for flow in discovery_flows(hass)
    }
    assert names == {"Desky A", "Desky B"}


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

    # Submitting the form unchanged keeps the saved threshold
    assert result["data_schema"]({}) == {CONF_STANDING_THRESHOLD: 100}


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
