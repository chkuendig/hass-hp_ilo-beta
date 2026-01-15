"""Support for HP iLO binary sensors."""
from __future__ import annotations

import logging

import hpilo

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import CONNECTION_UPNP

from .sensor import HpIloData, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HP iLO binary sensor entities."""
    
    try:
        port = int(entry.data['port'])
        hp_ilo_data = HpIloData(
            entry.data['host'], 
            port, 
            entry.data['username'], 
            entry.data['password']
        )
    except ValueError as error:
        _LOGGER.error("Failed to initialize HP iLO data: %s", error)
        return

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

    binary_sensors = []

    # Add power status binary sensor
    try:
        power_status = hp_ilo_data.data.get_host_power_status()
        _LOGGER.info("Adding binary sensor for Server Power Status")
        binary_sensors.append(
            HpIloPowerStatusBinarySensor(
                hass=hass,
                hp_ilo_data=hp_ilo_data,
                entry=entry,
                device_info=device_info
            )
        )
    except (hpilo.IloError, hpilo.IloFeatureNotSupported) as error:
        _LOGGER.info("Server Power Status binary sensor can't be loaded: %s", error)

    async_add_entities(binary_sensors, True)


class HpIloPowerStatusBinarySensor(BinarySensorEntity):
    """Binary sensor for HP iLO server power status."""

    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(
        self,
        hass: HomeAssistant,
        hp_ilo_data: HpIloData,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the binary sensor."""
        self._hass = hass
        self.hp_ilo_data = hp_ilo_data
        self._entry_id = entry.entry_id
        self._attr_device_info = device_info
        self._attr_name = "Server Power"
        self._attr_unique_id = f"{entry.data['unique_id']}_server_power"

    def update(self) -> None:
        """Get the latest data from HP iLO."""
        self.hp_ilo_data.update()
        try:
            power_status = self.hp_ilo_data.data.get_host_power_status()
            # get_host_power_status returns "ON" or "OFF"
            self._attr_is_on = power_status == "ON"
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to get power status: %s", error)
