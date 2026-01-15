"""DataUpdateCoordinator for HP iLO integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

import hpilo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)

# Update interval - all entities will share this single refresh cycle
UPDATE_INTERVAL = timedelta(seconds=60)


@dataclass
class HpIloData:
    """Class to hold all HP iLO data fetched in a single update cycle."""
    
    # Server health data (temperatures, fans, firmware info, etc.)
    health: dict[str, Any] | None = None
    
    # Power status ("ON" or "OFF")
    power_status: str | None = None
    
    # Power on time in minutes
    power_on_time: int | None = None
    
    # Server name
    server_name: str | None = None
    
    # Host data (SMBIOS entries)
    host_data: list[dict] | None = None
    
    # Raw iLO connection for commands (buttons, switch actions)
    ilo: hpilo.Ilo | None = None


class HpIloDataUpdateCoordinator(DataUpdateCoordinator[HpIloData]):
    """Coordinator to manage fetching HP iLO data from a single endpoint."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = entry
        self.host = entry.data["host"]
        self.port = int(entry.data["port"])
        self.username = entry.data["username"]
        self.password = entry.data["password"]
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"HP iLO ({self.host})",
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> HpIloData:
        """Fetch data from HP iLO.
        
        This is called by the coordinator at the configured interval.
        All entities will receive the same data from this single fetch.
        """
        try:
            # Run the blocking iLO calls in the executor
            return await self.hass.async_add_executor_job(self._fetch_data)
        except hpilo.IloLoginFailed as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except hpilo.IloCommunicationError as err:
            raise UpdateFailed(f"Communication error: {err}") from err
        except hpilo.IloError as err:
            raise UpdateFailed(f"iLO error: {err}") from err

    def _fetch_data(self) -> HpIloData:
        """Fetch all data from HP iLO (runs in executor thread)."""
        _LOGGER.debug("Fetching data from HP iLO at %s:%s", self.host, self.port)
        
        # Create a new iLO connection
        ilo = hpilo.Ilo(
            hostname=self.host,
            login=self.username,
            password=self.password,
            port=self.port,
        )
        
        data = HpIloData(ilo=ilo)
        
        # Fetch all the data we need in one batch
        # Each of these is a separate API call, but they all happen
        # in this single update cycle and the results are cached
        
        # Get embedded health (temperatures, fans, firmware)
        try:
            data.health = ilo.get_embedded_health()
        except (hpilo.IloError, hpilo.IloFeatureNotSupported) as err:
            _LOGGER.debug("Could not get embedded health: %s", err)
        
        # Get power status
        try:
            data.power_status = ilo.get_host_power_status()
        except (hpilo.IloError, hpilo.IloFeatureNotSupported) as err:
            _LOGGER.debug("Could not get power status: %s", err)
        
        # Get power on time
        try:
            data.power_on_time = ilo.get_server_power_on_time()
        except (hpilo.IloError, hpilo.IloFeatureNotSupported) as err:
            _LOGGER.debug("Could not get power on time: %s", err)
        
        # Get server name
        try:
            data.server_name = ilo.get_server_name()
        except (hpilo.IloError, hpilo.IloFeatureNotSupported) as err:
            _LOGGER.debug("Could not get server name: %s", err)
        
        # Get host data (SMBIOS entries for model, BIOS version, etc.)
        try:
            data.host_data = ilo.get_host_data()
        except (hpilo.IloError, hpilo.IloFeatureNotSupported) as err:
            _LOGGER.debug("Could not get host data: %s", err)
        
        _LOGGER.debug("Successfully fetched data from HP iLO")
        return data
