"""Test that non numeric readings reported by iLO do not break the sensors."""
import copy
import logging

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNKNOWN

from custom_components.hp_ilo.sensor import DOMAIN, _numeric_or_none

from .const import MOCK_CONFIG_FULL, MOCK_ILO_EMBEDDED_HEALTH, MOCK_ILO_POWER_READINGS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (40, 40),
        (40.5, 40.5),
        ("40", 40),
        ("40.5", 40.5),
        ("N/A", None),
        ("", None),
        (None, None),
        (True, None),
        (float("nan"), None),
        (float("inf"), None),
        ([40], None),
    ],
)
def test_numeric_or_none(value, expected):
    """Only finite numbers pass through."""
    assert _numeric_or_none(value) == expected


async def test_not_available_readings_become_unknown(hass, mock_hpilo, caplog):
    """An "N/A" reading gives an unknown state instead of an error."""
    health = copy.deepcopy(MOCK_ILO_EMBEDDED_HEALTH)
    health["temperature"]["02-CPU 1"]["currentreading"] = ("N/A", "N/A")
    health["fans"]["Fan 1"]["speed"] = ("N/A", "N/A")
    mock_hpilo.get_embedded_health.return_value = health
    mock_hpilo.get_power_readings.return_value = {
        **MOCK_ILO_POWER_READINGS,
        "present_power_reading": ("N/A", "N/A"),
    }

    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG_FULL, unique_id=MOCK_CONFIG_FULL["unique_id"]
    )
    entry.add_to_hass(hass)
    with caplog.at_level(logging.ERROR):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.192_168_1_100_02_cpu_1").state == STATE_UNKNOWN
    assert hass.states.get("sensor.192_168_1_100_fan_1").state == STATE_UNKNOWN
    assert hass.states.get("sensor.192_168_1_100_server_power_present").state == STATE_UNKNOWN
    # the other readings are not affected
    assert float(hass.states.get("sensor.192_168_1_100_01_inlet_ambient").state) == 21
    assert float(hass.states.get("sensor.192_168_1_100_fan_2").state) == 18
    assert float(hass.states.get("sensor.192_168_1_100_server_power_average").state) == 106
    assert "Unexpected error updating listener" not in caplog.text
