"""Test hp_ilo init."""
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.const import Platform

from custom_components.hp_ilo.sensor import DOMAIN

from .const import MOCK_CONFIG_FULL


@pytest.mark.asyncio
async def test_setup_unload_and_reload_entry(hass, mock_hpilo):
    """Test entry setup, unload, and reload."""
    # Create a mock entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_FULL,
        unique_id="192.168.1.100",
    )
    config_entry.add_to_hass(hass)

    # Setup the integration
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify it's setup
    assert config_entry.state.value == "loaded"
    assert DOMAIN in hass.data

    # Unload the entry
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify it's unloaded
    assert config_entry.state.value == "not_loaded"

    # Reload the entry
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify it's loaded again
    assert config_entry.state.value == "loaded"


@pytest.mark.asyncio
async def test_setup_creates_domain_entry(hass, mock_hpilo):
    """Test that setup creates domain entry."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_FULL,
        unique_id="192.168.1.100",
    )
    config_entry.add_to_hass(hass)

    # Setup the integration
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Verify domain is initialized
    assert DOMAIN in hass.data
    assert config_entry.entry_id in hass.data[DOMAIN]
    assert config_entry.state.value == "loaded"
