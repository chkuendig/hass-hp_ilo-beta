"""Support for HP iLO power switch."""
from __future__ import annotations

import logging

import hpilo

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up HP iLO switch entities."""
    
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

    switches = []

    # Add power switch
    try:
        # Test that we can read power status
        hp_ilo_data.data.get_host_power_status()
        _LOGGER.info("Adding switch for Server Power Control")
        switches.append(
            HpIloPowerSwitch(
                hass=hass,
                hp_ilo_data=hp_ilo_data,
                entry=entry,
                device_info=device_info
            )
        )
    except (hpilo.IloError, hpilo.IloFeatureNotSupported) as error:
        _LOGGER.info("Server Power switch can't be loaded: %s", error)

    async_add_entities(switches, True)


class HpIloPowerSwitch(SwitchEntity):
    """Switch for HP iLO server power control.
    
    This switch allows turning the server on and off via iLO.
    Uses set_host_power() to control power state.
    
    Note: This entity is disabled by default as it can be destructive
    (e.g., if Home Assistant is running on the same machine).
    """

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:power"
    _attr_entity_registry_enabled_default = False  # Disabled by default - destructive action

    def __init__(
        self,
        hass: HomeAssistant,
        hp_ilo_data: HpIloData,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the switch."""
        self._hass = hass
        self.hp_ilo_data = hp_ilo_data
        self._entry_id = entry.entry_id
        self._attr_device_info = device_info
        self._attr_name = "Server Power Control"
        self._attr_unique_id = f"{entry.data['unique_id']}_set_host_power"

    @property
    def is_on(self) -> bool | None:
        """Return true if the server is powered on."""
        return self._attr_is_on

    def update(self) -> None:
        """Get the latest power state from HP iLO."""
        self.hp_ilo_data.update()
        try:
            power_status = self.hp_ilo_data.data.get_host_power_status()
            # get_host_power_status returns "ON" or "OFF"
            self._attr_is_on = power_status == "ON"
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to get power status: %s", error)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the server."""
        try:
            await self._hass.async_add_executor_job(
                self.hp_ilo_data.data.set_host_power,
                True  # host_power=True to turn on
            )
            self._attr_is_on = True
            _LOGGER.info("Successfully powered on server")
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to power on server: %s", error)
            raise

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the server.
        
        Note: This performs a graceful shutdown. For hard power off,
        use the press_pwr_btn button or hold_pwr_btn method.
        """
        try:
            await self._hass.async_add_executor_job(
                self.hp_ilo_data.data.set_host_power,
                False  # host_power=False to turn off
            )
            self._attr_is_on = False
            _LOGGER.info("Successfully powered off server")
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to power off server: %s", error)
            raise
