"""Test hp_ilo config flow."""
from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_ilo.sensor import DOMAIN

from .const import (
    MOCK_CONFIG_AUTH_INPUT,
    MOCK_CONFIG_USER_INPUT,
    MOCK_CONFIG_FULL,
)


@pytest.fixture(autouse=True)
def bypass_setup_fixture():
    """Prevent setup during config flow tests."""
    with patch(
        "custom_components.hp_ilo.async_setup_entry",
        return_value=True,
    ):
        yield


@pytest.mark.asyncio
async def test_manual_flow_success(hass, mock_hpilo):
    """Test a successful manual config flow."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # Submit host/port/protocol - this moves to confirm or auth step
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_USER_INPUT
    )

    # Could be confirm or auth step depending on implementation
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] in ("confirm", "auth")

    # If confirm step, move to auth
    if result["step_id"] == "confirm":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "auth"

    # Submit credentials
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_AUTH_INPUT
    )

    # Check that the config flow is complete and a new entry is created
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.168.1.100"
    assert result["data"][CONF_USERNAME] == "Administrator"
    assert result["data"][CONF_PASSWORD] == "test_password"


@pytest.mark.asyncio
async def test_manual_flow_auth_error(hass, mock_hpilo_auth_error):
    """Test manual config flow with authentication failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Submit host/port/protocol
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_USER_INPUT
    )

    # If confirm step, move to auth
    if result["step_id"] == "confirm":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

    # Should be at auth step now
    assert result["step_id"] == "auth"

    # Submit invalid credentials - should get auth error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_AUTH_INPUT
    )

    # Should show auth form again with error
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_manual_flow_connection_error(hass, mock_hpilo_connection_error):
    """Test manual config flow with connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Submit host/port/protocol
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_USER_INPUT
    )

    # If confirm step, move to auth
    if result["step_id"] == "confirm":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

    # Should be at auth step now
    assert result["step_id"] == "auth"

    # Submit credentials - should get connection error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_AUTH_INPUT
    )

    # Should show auth form again with error
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_duplicate_entry(hass, mock_hpilo):
    """Test that duplicate entries are prevented."""
    # Create an existing entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_FULL,
        unique_id="192.168.1.100",
    )
    entry.add_to_hass(hass)

    # Try to add the same host again
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_CONFIG_USER_INPUT
    )

    # Should abort due to duplicate
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
