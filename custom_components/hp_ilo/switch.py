"""Support for HP iLO power switch."""
from __future__ import annotations

import logging

import hpilo

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import CONNECTION_UPNP
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HpIloDataUpdateCoordinator

DOMAIN = "hp_ilo"
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HP iLO switch entities."""
    
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

    switches = []

    # Add power switch if power status is available
    if coordinator.data and coordinator.data.power_status is not None:
        _LOGGER.info("Adding switch for Server Power Control")
        switches.append(
            HpIloPowerSwitch(
                coordinator=coordinator,
                entry=entry,
                device_info=device_info
            )
        )

    async_add_entities(switches, False)


class HpIloPowerSwitch(CoordinatorEntity[HpIloDataUpdateCoordinator], SwitchEntity):
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
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_name = "Server Power Control"
        self._attr_unique_id = f"{entry.data['unique_id']}_set_host_power"

    @property
    def is_on(self) -> bool | None:
        """Return true if the server is powered on."""
        if not self.coordinator.data or not self.coordinator.data.power_status:
            return None
        return self.coordinator.data.power_status == "ON"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the server."""
        if not self.coordinator.data or not self.coordinator.data.ilo:
            _LOGGER.error("No iLO connection available")
            return
            
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.data.ilo.set_host_power,
                True  # host_power=True to turn on
            )
            _LOGGER.info("Successfully powered on server")
            # Request a refresh to update the state
            await self.coordinator.async_request_refresh()
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to power on server: %s", error)
            raise

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the server.
        
        Note: This performs a graceful shutdown. For hard power off,
        use the press_pwr_btn button or hold_pwr_btn method.
        """
        if not self.coordinator.data or not self.coordinator.data.ilo:
            _LOGGER.error("No iLO connection available")
            return
            
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.data.ilo.set_host_power,
                False  # host_power=False to turn off
            )
            _LOGGER.info("Successfully powered off server")
            # Request a refresh to update the state
            await self.coordinator.async_request_refresh()
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to power off server: %s", error)
            raise
