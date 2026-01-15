# HP iLO Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A drop-in replacement for the [official HP iLO integration](https://www.home-assistant.io/integrations/hp_ilo/) with significant improvements:

- **Config flow** — Set up via the UI instead of YAML configuration
- **Auto-discovery** — Automatically discovers iLO devices on your network via SSDP
- **Statistics support** — Proper `device_class` and `state_class` for long-term statistics ([PR #65900](https://github.com/home-assistant/core/pull/65900))
- **Power control switch** — Turn server on/off via `set_host_power()` ([PR #32209](https://github.com/home-assistant/core/pull/32209))
- **Power button entities** — Simulate physical power button press, hold (force off), and server reset
- **Binary sensor for power state** — Proper ON/OFF binary sensor instead of enum
- **Safe defaults** — All power control entities disabled by default to prevent accidental shutdowns

# Installation

Add this repo as a custom repo to HACS and the integration should show up. 

# Features

## Discovery

For Auto Discovery to work, it has to be enabled in the iLO admin UI: 
![ILO Screenshot](/screenshot_ilo_discovery.png?raw=true )

For development & testing it also makes sense to set the interval low enough (default seems to be 10min)

ILO servers are anouncing themselves on a few of SSDP search targets:

* `urn:schemas-upnp-org:device:Basic:1` with details at `http://[IP]/upnp/BasicDevice.xml` (this implements the [UPnP 
Basic:1.0 Device Definition](http://upnp.org/specs/basic/UPnP-basic-Basic-v1-Device.pdf) standard ). Luckily Home Assistant already implements this as part of the existing SSDP discovery mechanism.
* `urn:dmtf-org:service:redfish-rest:1` with details at `https://[IP]/redfish/v1/` (this implements the [DMTF's Redfish Standard](https://www.dmtf.org/standards/redfish)). See also https://stackoverflow.com/a/39153603 and https://hewlettpackard.github.io/ilo-rest-api-docs/ilo5/?shell#introduction. This could be added to Home Assistant with [python-redfish-library](https://pypi.org/project/redfish/  ) 
* `urn:www-hp-com:service:Federation:2` - not clear where the details for this will end up at. I also didn't look into the underlying standard.

These all return slightly different data, but none seems to include all the information necessary (i.e. the correct UUID or the port/protocol of the REST api ).

Basic Device seems to be the one most common and is already supported by Home Assistant, so I picked that.


## Platforms

**This component will set up the following platforms.**

Platform | Description
-- | --
`binary_sensor` | Server power state (ON/OFF).
`sensor` | Temperature sensors, fan speed sensors, power-on time.
`switch` | Server power control (turn on/off).
`button` | Power button press, hold, and server reset.

The existing implementation includes:
- Automatically generated temperature and fan speed sensors
- Device entity with system configuration information (model, BIOS, iLO firmware version)
- Binary sensor for power state
- Switch for power on/off control
- Button for power button press (graceful shutdown/power on)
- Button for power button hold (force power off)
- Button for server reset (warm reboot)

### ⚠️ Power Control Entities - Disabled by Default

The following power control entities are **disabled by default** because they can be destructive (e.g., if Home Assistant is running on the same server, you won't be able to turn it back on):

| Entity | Description |
|--------|-------------|
| **Power Button** | Simulates a short press of the physical power button (graceful shutdown when on, power on when off) |
| **Power Button Hold (Force Off)** | Simulates holding the power button - forces immediate hard power off. ⚠️ Can cause data loss! |
| **Reset Server** | Performs a warm reboot of the server |
| **Server Power Control** (switch) | Turn server on/off via `set_host_power()` |

To enable these entities:
1. Go to **Settings** → **Devices & Services** → **HP iLO**
2. Click on your device
3. Find the disabled entities (shown with a "disabled" badge)
4. Click on the entity and select **Enable**


## Data Updates & Caching

The integration uses Home Assistant's `DataUpdateCoordinator` pattern for efficient data fetching:
- All data is fetched in a single update cycle (every 60 seconds)
- All entities share the same cached data
- No redundant API calls - temperatures, fans, power status all updated together

## Tests

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

---

# TODO

- **Configuration improvements**
  - Update of IPs and Hostname from discovery in case any of them change
  - Import of existing sensors from configuration.yaml
  - Option to enable/disable what sensors and other entities/platforms are added

- **Strings and Translations** — Config flow should support i18n

- **Firmware Upgrades** — Buttons for [firmware upgrades](https://seveas.github.io/python-hpilo/firmware.html) using the python-hpilo library
