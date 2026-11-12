"""Support for information from HP iLO sensors."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
from typing import Any

import hpilo
import voluptuous as vol

from homeassistant.helpers import template
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    CONF_STATE_CLASS,
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA,
    STATE_CLASSES_SCHEMA,
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_HOST,
    CONF_MONITORED_VARIABLES,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SENSOR_TYPE,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_USERNAME,
    CONF_VALUE_TEMPLATE,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.device_registry import CONNECTION_UPNP
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util

from .coordinator import HpIloDataUpdateCoordinator, HpIloData

DOMAIN = "hp_ilo"
_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "HP ILO"

# Longest interval between two valid power samples that is still integrated into
# the energy counter. Longer gaps (iLO unreachable, Home Assistant stopped, ...)
# are skipped rather than extrapolated, so the counter never jumps.
MAX_INTEGRATION_GAP = timedelta(minutes=5)

SENSOR_TYPES = {
    "server_name": ["Server Name", "get_server_name"],
    "server_fqdn": ["Server FQDN", "get_server_fqdn"],
    "server_host_data": ["Server Host Data", "get_host_data"],
    "server_oa_info": ["Server Onboard Administrator Info", "get_oa_info"],
    "server_power_status": ["Server Power state", "get_host_power_status"],
    "server_power_readings": ["Server Power readings", "get_power_readings"],
    "server_power_on_time": ["Server Power On time", "get_server_power_on_time"],
    "server_asset_tag": ["Server Asset Tag", "get_asset_tag"],
    "server_uid_status": ["Server UID light", "get_uid_status"],
    "server_health": ["Server Health", "get_embedded_health"],
    "network_settings": ["Network Settings", "get_network_settings"],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_MONITORED_VARIABLES, default=[]): vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_NAME): cv.string,
                        vol.Required(CONF_SENSOR_TYPE): vol.All(
                            cv.string, vol.In(SENSOR_TYPES)
                        ),
                        vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
                        vol.Optional(CONF_VALUE_TEMPLATE): cv.template,
                        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
                        vol.Optional(CONF_STATE_CLASS): STATE_CLASSES_SCHEMA,
                    }
                )
            ],
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_PORT): cv.port,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device and sensor entities for a config entry."""
    
    # Get the coordinator from hass.data
    coordinator: HpIloDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # config flow sets this to either UUID, serial number or None
    if (unique_id := entry.unique_id) is None:
        unique_id = entry.entry_id

    device_name = entry.data['name']
    configuration_url = f"https://{entry.data['host']}:{entry.data['port']}"

    connections = {(CONNECTION_UPNP, unique_id)}
    identifiers = {(DOMAIN, unique_id)}
    device_info = DeviceInfo(
        name=device_name,
        manufacturer="Hewlett Packard Enterprise",
        configuration_url=configuration_url,
        connections=connections,
        identifiers=identifiers
    )

    sensors: list[SensorEntity] = []
    
    # Get initial data from coordinator
    data = coordinator.data
    
    # Process health data for temperature and fan sensors
    if data.health:
        health = data.health
        
        # Temperature sensors
        if 'temperature' in health:
            for temp_sensor in health['temperature'].values():
                if temp_sensor.get('status') != 'Not Installed':
                    label = temp_sensor['label']
                    _LOGGER.info("Adding sensor for Temperature Sensor %s", label)
                    sensors.append(
                        HpIloTemperatureSensor(
                            coordinator=coordinator,
                            entry=entry,
                            device_info=device_info,
                            sensor_label=label,
                        )
                    )
        
        # Fan sensors
        if 'fans' in health:
            for fan_sensor in health['fans'].values():
                label = fan_sensor['label']
                _LOGGER.info("Adding sensor for Fan %s", label)
                sensors.append(
                    HpIloFanSensor(
                        coordinator=coordinator,
                        entry=entry,
                        device_info=device_info,
                        sensor_label=label,
                    )
                )
        
        # Update device_info with firmware version
        if 'firmware_information' in health:
            fw_info = health['firmware_information']
            if 'iLO' in fw_info:
                device_info['sw_version'] = fw_info['iLO']
    
    # Process host data for device info
    if data.host_data:
        for smbios_value in data.host_data:
            if smbios_value.get('type') == 0:  # BIOS Information
                device_info['hw_version'] = f"{smbios_value.get('Family', '')} {smbios_value.get('Date', '')}"
            if smbios_value.get('type') == 1:  # System Information
                device_info['model'] = smbios_value.get('Product Name')
    
    # Power on time sensor
    if data.power_on_time is not None:
        _LOGGER.info("Adding sensor for Server Power On time")
        sensors.append(
            HpIloPowerOnTimeSensor(
                coordinator=coordinator,
                entry=entry,
                device_info=device_info,
            )
        )

    # Power reading sensors
    if data.power_readings is not None:
        power_reading_definitions = {
            "present_power_reading": "Server Power (Present)",
            "average_power_reading": "Server Power (Average)",
            "maximum_power_reading": "Server Power (Maximum)",
            "minimum_power_reading": "Server Power (Minimum)",
        }
        for reading_key, reading_name in power_reading_definitions.items():
            if reading_key in data.power_readings:
                _LOGGER.info("Adding sensor for %s", reading_name)
                sensors.append(
                    HpIloPowerReadingSensor(
                        coordinator=coordinator,
                        entry=entry,
                        device_info=device_info,
                        reading_key=reading_key,
                        reading_name=reading_name,
                    )
                )

        # iLO has no cumulative energy counter: estimate it from the present power
        if "present_power_reading" in data.power_readings:
            _LOGGER.info("Adding sensor for Server Energy")
            sensors.append(
                HpIloEnergySensor(
                    coordinator=coordinator,
                    entry=entry,
                    device_info=device_info,
                )
            )

    # NIC status sensors
    if data.nic_information:
        for nic_key, nic_data in data.nic_information.items():
            mac = nic_data.get("mac_address", "")
            if not mac or mac == "N/A":
                continue
            port_desc = nic_data.get("port_description", "Unknown")
            net_port = nic_data.get("network_port", "Unknown")
            _LOGGER.info("Adding sensor for NIC %s %s", port_desc, net_port)
            sensors.append(
                HpIloNicSensor(
                    coordinator=coordinator,
                    entry=entry,
                    device_info=device_info,
                    nic_key=nic_key,
                    mac_address=mac,
                    port_description=port_desc,
                    network_port=net_port,
                )
            )

    async_add_entities(sensors, False)


class HpIloTemperatureSensor(CoordinatorEntity[HpIloDataUpdateCoordinator], SensorEntity):
    """Representation of an HP iLO temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        sensor_label: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_label = sensor_label
        self._attr_device_info = device_info
        self._attr_name = sensor_label
        self._attr_unique_id = f"{entry.data['unique_id']}_{sensor_label}"

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        
        temps = self.coordinator.data.health.get('temperature', {})
        # Find sensor by label (dict is keyed by index, not label)
        for sensor_data in temps.values():
            if sensor_data.get('label') == self._sensor_label:
                if 'currentreading' in sensor_data:
                    # currentreading is typically a tuple like (25, 'Celsius')
                    reading = sensor_data['currentreading']
                    if isinstance(reading, (list, tuple)) and len(reading) > 0:
                        return reading[0]
                    return reading
        return None


class HpIloFanSensor(CoordinatorEntity[HpIloDataUpdateCoordinator], SensorEntity):
    """Representation of an HP iLO fan sensor."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fan"

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        sensor_label: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_label = sensor_label
        self._attr_device_info = device_info
        self._attr_name = sensor_label
        self._attr_unique_id = f"{entry.data['unique_id']}_{sensor_label}"

    @property
    def native_value(self) -> int | None:
        """Return the current fan speed percentage."""
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        
        fans = self.coordinator.data.health.get('fans', {})
        # Find sensor by label (dict is keyed by index, not label)
        for sensor_data in fans.values():
            if sensor_data.get('label') == self._sensor_label:
                if 'speed' in sensor_data:
                    # speed is typically a tuple like (28, 'Percentage')
                    speed = sensor_data['speed']
                    if isinstance(speed, (list, tuple)) and len(speed) > 0:
                        return speed[0]
                    return speed
        return None


class HpIloPowerOnTimeSensor(CoordinatorEntity[HpIloDataUpdateCoordinator], SensorEntity):
    """Representation of an HP iLO power on time sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_unit_of_measurement = UnitOfTime.DAYS

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_name = "Server Power On time"
        self._attr_unique_id = f"{entry.data['unique_id']}_Server Power On time"

    @property
    def native_value(self) -> int | None:
        """Return the power on time in minutes."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.power_on_time


class HpIloPowerReadingSensor(CoordinatorEntity[HpIloDataUpdateCoordinator], SensorEntity):
    """Representation of an HP iLO power reading sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        reading_key: str,
        reading_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._reading_key = reading_key
        self._attr_device_info = device_info
        self._attr_name = reading_name
        self._attr_unique_id = f"{entry.data['unique_id']}_{reading_key}"

    @property
    def native_value(self) -> int | None:
        """Return the current power reading in Watts."""
        if not self.coordinator.data or not self.coordinator.data.power_readings:
            return None

        reading = self.coordinator.data.power_readings.get(self._reading_key)
        if reading is None:
            return None
        if isinstance(reading, (list, tuple)) and len(reading) > 0:
            return reading[0]
        return reading


class HpIloEnergySensor(CoordinatorEntity[HpIloDataUpdateCoordinator], RestoreSensor):
    """Energy consumed by the server, estimated from the present power reading.

    iLO does not expose a cumulative energy counter, so the instantaneous power
    is integrated over time with the trapezoidal rule on every coordinator
    update. The total is restored after a restart. Intervals during which no
    valid reading is available (iLO unreachable, Home Assistant not running)
    are not counted, so the value never jumps or goes back to zero.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_name = "Server Energy"
        self._attr_unique_id = f"{entry.data['unique_id']}_energy"
        self._energy_kwh = 0.0
        self._last_sample: tuple[datetime, float] | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the previous total and take the first power sample."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data is not None and last_data.native_unit_of_measurement in (
            None,
            UnitOfEnergy.KILO_WATT_HOUR,
        ):
            try:
                restored = float(last_data.native_value)
            except (TypeError, ValueError):
                restored = None
            if restored is not None and math.isfinite(restored) and restored >= 0:
                self._energy_kwh = restored
        self._integrate()

    @property
    def available(self) -> bool:
        """Return True if a valid power reading was received."""
        return super().available and self._present_power() is not None

    @property
    def native_value(self) -> float:
        """Return the energy consumed so far, in kWh."""
        return round(self._energy_kwh, 6)

    def _present_power(self) -> float | None:
        """Return the present power reading in Watts, if valid."""
        if not self.coordinator.data or not self.coordinator.data.power_readings:
            return None
        reading = self.coordinator.data.power_readings.get("present_power_reading")
        if isinstance(reading, (list, tuple)):
            reading = reading[0] if reading else None
        try:
            power = float(reading)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(power) or power < 0:
            return None
        return power

    def _integrate(self) -> None:
        """Add the energy since the previous sample (trapezoidal rule)."""
        power = self._present_power()
        if power is None:
            return
        now = dt_util.utcnow()
        if self._last_sample is not None:
            last_time, last_power = self._last_sample
            elapsed = now - last_time
            if elapsed == timedelta(0):
                return
            if timedelta(0) < elapsed <= MAX_INTEGRATION_GAP:
                self._energy_kwh += (
                    (last_power + power) / 2 * elapsed.total_seconds() / 3_600_000
                )
        self._last_sample = (now, power)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate the new power reading and update the state."""
        self._integrate()
        super()._handle_coordinator_update()


class HpIloNicSensor(CoordinatorEntity[HpIloDataUpdateCoordinator], SensorEntity):
    """Representation of an HP iLO NIC status sensor."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:ethernet"

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        nic_key: str,
        mac_address: str,
        port_description: str,
        network_port: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._nic_key = nic_key
        self._attr_device_info = device_info
        self._attr_name = f"NIC {port_description} {network_port}"
        mac_id = mac_address.replace(":", "").lower()
        self._attr_unique_id = f"{entry.data['unique_id']}_nic_{mac_id}"

    @property
    def native_value(self) -> str | None:
        """Return the NIC status string."""
        nic = self._get_nic_data()
        if nic is None:
            return None
        return nic.get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional NIC attributes."""
        nic = self._get_nic_data()
        if nic is None:
            return None
        return {
            "ip_address": nic.get("ip_address"),
            "mac_address": nic.get("mac_address"),
            "network_port": nic.get("network_port"),
            "port_description": nic.get("port_description"),
            "location": nic.get("location"),
        }

    def _get_nic_data(self) -> dict[str, Any] | None:
        """Return the NIC dict for this sensor from coordinator data."""
        if not self.coordinator.data or not self.coordinator.data.nic_information:
            return None
        return self.coordinator.data.nic_information.get(self._nic_key)
