"""Support for HP iLO buttons."""
from __future__ import annotations

import logging

import hpilo

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import CONNECTION_UPNP

from .coordinator import HpIloDataUpdateCoordinator

DOMAIN = "hp_ilo"
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HP iLO button entities."""
    
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

    buttons = [
        HpIloPowerButton(
            coordinator=coordinator,
            entry=entry,
            device_info=device_info
        ),
        HpIloPowerButtonHold(
            coordinator=coordinator,
            entry=entry,
            device_info=device_info
        ),
        HpIloResetButton(
            coordinator=coordinator,
            entry=entry,
            device_info=device_info
        ),
        HpIloClearEventLogButton(
            coordinator=coordinator,
            entry=entry,
            device_info=device_info,
            log_type="ilo",
        ),
        HpIloClearEventLogButton(
            coordinator=coordinator,
            entry=entry,
            device_info=device_info,
            log_type="server",
        ),
    ]

    async_add_entities(buttons, False)


class HpIloPowerButton(ButtonEntity):
    """Representation of an HP iLO power button press.
    
    Simulates a short press of the physical power button.
    When server is off, this turns it on.
    When server is on, this initiates a graceful shutdown.
    
    Note: This entity is disabled by default as it can be destructive
    (e.g., if Home Assistant is running on the same machine).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:power"
    _attr_entity_registry_enabled_default = False  # Disabled by default - destructive action

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "Power Button"
        self._attr_unique_id = f"{entry.data['unique_id']}_press_pwr_btn"

    async def async_press(self) -> None:
        """Press the power button."""
        if not self.coordinator.data or not self.coordinator.data.ilo:
            _LOGGER.error("No iLO connection available")
            return
            
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.data.ilo.press_pwr_btn
            )
            _LOGGER.info("Successfully pressed power button")
            # Request a refresh to update the power state
            await self.coordinator.async_request_refresh()
        except (
            hpilo.IloError,
            hpilo.IloCommunicationError,
        ) as error:
            _LOGGER.error("Failed to press power button: %s", error)
            raise


class HpIloPowerButtonHold(ButtonEntity):
    """Representation of an HP iLO power button long press (hold).
    
    Simulates pressing and holding the physical power button.
    This forces an immediate hard power off, similar to holding
    the power button on a physical machine for several seconds.
    
    WARNING: This can cause data loss! Use only when the server
    is unresponsive and a graceful shutdown is not possible.
    
    Note: This entity is disabled by default as it can be destructive
    (e.g., if Home Assistant is running on the same machine).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:power-cycle"
    _attr_entity_registry_enabled_default = False  # Disabled by default - destructive action

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "Power Button Hold (Force Off)"
        self._attr_unique_id = f"{entry.data['unique_id']}_power_button_hold"

    async def async_press(self) -> None:
        """Press and hold the power button (force power off)."""
        if not self.coordinator.data or not self.coordinator.data.ilo:
            _LOGGER.error("No iLO connection available")
            return
            
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.data.ilo.hold_pwr_btn
            )
            _LOGGER.info("Successfully held power button (force off)")
            # Request a refresh to update the power state
            await self.coordinator.async_request_refresh()
        except (
            hpilo.IloError,
            hpilo.IloCommunicationError,
        ) as error:
            _LOGGER.error("Failed to hold power button: %s", error)
            raise


class HpIloResetButton(ButtonEntity):
    """Representation of an HP iLO server reset button.
    
    Performs a server reset (warm reboot). The server will restart
    without going through a full power cycle.
    
    Note: This entity is disabled by default as it can be disruptive
    (e.g., if Home Assistant is running on the same machine).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart"
    _attr_entity_registry_enabled_default = False  # Disabled by default - disruptive action

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._attr_name = "Reset Server"
        self._attr_unique_id = f"{entry.data['unique_id']}_reset_server"

    async def async_press(self) -> None:
        """Reset the server."""
        if not self.coordinator.data or not self.coordinator.data.ilo:
            _LOGGER.error("No iLO connection available")
            return
            
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.data.ilo.reset_server
            )
            _LOGGER.info("Successfully reset server")
            # Request a refresh to update the state
            await self.coordinator.async_request_refresh()
        except (
            hpilo.IloError,
            hpilo.IloCommunicationError,
        ) as error:
            _LOGGER.error("Failed to reset server: %s", error)
            raise


class HpIloClearEventLogButton(ButtonEntity):
    """Button to clear an iLO or server (IML) event log.

    Clearing the iLO event log calls ilo.clear_ilo_event_log() (RIBCL CLEAR_EVENTLOG).
    Clearing the server event log calls ilo.clear_server_event_log() (RIBCL CLEAR_IML).

    Both buttons are enabled by default — clearing a log is reversible (data is gone,
    but it doesn't affect server operation).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:notification-clear-all"

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        log_type: str,  # "ilo" or "server"
    ) -> None:
        self.coordinator = coordinator
        self._attr_device_info = device_info
        self._log_type = log_type
        if log_type == "ilo":
            self._attr_name = "Clear iLO Event Log"
            self._attr_unique_id = f"{entry.data['unique_id']}_clear_ilo_event_log"
        else:
            self._attr_name = "Clear Server Event Log"
            self._attr_unique_id = f"{entry.data['unique_id']}_clear_server_event_log"

    async def async_press(self) -> None:
        """Clear the selected event log and refresh coordinator data."""
        if not self.coordinator.data or not self.coordinator.data.ilo:
            _LOGGER.error("No iLO connection available")
            return

        ilo = self.coordinator.data.ilo
        method = (
            ilo.clear_ilo_event_log
            if self._log_type == "ilo"
            else ilo.clear_server_event_log
        )
        log_label = "iLO event log" if self._log_type == "ilo" else "server event log"

        try:
            await self.hass.async_add_executor_job(method)
            _LOGGER.info("Successfully cleared %s", log_label)
            await self.coordinator.async_request_refresh()
        except (hpilo.IloError, hpilo.IloCommunicationError) as error:
            _LOGGER.error("Failed to clear %s: %s", log_label, error)
            raise
