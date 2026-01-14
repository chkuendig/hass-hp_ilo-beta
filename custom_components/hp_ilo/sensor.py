"""Support for information from HP iLO sensors."""
from __future__ import annotations

from datetime import timedelta
import logging

import hpilo
import voluptuous as vol
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from homeassistant.helpers import  template
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
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
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
    UnitOfTemperature,  # Updated import for temperature unit
    UnitOfTime,         # Updated import for time unit
)
from homeassistant.const import (
    CONF_HOST, 
    CONF_NAME, 
    CONF_PORT, 
    CONF_USERNAME, 
    CONF_PASSWORD)
from homeassistant.helpers.device_registry import CONNECTION_UPNP

from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle

DOMAIN = "hp_ilo"
_LOGGER = logging.getLogger(__name__)


DEFAULT_NAME = "HP ILO"

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=300)

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


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the HP iLO sensors."""
    hostname = config[CONF_HOST]
    port = config[CONF_PORT]
    login = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    monitored_variables = config[CONF_MONITORED_VARIABLES]

    # Create a data fetcher to support all of the configured sensors. Then make
    # the first call to init the data and confirm we can connect.
    try:
        hp_ilo_data = HpIloData(hostname, port, login, password)
    except ValueError as error:
        _LOGGER.error(error)
        return

    # Initialize and add all of the sensors.
    devices = []
    for monitored_variable in monitored_variables:
        new_device = HpIloSensor(
            hass=hass,
            hp_ilo_data=hp_ilo_data,
            sensor_name=f"{config[CONF_NAME]} {monitored_variable[CONF_NAME]}",
            sensor_type=monitored_variable[CONF_SENSOR_TYPE],
            sensor_value_template=monitored_variable.get(CONF_VALUE_TEMPLATE),
            unit_of_measurement=monitored_variable.get(CONF_UNIT_OF_MEASUREMENT),
            device_class=monitored_variable.get(CONF_DEVICE_CLASS),
            state_class=monitored_variable.get(CONF_STATE_CLASS),
        )
        devices.append(new_device)

    add_entities(devices, True)

 
class HpIloSensor(SensorEntity):
    """Representation of a HP iLO sensor."""

    def __init__(
        self,
        hass,
        hp_ilo_data,
        sensor_type,
        sensor_name,
        sensor_value_template,
        unit_of_measurement,
        device_class,
        state_class,
        options=None,
    ):
        """Initialize the HP iLO sensor."""
        self._hass = hass
        self._attr_name = sensor_name
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._ilo_function = SENSOR_TYPES[sensor_type][1]
        self.hp_ilo_data = hp_ilo_data
        self._attr_options = options

        if sensor_value_template is not None:
            sensor_value_template.hass = hass
        self._sensor_value_template = sensor_value_template

        _LOGGER.debug("Created HP iLO sensor %r", self)

    def update(self):
        """Get the latest data from HP iLO and updates the states."""
        # Call the API for new data. Each sensor will re-trigger this
        # same exact call, but that's fine. Results should be cached for
        # a short period of time to prevent hitting API limits.
        self.hp_ilo_data.update()
        ilo_data = getattr(self.hp_ilo_data.data, self._ilo_function)()

        if self._sensor_value_template is not None:
            ilo_data = self._sensor_value_template.render(
                ilo_data=ilo_data, parse_result=False
            )

        self._attr_native_value = ilo_data


class HpIloData:
    """Gets the latest data from HP iLO."""

    def __init__(self, host, port, login, password):
        """Initialize the data object."""
        self._host = host
        self._port = port
        self._login = login
        self._password = password

        self.data = None

        self.update()

    # TODO: Check if this used to work for caching - it clearly isn't working (hpilo.Ilo will request the data on demand)
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data from HP iLO."""
        try:
            _LOGGER.warning("Creating hpilo.Ilo with host=%s, port=%s", 
                           self._host, self._port)
            self.data = hpilo.Ilo(
                hostname=self._host,
                login=self._login,
                password=self._password,
                port=self._port
            )
        except (
            hpilo.IloError,
            hpilo.IloCommunicationError,
            hpilo.IloLoginFailed,
        ) as error:
            raise ValueError(f"Unable to init HP ILO, {error}") from error




class HpIloDeviceSensor(HpIloSensor):

    def __init__(
        self,
        hass: HomeAssistant,
        hp_ilo_data: HpIloData,
        sensor_type,
        sensor_name,
        sensor_value_template:template.Template,
        unit_of_measurement,
        device_class,
        state_class,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        options=None
    ) -> None:
        """Initialize the HpIlo entity."""
        super().__init__(hass=hass, hp_ilo_data=hp_ilo_data, sensor_type=sensor_type, sensor_name=sensor_name,
        sensor_value_template=sensor_value_template,unit_of_measurement=unit_of_measurement,
        device_class=device_class,state_class=state_class,options=options)
        self._hass = hass

        self._entry_id = entry.entry_id 
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.data['unique_id']}_{sensor_name}"
    
    
'''
Setup device and sensor entities for a config entry
'''
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

   
    # Create a data fetcher to support all of the configured sensors. Then make
    # the first call to init the data and confirm we can connect.
    # TODO: this should probably be constructed in the ConfigEntry
    try:
        # Port is required from config flow
        port = int(entry.data['port'])
        hp_ilo_data = HpIloData(entry.data['host'], port, entry.data['username'], entry.data['password'])
    except ValueError as error:
        _LOGGER.error(error)
        return

    # config flow sets this to either UUID, serial number or None
    if (unique_id := entry.unique_id) is None:
        unique_id = entry.entry_id

    device_name = entry.data['name']
    # iLO always uses HTTPS, construct URL with host and port
    configuration_url = f"https://{entry.data['host']}:{entry.data['port']}"

    connections= {(CONNECTION_UPNP,unique_id)} #TODO: This is probably the wrong identifier
    identifiers={(DOMAIN, unique_id)} #TODO: This is probably the wrong identifier
    device_info = DeviceInfo(
        name=device_name,
        manufacturer="Hewlett Packard Enterprise", 
        configuration_url=configuration_url, 
        connections=connections, 
        identifiers=identifiers) #TODO: we can probably fill more here if we had proper config data

    sensors: list[SensorEntity] = []

    for sensor_type in SENSOR_TYPES: #these should be configurable in integration config options
            ilo_function = SENSOR_TYPES[sensor_type][1]
            sensor_type_name = SENSOR_TYPES[sensor_type][0]
            try:
                sensor_data = getattr(hp_ilo_data.data,ilo_function )()
            except hpilo.IloNotARackServer as error:
                _LOGGER.info("%s cant be loaded: %s",SENSOR_TYPES[sensor_type][0],error)
                continue
            except hpilo.IloFeatureNotSupported as error:
                _LOGGER.info("%s cant be loaded: %s",SENSOR_TYPES[sensor_type][0],error)
                continue

            if sensor_type == "server_health":
                for health_value_keys in sensor_data:
                    if health_value_keys == 'temperature':
                        for temperature_sensor in sensor_data[health_value_keys].values():
                            if temperature_sensor['status'] != 'Not Installed':
                                _LOGGER.info("Adding sensor for Temperature Sensor %s", temperature_sensor['label'])
                                new_sensor = HpIloDeviceSensor(
                                    hass=hass,
                                    hp_ilo_data=hp_ilo_data,
                                    sensor_name=temperature_sensor['label'],
                                    sensor_type=sensor_type,
                                    sensor_value_template=template.Template('{{ ilo_data.temperature["' + temperature_sensor['label'] + '"].currentreading[0] }}', hass),
                                    unit_of_measurement=UnitOfTemperature.CELSIUS,  # Updated to UnitOfTemperature.CELSIUS
                                    device_class=SensorDeviceClass.TEMPERATURE,
                                    state_class=SensorStateClass.MEASUREMENT,
                                    entry=entry,
                                    device_info=device_info
                                )
                                sensors.append(new_sensor)
                    if(health_value_keys == 'fans'):
                        for fan_sensor in sensor_data[health_value_keys].values():
                            _LOGGER.info("Adding sensor for Fan %s ",fan_sensor['label'])
                            new_sensor = HpIloDeviceSensor(
                                    hass=hass,
                                    hp_ilo_data=hp_ilo_data,
                                    sensor_name=fan_sensor['label'],
                                    sensor_type=sensor_type,
                                    sensor_value_template=template.Template('{{ ilo_data.fans["'+fan_sensor['label']+'"].speed[0] }}', hass),
                                    unit_of_measurement=PERCENTAGE,
                                    device_class=None,# TODO: this shouldn't be a sensor but a FanEntity
                                    state_class=None,# TODO: this shouldn't be a sensor but a FanEntity
                                    entry=entry,
                                    device_info=device_info
                                )
                            new_sensor._attr_icon = "mdi:fan"
                            sensors.append(new_sensor )
                    else:
                        if(health_value_keys == 'firmware_information'):
                            device_info['sw_version'] = sensor_data[health_value_keys]['iLO']
                        _LOGGER.info("%s: %s not yet supported data",sensor_type_name,health_value_keys)
            elif sensor_type == "server_power_on_time":
                _LOGGER.info("Adding sensor for %s", sensor_type_name)
                new_sensor = HpIloDeviceSensor(
                    hass=hass,
                    hp_ilo_data=hp_ilo_data,
                    sensor_name=sensor_type_name,
                    sensor_type=sensor_type,
                    sensor_value_template=template.Template('{{ ilo_data }}', hass),
                    unit_of_measurement=UnitOfTime.SECONDS,  # Updated to UnitOfTime.SECONDS
                    device_class=None,  # TODO: it's not clear what entity is best for this
                    state_class=None,  # TODO: it's not clear what entity is best for this
                    entry=entry,
                    device_info=device_info
                )
                sensors.append(new_sensor)
            elif sensor_type == "server_power_status":
                _LOGGER.info("Adding sensor for %s", sensor_type_name)
                new_sensor = HpIloDeviceSensor(
                    hass=hass,
                    hp_ilo_data=hp_ilo_data,
                    sensor_name=sensor_type_name,
                    sensor_type=sensor_type,
                    sensor_value_template=template.Template('{{ ilo_data}}', hass),
                    unit_of_measurement=None,
                    device_class=SensorDeviceClass.ENUM,#TODO: This should use a real binary sensor entity
                    state_class=None,# TODO:  it's not clear what entity is best for this
                    entry=entry,
                    options=("ON","OFF"),
                    device_info=device_info
                )
                
                sensors.append(new_sensor )
            elif sensor_type == "server_host_data":
                # SMBIOS Entries
                for smbios_value in sensor_data:
                    if smbios_value['type'] == 0: # BIOS Information 
                        device_info['hw_version'] = smbios_value['Family'] + " " +smbios_value[ 'Date']
                    if smbios_value['type'] == 1: # System Information 
                        device_info['model'] = smbios_value['Product Name']
                    if smbios_value['type'] == 4: # 	Processor Information 
                        pass # not sure what to do with this info
                    if smbios_value['type'] == 17: # 	Memory Device 
                        pass # not sure what to do with this info
            else:
                _LOGGER.warning("Automatic config for %s not yet implemented. Values: %s", sensor_type_name,sensor_data)

    async_add_entities(sensors, False)
