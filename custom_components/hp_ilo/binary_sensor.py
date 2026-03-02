"""Support for HP iLO binary sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
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
    """Set up HP iLO binary sensor entities."""

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

    binary_sensors = []
    data = coordinator.data

    # ------------------------------------------------------------------ power
    if data and data.power_status is not None:
        _LOGGER.info("Adding binary sensor for Server Power Status")
        binary_sensors.append(HpIloPowerStatusBinarySensor(coordinator, entry, device_info))

    # --------------------------------------------------------------- subsystem health
    if data and data.health:
        health = data.health
        HEALTH_SUBSYSTEMS = [
            ('bios_hardware',   "BIOS Hardware Health"),
            ('memory',          "Memory Health"),
            ('processors',      "Processor Health"),
            ('nic_information', "Network Health"),
            ('storage',         "Storage Health"),
            ('temperature',     "Temperature Health"),
            ('fans',            "Fan Health"),
        ]
        for subsystem_key, sensor_name in HEALTH_SUBSYSTEMS:
            if subsystem_key in health:
                _LOGGER.info("Adding binary sensor for %s", sensor_name)
                binary_sensors.append(
                    HpIloSubsystemHealthBinarySensor(
                        coordinator, entry, device_info, subsystem_key, sensor_name
                    )
                )

    # ------------------------------------------------------------------- UID light
    if data and data.uid_status is not None:
        _LOGGER.info("Adding binary sensor for UID Light")
        binary_sensors.append(HpIloUidLightBinarySensor(coordinator, entry, device_info))

    # -------------------------------------------------------- critical temp remain off
    if data and data.critical_temp_remain_off is not None:
        _LOGGER.info("Adding binary sensor for Critical Temp Remain Off")
        binary_sensors.append(HpIloCriticalTempRemainOffBinarySensor(coordinator, entry, device_info))

    async_add_entities(binary_sensors, False)


# ---------------------------------------------------------------------------
# Base helper
# ---------------------------------------------------------------------------

class _HpIloBinarySensor(CoordinatorEntity[HpIloDataUpdateCoordinator], BinarySensorEntity):
    """Shared base for all HP iLO binary sensor entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, device_info, unique_suffix, name):
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_name = name
        self._attr_unique_id = f"{entry.data['unique_id']}_{unique_suffix}"


# ---------------------------------------------------------------------------
# Power binary sensor
# ---------------------------------------------------------------------------

class HpIloPowerStatusBinarySensor(_HpIloBinarySensor):
    """Binary sensor for HP iLO server power status."""

    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "server_power", "Server Power")
        self._update_state()

    def _handle_coordinator_update(self) -> None:
        self._update_state()
        super()._handle_coordinator_update()

    def _update_state(self) -> None:
        if not self.coordinator.data or self.coordinator.data.power_status is None:
            self._attr_is_on = None
        else:
            self._attr_is_on = self.coordinator.data.power_status == "ON"


# ---------------------------------------------------------------------------
# Subsystem health binary sensor
# ---------------------------------------------------------------------------

class HpIloSubsystemHealthBinarySensor(_HpIloBinarySensor):
    """Binary sensor for HP iLO subsystem health.

    Device class PROBLEM: is_on=True means a fault is detected.
    is_on=False means all statuses are OK (or subsystem is not present).
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    _FAULT_STATUSES = {"Degraded", "Failed", "Critical", "Warning", "Not Redundant"}

    def __init__(self, coordinator, entry, device_info, subsystem_key, sensor_name):
        super().__init__(coordinator, entry, device_info, f"{subsystem_key}_health", sensor_name)
        self._subsystem_key = subsystem_key

    def _collect_statuses(self, data: object) -> list[str]:
        statuses: list[str] = []
        if isinstance(data, dict):
            if 'status' in data and isinstance(data['status'], str):
                statuses.append(data['status'])
            for val in data.values():
                statuses.extend(self._collect_statuses(val))
        elif isinstance(data, list):
            for item in data:
                statuses.extend(self._collect_statuses(item))
        return statuses

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or not self.coordinator.data.health:
            return None
        subsystem_data = self.coordinator.data.health.get(self._subsystem_key)
        # None = subsystem not present → no problem
        if subsystem_data is None:
            return False
        statuses = self._collect_statuses(subsystem_data)
        if not statuses:
            return False
        return any(s in self._FAULT_STATUSES for s in statuses)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.coordinator.data.health:
            return {}
        subsystem_data = self.coordinator.data.health.get(self._subsystem_key)
        if not subsystem_data:
            return {}
        statuses = self._collect_statuses(subsystem_data)
        return {"statuses": list(set(statuses))} if statuses else {}


# ---------------------------------------------------------------------------
# UID indicator light binary sensor
# ---------------------------------------------------------------------------

class HpIloUidLightBinarySensor(_HpIloBinarySensor):
    """Binary sensor for the HP iLO UID (Unit Identification) indicator light.

    is_on=True  → UID light is ON  (server is being identified/located)
    is_on=False → UID light is OFF
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(coordinator, entry, device_info, "uid_light", "UID Light")

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or self.coordinator.data.uid_status is None:
            return None
        return self.coordinator.data.uid_status.upper() == "ON"


# ---------------------------------------------------------------------------
# Critical temperature remain-off binary sensor
# ---------------------------------------------------------------------------

class HpIloCriticalTempRemainOffBinarySensor(_HpIloBinarySensor):
    """Binary sensor for the 'remain off after critical temperature' setting.

    is_on=True  → server will stay powered off after a thermal shutdown
    is_on=False → server will restart automatically after a thermal shutdown
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:thermometer-alert"

    def __init__(self, coordinator, entry, device_info):
        super().__init__(
            coordinator, entry, device_info,
            "critical_temp_remain_off", "Critical Temp Remain Off"
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or self.coordinator.data.critical_temp_remain_off is None:
            return None
        return self.coordinator.data.critical_temp_remain_off
