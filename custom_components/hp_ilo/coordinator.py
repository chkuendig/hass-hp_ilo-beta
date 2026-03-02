"""DataUpdateCoordinator for HP iLO integration."""
from __future__ import annotations

import warnings
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

    # Server health data (temperatures, fans, processors, memory, NIC, storage)
    health: dict[str, Any] | None = None

    # Power status ("ON" or "OFF")
    power_status: str | None = None

    # Power on time in minutes
    power_on_time: int | None = None

    # Server name
    server_name: str | None = None

    # Host data (SMBIOS entries: model, BIOS version, serial, memory DIMMs, etc.)
    host_data: list[dict] | None = None

    # Network settings (iLO management NIC: IP, MAC, DNS, gateway, etc.)
    network_settings: dict | None = None

    # iLO firmware version, type and license
    fw_version: dict | None = None

    # Present, min, max and average power readings in Watts
    power_readings: dict | None = None

    # UID indicator light status ("ON" / "OFF")
    uid_status: str | None = None

    # Server asset tag string (or None if not set)
    asset_tag: str | None = None

    # Power regulator / saver mode dict  e.g. {'host_power_saver': 'AUTO'}
    power_saver: dict | None = None

    # Power cap, alert thresholds and efficiency mode
    pwreg: dict | None = None

    # Whether server stays powered off after a critical temperature shutdown
    critical_temp_remain_off: bool | None = None

    # iLO event log entries (list of dicts, most-recent first)
    ilo_event_log: list[dict] | None = None

    # Integrated Management Log / server event log entries (most-recent first)
    server_event_log: list[dict] | None = None

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

        Called by the coordinator at the configured interval.
        All entities receive the same data from this single fetch.
        """
        try:
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

        ilo = hpilo.Ilo(
            hostname=self.host,
            login=self.username,
            password=self.password,
            port=self.port,
        )

        data = HpIloData(ilo=ilo)

        def _try(label, fn):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    return fn()
            except (hpilo.IloError, hpilo.IloFeatureNotSupported) as err:
                _LOGGER.debug("Could not get %s: %s", label, err)
            return None

        data.health           = _try("embedded health",       ilo.get_embedded_health)
        data.power_status     = _try("power status",          ilo.get_host_power_status)
        data.power_on_time    = _try("power on time",         ilo.get_server_power_on_time)
        data.server_name      = _try("server name",           ilo.get_server_name)
        data.network_settings = _try("network settings",      ilo.get_network_settings)
        data.host_data        = _try("host data",             ilo.get_host_data)
        data.fw_version       = _try("firmware version",      ilo.get_fw_version)
        data.power_readings   = _try("power readings",        ilo.get_power_readings)
        data.uid_status       = _try("UID status",            ilo.get_uid_status)
        data.power_saver      = _try("power saver status",    ilo.get_host_power_saver_status)
        data.pwreg            = _try("power regulation",      ilo.get_pwreg)
        data.ilo_event_log    = _try("iLO event log",         ilo.get_ilo_event_log)
        data.server_event_log = _try("server event log",      ilo.get_server_event_log)

        raw = _try("critical temp remain off", ilo.get_critical_temp_remain_off)
        if raw is not None:
            data.critical_temp_remain_off = (
                raw.get("critical_temp_remain_off", "No").upper() == "YES"
            )

        # asset tag returns {'asset_tag': 'NL00001'} or {'asset_tag': None}
        raw_tag = _try("asset tag", ilo.get_asset_tag)
        if raw_tag is not None:
            data.asset_tag = raw_tag.get("asset_tag")

        _LOGGER.debug("Successfully fetched data from HP iLO")
        return data
