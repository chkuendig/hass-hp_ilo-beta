# Notice 🚧

This is a WIP component for an updated **HP Integrated Lights-Out (ILO)** component in Home Assistant.  The goal is to add a proper config flow with discovery and expose as much of the functonality of ILO as possible.

There's still a lot from `custom-components/integration_blueprint` in this repo to keep track of a few missing things. It will eventually be cleaned up.


hacs_badge

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# Installation
Add this repo as a custom repo to HACS and the integration should show up. At the moment there's no versioning of releases yet.

# Features

## Discovery
**Status: Done ✅**

For Auto Discovery to work, it has to be enabled in the iLO admin UI: 
![ILO Screenshot](/screenshot_ilo_discovery.png?raw=true )

For development & testing it also makes sense to set the interval low enough (default seems to be 10min)

ILO servers are anouncing themselves on a few of SSDP search targets:

* `urn:schemas-upnp-org:device:Basic:1` with details at `http://[IP]/upnp/BasicDevice.xml` (this implements the [UPnP 
Basic:1.0 Device Definition](http://upnp.org/specs/basic/UPnP-basic-Basic-v1-Device.pdf) standard ). Luckily Home Assistant already implements this as part of the existing SSDP discovery mechanism.
* `urn:dmtf-org:service:redfish-rest:1` with details at `https://[IP]/redfish/v1/` (this implements the [DMTF’s Redfish Standard](https://www.dmtf.org/standards/redfish)). See also https://stackoverflow.com/a/39153603 and https://hewlettpackard.github.io/ilo-rest-api-docs/ilo5/?shell#introduction. This could be added to Home Assistant with [python-redfish-library](https://pypi.org/project/redfish/  ) 
* `urn:www-hp-com:service:Federation:2` - not clear where the details for this will end up at. I also didn't look into the underlying standard.

These all return slightly different data, but none seems to include all the information necessary (i.e. the correct UUID or the port/protocol of the REST api ).

Basic Device seems to be the one most common and is already supported by Home Assistant, so I picked that.


## Configuration
**Status: WIP ⏳** 

The goal is to implement a clean config flow supporting a few things:
- Regular setup flow for discovered devices as well as a manual setup flow.
- Update of IPs and Hostname from discovery in case any of them change.
- Import of existing sensors from configuration.yaml
- It should be possible to enable/disable what sensors and other entities/platforms are added. (since this can quickly get out of hand)


## Platforms
**Status: WIP ⏳**

**This component will set up the following platforms.**

Platform | Description
-- | --
`binary_sensor` | Server power state (ON/OFF).
`sensor` | Temperature sensors, fan speed sensors, power-on time.
`switch` | Server power control (turn on/off).
`button` | Power button press and hold (simulates physical power button).

The existing implementation includes:
- ✅ Automatically generated temperature and fan speed sensors
- ✅ Device entity with system configuration information (model, BIOS, iLO firmware version)
- ✅ Binary sensor for power state
- ✅ Switch for power on/off control
- ✅ Button for power button press (graceful shutdown/power on)
- ✅ Button for power button hold (force power off)
- 🔜 Buttons for [Firmware upgrades](https://seveas.github.io/python-hpilo/firmware.html) and other [power operations](https://seveas.github.io/python-hpilo/power.html) (reset, cold boot, etc.)

### ⚠️ Power Control Entities - Disabled by Default

The following power control entities are **disabled by default** because they can be destructive (e.g., if Home Assistant is running on the same server, you won't be able to turn it back on):

| Entity | Description |
|--------|-------------|
| **Power Button** | Simulates a short press of the physical power button (graceful shutdown when on, power on when off) |
| **Power Button Hold (Force Off)** | Simulates holding the power button - forces immediate hard power off. ⚠️ Can cause data loss! |
| **Server Power Control** (switch) | Turn server on/off via `set_host_power()` |

To enable these entities:
1. Go to **Settings** → **Devices & Services** → **HP iLO**
2. Click on your device
3. Find the disabled entities (shown with a "disabled" badge)
4. Click on the entity and select **Enable**

Related closed PRs in upstream: https://github.com/home-assistant/core/pull/65900, https://github.com/home-assistant/core/pull/32209


## Caching 
**Status: Planned 🔜**

Startup and refresh is currently not optimized, slowing this integration down quite a bit. It also seems that data isn't shared between sensors, meaning the rate limiting is resulting in very coarse grained data once there's more then a handful of sensors active.

## Tests
**Status: Done ✅**

The component includes a comprehensive pytest-based test suite covering configuration flow and integration setup. Mock data is based on real iLO API responses from [python-hpilo's test data](https://github.com/seveas/python-hpilo/tree/main/tests/xml).

### Running Tests

Install test dependencies and run the test suite:

```bash
# Install test dependencies
source venv/bin/activate
pip install -r requirements_test.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_config_flow.py -v

# Run with coverage
pytest tests/ --cov=custom_components.hp_ilo
```


## Strings and Translations
**Status: Planned 🔜**

Config flow should support i18n. 

# integration_blueprint

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![hacs][hacsbadge]][hacs]
![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

_Component to integrate with [hp_ilo][hp_ilo]._
