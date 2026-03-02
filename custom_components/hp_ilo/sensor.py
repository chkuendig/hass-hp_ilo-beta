"""Support for HP iLO sensors."""
from __future__ import annotations

import logging
import re
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
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.device_registry import CONNECTION_UPNP
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .coordinator import HpIloDataUpdateCoordinator, HpIloData

DOMAIN = "hp_ilo"
_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "HP ILO"

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

    coordinator: HpIloDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

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
        identifiers=identifiers,
    )

    sensors: list[SensorEntity] = []
    data = coordinator.data

    # ------------------------------------------------------------------ health
    if data.health:
        health = data.health

        # Temperature sensors
        if 'temperature' in health:
            for temp_sensor in health['temperature'].values():
                if temp_sensor.get('status') != 'Not Installed':
                    label = temp_sensor['label']
                    _LOGGER.info("Adding sensor for Temperature Sensor %s", label)
                    sensors.append(HpIloTemperatureSensor(coordinator, entry, device_info, label))

        # Fan sensors
        if 'fans' in health:
            for fan_sensor in health['fans'].values():
                label = fan_sensor['label']
                _LOGGER.info("Adding sensor for Fan %s", label)
                sensors.append(HpIloFanSensor(coordinator, entry, device_info, label))

        # Memory sensors — data lives in memory_components as a list of lists of tuples
        if 'memory' in health:
            memory = health['memory']
            components = memory.get('memory_components', []) if isinstance(memory, dict) else []
            for component in components:
                # Each component is a list of (field_name, {'value': ...}) tuples
                fields = {k: v.get('value') for k, v in component if isinstance(v, dict)}
                location = fields.get('memory_location', '').strip()
                size = fields.get('memory_size', 'Not Installed')
                if location and size and size != 'Not Installed':
                    _LOGGER.info("Adding sensor for Memory %s", location)
                    sensors.append(HpIloMemorySensor(coordinator, entry, device_info, location))

        # Processor sensors
        if 'processors' in health:
            for proc_key, proc_data in health['processors'].items():
                if isinstance(proc_data, dict) and proc_data.get('status', 'Unknown') not in ('Not Installed', 'Unknown'):
                    _LOGGER.info("Adding sensor for Processor %s", proc_key)
                    sensors.append(HpIloProcessorSensor(coordinator, entry, device_info, proc_key))
                    # Per-field sensors for type, speed and execution technology
                    for field, label in (
                        ('name',                f'{proc_key} Name'),
                        ('speed',               f'{proc_key} Speed'),
                        ('execution_technology', f'{proc_key} Execution Technology'),
                        ('memory_technology',    f'{proc_key} Memory Technology'),
                    ):
                        if field in proc_data:
                            sensors.append(HpIloProcessorFieldSensor(
                                coordinator, entry, device_info, proc_key, field, label
                            ))

        # NIC sensors
        if 'nic_information' in health:
            for nic_key, nic_data in health['nic_information'].items():
                if isinstance(nic_data, dict):
                    _LOGGER.info("Adding sensor for NIC %s", nic_key)
                    sensors.append(HpIloNicSensor(coordinator, entry, device_info, nic_key))

        # Storage controller sensors
        if 'storage' in health:
            storage_data = health['storage']
            if not isinstance(storage_data, dict):
                storage_data = {}
            for ctrl_key, ctrl_data in storage_data.items():
                if isinstance(ctrl_data, dict):
                    _LOGGER.info("Adding sensor for Storage Controller %s", ctrl_key)
                    sensors.append(HpIloStorageControllerSensor(coordinator, entry, device_info, ctrl_key))

        # BIOS/Hardware aggregate sensor
        if 'bios_hardware' in health:
            _LOGGER.info("Adding sensor for BIOS Hardware Status")
            sensors.append(HpIloBiosHardwareSensor(coordinator, entry, device_info))

        # Enrich device_info from firmware_information block inside health
        if 'firmware_information' in health:
            fw_info = health['firmware_information']
            if 'iLO' in fw_info:
                device_info['sw_version'] = fw_info['iLO']

            # Explicit label overrides for known keys; all other keys get a
            # cleaned-up label automatically so new firmware components are
            # always picked up regardless of server generation.
            FW_LABEL_OVERRIDES = {
                'iLO':                                        None,  # shown in device_info, skip as sensor
                'System ROM':                                 'System ROM',
                'Redundant System ROM':                       'Redundant System ROM',
                'System ROM Bootblock':                       'System ROM Bootblock',
                'Intelligent Provisioning':                   'Intelligent Provisioning',
                'Intelligent Platform Abstraction Data':      'Intelligent Platform Abstraction Data',
                'Power Management Controller Firmware':       'Power Management Controller Firmware',
                'Power Management Controller Firmware Bootloader': 'Power Management Controller Bootloader',
                'Server Platform Services (SPS) Firmware':   'SPS Firmware',
                'System Programmable Logic Device':           'System Programmable Logic Device',
            }
            for fw_key, fw_val in fw_info.items():
                if fw_val is None:
                    continue
                # Skip iLO — already in device_info
                if fw_key == 'iLO':
                    continue
                fw_label = FW_LABEL_OVERRIDES.get(fw_key, fw_key)
                _LOGGER.info("Adding sensor for firmware component: %s", fw_label)
                sensors.append(HpIloFirmwareComponentSensor(
                    coordinator, entry, device_info, fw_key, fw_label
                ))

        # iLO health-at-a-glance self-test sensors (one per subsystem)
        if 'health_at_a_glance' in health:
            for subsystem_key, subsystem_data in health['health_at_a_glance'].items():
                if isinstance(subsystem_data, dict):
                    label = subsystem_key.replace('_', ' ').title()
                    _LOGGER.info("Adding health-at-a-glance sensor for: %s", label)
                    sensors.append(HpIloHealthAtAGlanceSensor(
                        coordinator, entry, device_info, subsystem_key, label
                    ))

    # ---------------------------------------------------------------- host data
    if data.host_data:
        for smbios_value in data.host_data:
            if smbios_value.get('type') == 0:
                device_info['hw_version'] = f"{smbios_value.get('Family', '')} {smbios_value.get('Date', '')}"
            if smbios_value.get('type') == 1:
                device_info['model'] = smbios_value.get('Product Name')

    # --------------------------------------------------------------- fw version
    if data.fw_version:
        _LOGGER.info("Adding sensor for iLO Firmware")
        sensors.append(HpIloFirmwareSensor(coordinator, entry, device_info))
        # Also enrich device_info
        if 'firmware_version' in data.fw_version:
            device_info['sw_version'] = data.fw_version['firmware_version']

    # ------------------------------------------------------------ power sensors
    if data.power_on_time is not None:
        _LOGGER.info("Adding sensor for Server Power On time")
        sensors.append(HpIloPowerOnTimeSensor(coordinator, entry, device_info))

    if data.power_readings is not None:
        _LOGGER.info("Adding power reading sensors")
        for reading_key, label in (
            ('present_power_reading', 'Present Power'),
            ('average_power_reading', 'Average Power'),
            ('minimum_power_reading', 'Minimum Power'),
            ('maximum_power_reading', 'Maximum Power'),
        ):
            if reading_key in data.power_readings:
                sensors.append(HpIloPowerReadingSensor(coordinator, entry, device_info, reading_key, label))

    # -------------------------------------------------------------- power saver
    if data.power_saver is not None:
        _LOGGER.info("Adding sensor for Power Saver mode")
        sensors.append(HpIloPowerSaverSensor(coordinator, entry, device_info))

    # ------------------------------------------------------------------- pwreg
    if data.pwreg is not None:
        _LOGGER.info("Adding sensor for Power Regulation")
        sensors.append(HpIloPowerRegSensor(coordinator, entry, device_info))

    # ---------------------------------------------------------------- asset tag
    # Always add if the API call succeeded (value may be None = not set)
    if data.asset_tag is not None:
        _LOGGER.info("Adding sensor for Asset Tag")
        sensors.append(HpIloAssetTagSensor(coordinator, entry, device_info))

    # ------------------------------------------------------------ event log sensors
    if data.ilo_event_log is not None:
        _LOGGER.info("Adding sensors for iLO Event Log")
        sensors.append(HpIloEventLogSensor(coordinator, entry, device_info, "ilo"))
        for field, label in (
            ('description', 'iLO Event Log Last Description'),
            ('last_update',  'iLO Event Log Last Timestamp'),
            ('class',        'iLO Event Log Last Class'),
        ):
            sensors.append(HpIloEventLogFieldSensor(coordinator, entry, device_info, "ilo", field, label))

    if data.server_event_log is not None:
        _LOGGER.info("Adding sensors for Server Event Log")
        sensors.append(HpIloEventLogSensor(coordinator, entry, device_info, "server"))
        for field, label in (
            ('description', 'Server Event Log Last Description'),
            ('last_update',  'Server Event Log Last Timestamp'),
            ('class',        'Server Event Log Last Class'),
        ):
            sensors.append(HpIloEventLogFieldSensor(coordinator, entry, device_info, "server", field, label))

    async_add_entities(sensors, False)


# ---------------------------------------------------------------------------
# Base helper
# ---------------------------------------------------------------------------

class _HpIloSensor(CoordinatorEntity[HpIloDataUpdateCoordinator], SensorEntity):
    """Shared base for all HP iLO sensor entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        unique_suffix: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_name = name
        self._attr_unique_id = f"{entry.data['unique_id']}_{unique_suffix}"


# ---------------------------------------------------------------------------
# Health sensors (temperature, fan, memory, processor, NIC, storage, BIOS)
# ---------------------------------------------------------------------------

class HpIloTemperatureSensor(_HpIloSensor):
    """HP iLO temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, device_info, sensor_label):
        # Strip leading "NN-" prefix (e.g. "01-Inlet Ambient" → "Inlet Ambient")
        # for the display name; keep the original as unique_id suffix to avoid
        # collisions if two zones happen to share a name after stripping.
        display_name = re.sub(r'^\d+-', '', sensor_label).strip()
        super().__init__(coordinator, entry, device_info, sensor_label, display_name)
        self._sensor_label = sensor_label

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        for sensor_data in self.coordinator.data.health.get('temperature', {}).values():
            if sensor_data.get('label') == self._sensor_label:
                reading = sensor_data.get('currentreading')
                if isinstance(reading, (list, tuple)):
                    return reading[0]
                return reading
        return None


class HpIloFanSensor(_HpIloSensor):
    """HP iLO fan speed sensor."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator, entry, device_info, sensor_label):
        super().__init__(coordinator, entry, device_info, sensor_label, sensor_label)
        self._sensor_label = sensor_label

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        for sensor_data in self.coordinator.data.health.get('fans', {}).values():
            if sensor_data.get('label') == self._sensor_label:
                speed = sensor_data.get('speed')
                if isinstance(speed, (list, tuple)):
                    return speed[0]
                return speed
        return None


class HpIloMemorySensor(_HpIloSensor):
    """HP iLO memory DIMM sensor.

    Data comes from health['memory']['memory_components'] which is a list of
    lists of (field_name, {'value': ...}) tuples — one list per DIMM slot.

    native_value → size (e.g. '8192 MB')
    Attributes   → location, speed
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:memory"

    def __init__(self, coordinator, entry, device_info, location: str):
        # Use location string as both unique suffix and display name
        unique_suffix = "memory_" + location.strip().lower().replace(' ', '_')
        super().__init__(coordinator, entry, device_info, unique_suffix, location.strip())
        self._location = location

    def _get_fields(self) -> dict | None:
        """Return the field dict for this DIMM slot, or None if not found."""
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        memory = self.coordinator.data.health.get('memory', {})
        components = memory.get('memory_components', []) if isinstance(memory, dict) else []
        for component in components:
            fields = {k: v.get('value') for k, v in component if isinstance(v, dict)}
            if fields.get('memory_location', '').strip() == self._location.strip():
                return fields
        return None

    @property
    def native_value(self) -> str | None:
        """Return size @ speed (e.g. '8192 MB @ 1600 MHz')."""
        fields = self._get_fields()
        if not fields:
            return None
        size = fields.get('memory_size', '')
        speed = fields.get('memory_speed', '')
        if size and speed and speed != '0 MHz':
            return f"{size} @ {speed}"
        return size or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fields = self._get_fields()
        if not fields:
            return {}
        attrs: dict[str, Any] = {}
        if 'memory_location' in fields:
            attrs['location'] = fields['memory_location'].strip()
        size = fields.get('memory_size', '')
        speed = fields.get('memory_speed', '')
        if size:
            attrs['size'] = size
        if speed and speed != '0 MHz':
            attrs['speed'] = speed
            # Infer DDR generation from speed
            try:
                mhz = int(speed.replace('MHz', '').strip())
                if mhz <= 1066:
                    attrs['type'] = 'DDR2'
                elif mhz <= 1866:
                    attrs['type'] = 'DDR3'
                elif mhz <= 3200:
                    attrs['type'] = 'DDR4'
                else:
                    attrs['type'] = 'DDR5'
            except ValueError:
                pass
        return attrs


class HpIloProcessorSensor(_HpIloSensor):
    """HP iLO CPU/processor sensor.

    native_value → health status (OK / Degraded / …)
    Attributes   → name, speed, execution_technology, cache sizes
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cpu-64-bit"

    def __init__(self, coordinator, entry, device_info, proc_key):
        super().__init__(coordinator, entry, device_info, f"processor_{proc_key}", proc_key)
        self._proc_key = proc_key

    def _get_proc(self) -> dict | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        return self.coordinator.data.health.get('processors', {}).get(self._proc_key)

    @property
    def name(self) -> str:
        proc = self._get_proc()
        return proc.get('label', self._proc_key) if proc else self._proc_key

    @property
    def native_value(self) -> str | None:
        proc = self._get_proc()
        return proc.get('status') if proc else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        proc = self._get_proc()
        if not proc:
            return {}
        attrs: dict[str, Any] = {}
        for key in ('name', 'speed', 'execution_technology', 'memory_technology',
                    'internal_l1_cache', 'internal_l2_cache', 'internal_l3_cache'):
            if key in proc:
                val = proc[key]
                attrs[key] = val.strip() if isinstance(val, str) else val
        return attrs


class HpIloProcessorFieldSensor(_HpIloSensor):
    """Exposes a single processor field (name, speed, execution_technology, memory_technology)
    as a dedicated HA entity so it appears in the diagnostics panel.

    native_value → the field value, stripped of whitespace
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cpu-64-bit"

    def __init__(self, coordinator, entry, device_info, proc_key: str, field: str, label: str):
        super().__init__(coordinator, entry, device_info, f"processor_{proc_key}_{field}", label)
        self._proc_key = proc_key
        self._field = field

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        proc = self.coordinator.data.health.get('processors', {}).get(self._proc_key)
        if not proc:
            return None
        val = proc.get(self._field)
        return str(val).strip()[:255] if val is not None else None


class HpIloNicSensor(_HpIloSensor):
    """HP iLO NIC sensor.

    Merges nic_information (MAC, port, link status) with network_settings
    (IP, subnet, gateway, DNS, DHCP, speed/duplex) matched by MAC address.

    native_value → IP address when available, otherwise None
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:ethernet"

    def __init__(self, coordinator, entry, device_info, nic_key):
        super().__init__(coordinator, entry, device_info, f"nic_{nic_key}", nic_key)
        self._nic_key = nic_key

    def _get_nic(self) -> dict | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        return self.coordinator.data.health.get('nic_information', {}).get(self._nic_key)

    def _get_ns(self) -> dict | None:
        """Return network_settings for this NIC.

        There is only one iLO management NIC. The MAC addresses reported by
        nic_information and network_settings differ by design (shared NIC vs
        iLO dedicated port share the same physical adapter but have different
        MACs), so we always merge rather than cross-checking.
        """
        return self.coordinator.data.network_settings if self.coordinator.data else None

    @property
    def name(self) -> str:
        nic = self._get_nic()
        if not nic:
            return self._nic_key
        desc = nic.get('port_description', '').strip()
        location = nic.get('location', '').strip()
        port = nic.get('network_port', '').strip()
        return f"{location} {desc} {port}".strip() or self._nic_key

    @property
    def native_value(self) -> str | None:
        """Return IP address if known, MAC address as stable fallback."""
        ns = self._get_ns()
        if ns:
            ip = ns.get('ip_address') or ns.get('ipv4_address')
            if ip and ip not in ('N/A', '0.0.0.0', ''):
                return ip
        nic = self._get_nic()
        if nic:
            ip = nic.get('ip_address')
            if ip and ip not in ('N/A', ''):
                return ip
            # Fall back to MAC address — always present and meaningful
            mac = nic.get('mac_address')
            if mac:
                return mac
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        nic = self._get_nic()
        if nic:
            for key in ('mac_address', 'location', 'network_port', 'port_description', 'status'):
                if key in nic:
                    attrs[key] = nic[key]
        ns = self._get_ns()
        if ns:
            for key in ('ip_address', 'subnet_mask', 'gateway_ip_address',
                        'dns_name', 'domain_name', 'dhcp_enabled',
                        'speed_autoselect', 'nic_speed', 'full_duplex',
                        'ipv6_address', 'ipv6_static_route'):
                val = ns.get(key)
                if val is not None and val not in ('N/A', ''):
                    attrs[key] = val
        return attrs


class HpIloStorageControllerSensor(_HpIloSensor):
    """HP iLO storage controller sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:harddisk"

    def __init__(self, coordinator, entry, device_info, ctrl_key):
        super().__init__(coordinator, entry, device_info, f"storage_{ctrl_key}", ctrl_key)
        self._ctrl_key = ctrl_key

    def _get_ctrl(self) -> dict | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        return self.coordinator.data.health.get('storage', {}).get(self._ctrl_key)

    @property
    def name(self) -> str:
        ctrl = self._get_ctrl()
        return ctrl.get('label', self._ctrl_key) if ctrl else self._ctrl_key

    @property
    def native_value(self) -> str | None:
        ctrl = self._get_ctrl()
        return ctrl.get('status') if ctrl else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ctrl = self._get_ctrl()
        if not ctrl:
            return {}
        return {k: ([str(i) for i in v] if isinstance(v, list) else v)
                for k, v in ctrl.items() if k not in ('label', 'status')}


class HpIloBiosHardwareSensor(_HpIloSensor):
    """HP iLO BIOS/Hardware aggregate health sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "bios_hardware", "BIOS Hardware")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        bios_hw = self.coordinator.data.health.get('bios_hardware')
        if bios_hw is None:
            return None
        return bios_hw.get('status') if isinstance(bios_hw, dict) else str(bios_hw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.coordinator.data.health:
            return {}
        bios_hw = self.coordinator.data.health.get('bios_hardware', {})
        return {k: v for k, v in bios_hw.items() if k != 'status'} if isinstance(bios_hw, dict) else {}


# ---------------------------------------------------------------------------
# Power sensors
# ---------------------------------------------------------------------------

class HpIloPowerOnTimeSensor(_HpIloSensor):
    """HP iLO server power-on duration sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_unit_of_measurement = UnitOfTime.DAYS

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "Server Power On time", "Server Power On time")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.power_on_time if self.coordinator.data else None


class HpIloPowerReadingSensor(_HpIloSensor):
    """HP iLO power reading sensor (present / average / min / max watts)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, device_info, reading_key: str, label: str):
        super().__init__(coordinator, entry, device_info, f"power_{reading_key}", label)
        self._reading_key = reading_key

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data or not self.coordinator.data.power_readings:
            return None
        reading = self.coordinator.data.power_readings.get(self._reading_key)
        if isinstance(reading, (list, tuple)):
            return reading[0]
        return reading


class HpIloPowerSaverSensor(_HpIloSensor):
    """HP iLO power regulator/saver mode sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "power_saver", "Power Saver Mode")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.power_saver:
            return None
        return self.coordinator.data.power_saver.get('host_power_saver')


class HpIloPowerRegSensor(_HpIloSensor):
    """HP iLO power cap / efficiency / alert regulation sensor.

    native_value → power cap mode (OFF / DYNAMIC / STATIC)
    Attributes   → efficiency_mode, alert threshold/duration
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "power_reg", "Power Cap Mode")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.pwreg:
            return None
        pcap = self.coordinator.data.pwreg.get('pcap', {})
        return pcap.get('mode') if isinstance(pcap, dict) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.coordinator.data.pwreg:
            return {}
        pwreg = self.coordinator.data.pwreg
        attrs: dict[str, Any] = {}
        if 'efficiency_mode' in pwreg:
            attrs['efficiency_mode'] = pwreg['efficiency_mode']
        alert = pwreg.get('pwralert', {})
        if isinstance(alert, dict):
            for key in ('type', 'threshold', 'duration'):
                if key in alert:
                    attrs[f'alert_{key}'] = alert[key]
        return attrs


# ---------------------------------------------------------------------------
# iLO identity / configuration sensors
# ---------------------------------------------------------------------------

class HpIloFirmwareSensor(_HpIloSensor):
    """HP iLO firmware version / type / license sensor.

    native_value → firmware version string (e.g. "2.10")
    Attributes   → management_processor, license_type, firmware_date
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "ilo_firmware", "iLO Firmware Version")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.fw_version:
            return None
        return self.coordinator.data.fw_version.get('firmware_version')

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.coordinator.data.fw_version:
            return {}
        return {k: v for k, v in self.coordinator.data.fw_version.items()
                if k != 'firmware_version'}


class HpIloAssetTagSensor(_HpIloSensor):
    """HP iLO server asset tag sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:tag"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "asset_tag", "Asset Tag")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.asset_tag


# ---------------------------------------------------------------------------
# Event log sensors
# ---------------------------------------------------------------------------

class HpIloEventLogSensor(_HpIloSensor):
    """HP iLO event log sensor.

    native_value → worst severity present in the log
                   (Critical > Caution > Informational)
    Attributes   → most_recent (description, class, timestamp of newest entry)
                   entries     (up to 50 most-recent entries, newest first)
                   total_entries
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    # Severity ranking — higher index = worse
    _SEVERITY_RANK = ["informational", "repaired", "caution", "critical"]

    _SEVERITY_ICON = {
        "informational": "mdi:information-outline",
        "caution":       "mdi:alert-outline",
        "critical":      "mdi:alert-circle-outline",
    }

    # Maximum number of entries to include in the attribute (HA attr size limit)
    _MAX_ENTRIES = 50

    def __init__(self, coordinator, entry, device_info, log_type: str):
        label = "iLO Event Log" if log_type == "ilo" else "Server Event Log"
        super().__init__(coordinator, entry, device_info, f"{log_type}_event_log", label)
        self._log_type = log_type

    def _get_log(self) -> list[dict] | None:
        if not self.coordinator.data:
            return None
        return (self.coordinator.data.ilo_event_log
                if self._log_type == "ilo"
                else self.coordinator.data.server_event_log)

    @property
    def icon(self) -> str:
        severity = (self.native_value or "").lower()
        return self._SEVERITY_ICON.get(severity, "mdi:text-box-outline")

    @property
    def native_value(self) -> str | None:
        """Return the worst severity found across all log entries."""
        log = self._get_log()
        if not log:
            return None
        worst_rank = -1
        worst_severity = None
        for entry in log:
            severity = (entry.get('severity') or '').lower()
            rank = self._SEVERITY_RANK.index(severity) if severity in self._SEVERITY_RANK else 0
            if rank > worst_rank:
                worst_rank = rank
                worst_severity = entry.get('severity')
        return worst_severity

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        log = self._get_log()
        if not log:
            return {}

        # Most recent entry (last in list)
        newest = log[-1]
        most_recent = {
            'severity':       newest.get('severity'),
            'description':    newest.get('description'),
            'class':          newest.get('class'),
            'last_update':    newest.get('last_update'),
            'initial_update': newest.get('initial_update'),
            'count':          newest.get('count'),
        }

        # Full log, newest first, capped at _MAX_ENTRIES
        entries = []
        for e in reversed(log[-self._MAX_ENTRIES:]):
            entries.append({
                k: v for k, v in e.items()
                if v is not None and v != ''
            })

        return {
            'most_recent':   most_recent,
            'entries':       entries,
            'total_entries': len(log),
        }

class HpIloEventLogFieldSensor(_HpIloSensor):
    """Exposes a single field of the most-recent critical (or worst) event log entry as a HA entity.

    This makes individual fields (description, timestamp, class) visible as
    first-class entities in the HA UI rather than buried inside attributes.

    native_value → the field value from the worst-severity entry in the log,
                   truncated to 255 chars (HA state limit)
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:text-box-outline"

    _SEVERITY_RANK = ["informational", "repaired", "caution", "critical"]

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        log_type: str,
        field: str,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry, device_info, f"{log_type}_event_log_{field}", label)
        self._log_type = log_type
        self._field = field

    def _get_worst_entry(self) -> dict | None:
        if not self.coordinator.data:
            return None
        log = (self.coordinator.data.ilo_event_log
               if self._log_type == "ilo"
               else self.coordinator.data.server_event_log)
        if not log:
            return None
        worst_rank = -1
        worst_entry = None
        for e in log:
            severity = (e.get('severity') or '').lower()
            rank = self._SEVERITY_RANK.index(severity) if severity in self._SEVERITY_RANK else 0
            if rank > worst_rank:
                worst_rank = rank
                worst_entry = e
        return worst_entry

    @property
    def native_value(self) -> str | None:
        entry = self._get_worst_entry()
        if not entry:
            return None
        val = entry.get(self._field)
        if val is None:
            return None
        # HA state is capped at 255 characters
        return str(val)[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the full worst entry for context."""
        entry = self._get_worst_entry()
        if not entry:
            return {}
        return {k: v for k, v in entry.items() if v is not None and v != ''}


# ---------------------------------------------------------------------------
# Firmware component sensors (from health['firmware_information'])
# ---------------------------------------------------------------------------

class HpIloFirmwareComponentSensor(_HpIloSensor):
    """Sensor for a single firmware component from health['firmware_information'].

    Covers System ROM, Backup ROM, Bootblock, Power Management Controller,
    SPS Firmware, System Programmable Logic Device, etc.

    native_value → version/date string for that component
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        fw_key: str,
        label: str,
    ) -> None:
        # Use a safe unique suffix derived from the key
        unique_suffix = "fw_" + fw_key.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
        super().__init__(coordinator, entry, device_info, unique_suffix, label)
        self._fw_key = fw_key

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        fw_info = self.coordinator.data.health.get('firmware_information', {})
        val = fw_info.get(self._fw_key)
        return str(val)[:255] if val is not None else None


# ---------------------------------------------------------------------------
# Health-at-a-glance self-test sensors (from health['health_at_a_glance'])
# ---------------------------------------------------------------------------

class HpIloHealthAtAGlanceSensor(_HpIloSensor):
    """Sensor for a single subsystem from health['health_at_a_glance'].

    This is the iLO's own rolled-up self-test result per subsystem
    (bios_hardware, fans, memory, network, processor, storage, temperature).

    native_value → status string (OK / Degraded / Failed / Not Installed / …)
    Attributes   → any additional fields iLO returns for that subsystem
                   (e.g. redundancy status)
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _STATUS_ICON = {
        'ok':           'mdi:check-circle-outline',
        'degraded':     'mdi:alert-outline',
        'failed':       'mdi:close-circle-outline',
        'critical':     'mdi:alert-circle-outline',
        'not installed': 'mdi:minus-circle-outline',
    }

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        subsystem_key: str,
        label: str,
    ) -> None:
        super().__init__(coordinator, entry, device_info, f"haag_{subsystem_key}", label)
        self._subsystem_key = subsystem_key

    def _get_data(self) -> dict | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        return self.coordinator.data.health.get('health_at_a_glance', {}).get(self._subsystem_key)

    @property
    def icon(self) -> str:
        status = (self.native_value or '').lower()
        return self._STATUS_ICON.get(status, 'mdi:help-circle-outline')

    @property
    def native_value(self) -> str | None:
        data = self._get_data()
        return data.get('status') if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._get_data()
        if not data:
            return {}
        return {k: v for k, v in data.items() if k != 'status'}
