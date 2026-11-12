"""Test that SSDP rediscovery does not overwrite an existing hp_ilo entry."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries, data_entry_flow
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo

from custom_components.hp_ilo.sensor import DOMAIN

UDN = "uuid:90e19f36-edcb-5b43-8e4e-7c72a5589293"


def _discovery(ip: str = "192.168.64.210") -> SsdpServiceInfo:
    """Return what an iLO announces: its IP address and the HTTP port."""
    return SsdpServiceInfo(
        ssdp_usn=f"{UDN}::upnp:rootdevice",
        ssdp_st="upnp:rootdevice",
        ssdp_udn=UDN,
        ssdp_location=f"http://{ip}:80/upnp/BasicDevice.xml",
        ssdp_server="HP-iLO/1.0 UPnP/1.0",
        upnp={
            "friendlyName": "ILO",
            "modelName": "iLO 4 in ProLiant DL380p Gen8",
        },
    )


def _entry(host: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=UDN,
        data={
            "host": host,
            "port": 443,
            "name": "ILO",
            "unique_id": UDN,
            "username": "Administrator",
            "password": "secret",
        },
    )


async def _discover(hass, ip: str = "192.168.64.210"):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=_discovery(ip)
    )


async def test_rediscovery_keeps_hostname_and_ssl_port(hass):
    """The configured hostname and SSL port survive an SSDP announcement."""
    entry = _entry("ilo.zalin.home")
    entry.add_to_hass(hass)

    result = await _discover(hass)

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "ilo.zalin.home"
    assert entry.data["port"] == 443


async def test_rediscovery_follows_ip_change_but_not_port(hass):
    """A bare IP address follows the device; the port is never overwritten."""
    entry = _entry("192.168.64.99")
    entry.add_to_hass(hass)

    result = await _discover(hass, "192.168.64.210")

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "192.168.64.210"
    assert entry.data["port"] == 443
    assert entry.data["name"] == "ILO"
