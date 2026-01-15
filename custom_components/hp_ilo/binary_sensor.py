"""Support for HP iLO binary sensors."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up HP iLO binary sensor entities."""
    
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

    binary_sensors = []

    # Add power status binary sensor if power status is available
    if coordinator.data and coordinator.data.power_status is not None:
        _LOGGER.info("Adding binary sensor for Server Power Status")
        binary_sensors.append(
            HpIloPowerStatusBinarySensor(
                coordinator=coordinator,
                entry=entry,
                device_info=device_info
            )
        )

    async_add_entities(binary_sensors, False)


class HpIloPowerStatusBinarySensor(CoordinatorEntity[HpIloDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for HP iLO server power status."""

    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(
        self,
        coordinator: HpIloDataUpdateCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_device_info = device_info
        self._attr_name = "Server Power"
        self._attr_unique_id = f"{entry.data['unique_id']}_server_power"
        # Set initial state
        self._update_state()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        super()._handle_coordinator_update()

    def _update_state(self) -> None:
        """Update the binary sensor state from coordinator data."""
        if not self.coordinator.data or self.coordinator.data.power_status is None:
            self._attr_is_on = None
        else:
            # get_host_power_status returns "ON" or "OFF"
            self._attr_is_on = self.coordinator.data.power_status == "ON"
