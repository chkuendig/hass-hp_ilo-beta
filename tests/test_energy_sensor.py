"""Test the estimated energy (kWh) sensor of hp_ilo."""
from datetime import timedelta

import hpilo
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import STATE_UNAVAILABLE, UnitOfEnergy
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.hp_ilo.coordinator import UPDATE_INTERVAL
from custom_components.hp_ilo.sensor import DOMAIN

from .const import MOCK_CONFIG_FULL, MOCK_ILO_POWER_READINGS

UNIQUE_ID = f"{MOCK_CONFIG_FULL['unique_id']}_energy"
STEP = UPDATE_INTERVAL + timedelta(seconds=1)  # margin for the refresh jitter


def _power(watts: int) -> dict:
    """Return power readings with the given present power."""
    return {**MOCK_ILO_POWER_READINGS, "present_power_reading": (watts, "Watts")}


def _kwh(watts: float, seconds: float) -> float:
    """Energy in kWh for a constant power over a duration."""
    return watts * seconds / 3_600_000


async def _setup(hass, mock_hpilo, watts: int = 100) -> str:
    """Set up the integration and return the energy entity id."""
    mock_hpilo.get_power_readings.return_value = _power(watts)
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG_FULL, unique_id=MOCK_CONFIG_FULL["unique_id"]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, UNIQUE_ID)
    assert entity_id is not None
    return entity_id


async def _advance(hass, freezer, delta: timedelta = STEP) -> None:
    """Move time forward and let the coordinator refresh."""
    freezer.tick(delta)
    # fire the timers that are due (the coordinator refresh) at the new time
    async_fire_time_changed(hass, dt_util.utcnow() + delta)
    # the coordinator refresh runs as a background task
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_energy_sensor_attributes(hass, mock_hpilo):
    """The sensor is compatible with the Energy dashboard."""
    entity_id = await _setup(hass, mock_hpilo)
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == 0.0
    assert state.attributes["device_class"] == SensorDeviceClass.ENERGY
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR


async def test_energy_trapezoidal_integration(hass, mock_hpilo, freezer):
    """Power is integrated with the trapezoidal rule."""
    entity_id = await _setup(hass, mock_hpilo, watts=100)

    mock_hpilo.get_power_readings.return_value = _power(200)
    await _advance(hass, freezer)
    expected = _kwh((100 + 200) / 2, STEP.total_seconds())
    assert float(hass.states.get(entity_id).state) == pytest.approx(expected, abs=1e-6)

    await _advance(hass, freezer)  # constant 200 W
    expected += _kwh(200, STEP.total_seconds())
    assert float(hass.states.get(entity_id).state) == pytest.approx(expected, abs=1e-6)


async def test_energy_long_gap_is_skipped(hass, mock_hpilo, freezer):
    """A gap longer than the maximum is not extrapolated (no jump)."""
    entity_id = await _setup(hass, mock_hpilo, watts=100)

    mock_hpilo.get_power_readings.return_value = _power(5000)
    await _advance(hass, freezer, timedelta(hours=2))
    assert float(hass.states.get(entity_id).state) == 0.0

    # Integration resumes from the new baseline
    await _advance(hass, freezer)
    assert float(hass.states.get(entity_id).state) == pytest.approx(
        _kwh(5000, STEP.total_seconds()), abs=1e-6
    )


async def test_energy_unreachable_ilo(hass, mock_hpilo, freezer):
    """Unavailable while iLO is unreachable, then continues without reset."""
    entity_id = await _setup(hass, mock_hpilo, watts=100)
    await _advance(hass, freezer)
    before = float(hass.states.get(entity_id).state)
    assert before == pytest.approx(_kwh(100, STEP.total_seconds()), abs=1e-6)

    mock_hpilo.get_power_readings.side_effect = hpilo.IloCommunicationError("down")
    await _advance(hass, freezer)
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    # Short outage: the missing interval is interpolated
    mock_hpilo.get_power_readings.side_effect = None
    mock_hpilo.get_power_readings.return_value = _power(100)
    await _advance(hass, freezer)
    after = float(hass.states.get(entity_id).state)
    assert after >= before
    assert after == pytest.approx(
        before + _kwh(100, 2 * STEP.total_seconds()), abs=1e-6
    )


async def test_energy_never_decreases_on_invalid_reading(hass, mock_hpilo, freezer):
    """Invalid readings are ignored and never count as zero."""
    entity_id = await _setup(hass, mock_hpilo, watts=100)
    await _advance(hass, freezer)
    before = float(hass.states.get(entity_id).state)

    mock_hpilo.get_power_readings.return_value = {
        **MOCK_ILO_POWER_READINGS,
        "present_power_reading": (None, "Watts"),
    }
    await _advance(hass, freezer)
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    mock_hpilo.get_power_readings.return_value = _power(100)
    await _advance(hass, freezer)
    assert float(hass.states.get(entity_id).state) >= before


@pytest.mark.parametrize(
    ("restored", "expected"),
    [("12.5", 12.5), ("unknown", 0.0), ("-3", 0.0), ("nan", 0.0)],
)
async def test_energy_restored_after_restart(hass, mock_hpilo, restored, expected):
    """The total is restored after a restart; garbage restarts from zero."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_or_create(
        "sensor", DOMAIN, UNIQUE_ID, suggested_object_id="ilo_energy"
    ).entity_id
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, restored),
                {
                    "native_value": restored,
                    "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
                },
            ),
        ),
    )
    assert await _setup(hass, mock_hpilo) == entity_id
    assert float(hass.states.get(entity_id).state) == pytest.approx(expected)


async def test_energy_sensor_not_created_without_power_readings(hass, mock_hpilo):
    """No energy sensor if the iLO does not report power."""
    mock_hpilo.get_power_readings.return_value = None
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG_FULL, unique_id=MOCK_CONFIG_FULL["unique_id"]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get_entity_id("sensor", DOMAIN, UNIQUE_ID) is None
