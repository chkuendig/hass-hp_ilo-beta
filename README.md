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

<h3>🌡️ Hardware Health Sensors</h3>
<ul>
<li><strong>Temperature sensors</strong>: All thermal zones exposed with number prefix stripped from display names (e.g. <code>01-Inlet Ambient</code> → <code>Inlet Ambient</code>)</li>
<li><strong>Fan sensors</strong>: Per-fan speed as percentage</li>
<li><strong>Memory DIMM sensors</strong>: Per installed DIMM — size @ speed as state (e.g. <code>8192 MB @ 1600 MHz</code>), DDR type inferred from speed, location as attribute</li>
<li><strong>Processor sensors</strong>: Status per CPU plus dedicated entities for name, speed, execution technology, and memory technology</li>
<li><strong>NIC sensor</strong>: MAC, IP, gateway, DNS, speed/duplex (merged from <code>nic_information</code> and <code>network_settings</code>)</li>
<li><strong>Storage controller sensors</strong>: Per controller with drive and logical volume details as attributes</li>
<li><strong>BIOS/Hardware aggregate sensor</strong>: Rolled-up hardware health</li>
</ul>
<h3>🔧 Firmware Information</h3>
<p>All firmware components exposed as individual diagnostic sensors, discovered dynamically (no hardcoded key names, works across server generations):</p>
<ul>
<li>System ROM &amp; Redundant System ROM (version + date)</li>
<li>System ROM Bootblock</li>
<li>Intelligent Provisioning</li>
<li>Intelligent Platform Abstraction Data</li>
<li>Server Platform Services (SPS) Firmware</li>
<li>System Programmable Logic Device</li>
</ul>
<h3>📋 Event Logs</h3>
<ul>
<li><strong>iLO Event Log</strong> &amp; <strong>Server Event Log</strong> sensors: worst severity across all entries as state, full log (up to 50 entries, newest first) in attributes</li>
<li>Per-field sensors for last critical entry: description, timestamp, class</li>
<li><strong>Clear iLO Event Log</strong> &amp; <strong>Clear Server Event Log</strong> buttons (requires <code>CONFIG_ILO_PRIV</code> on the iLO user — see below)</li>
</ul>
<h3>🔍 iLO Self-Tests (Health-at-a-Glance)</h3>
<p>One sensor per iLO subsystem showing the iLO's own rolled-up self-test result (OK / Degraded / Failed) for: BIOS, fans, temperature, power supplies, processor, memory, network, storage.</p>
<h3>⚡ Power Monitoring</h3>
<ul>
<li>Present, Average, Minimum, Maximum power readings (Watts) — where supported by iLO firmware</li>
<li>Power Saver mode (AUTO / OS Control / Static High / Static Low)</li>
<li>Power Cap mode with efficiency mode and alert thresholds</li>
</ul>
<h3>🏷️ System Identity</h3>
<ul>
<li>iLO Firmware Version (with management processor type, license, date)</li>
<li>Asset Tag</li>
<li>Server Power-On Time</li>
</ul>
<h3>🔴 Binary Sensors</h3>
<ul>
<li>Per-subsystem health (Memory, Processor, Network, Storage, Temperature, Fan) — fires when any status is Degraded/Failed/Critical/Warning</li>
<li>UID Locator Light status</li>
<li>Critical Temp Remain Off configuration</li>
</ul>

# Installation
Add this repo as a custom repo to HACS and the integration should show up. 

<h2>Required User Actions</h2>
<h3>iLO User Privileges for Log Clearing</h3>
<p>The <strong>Clear iLO Event Log</strong> and <strong>Clear Server Event Log</strong> buttons require the <strong>Configure iLO Settings (<code>CONFIG_ILO_PRIV</code>)</strong> privilege.</p>
<p>To grant it: iLO web UI → <strong>Administration → User Administration</strong> → select the HA user → enable <strong>"Configure iLO Settings"</strong> → Save.</p>
<p>Without this privilege, pressing the buttons will produce a <code>CONFIG_ILO_PRIV required</code> error in the HA log — all other entities work with standard read-only access.</p>
<hr>

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
<hr>
<h2>Bug Fixes Included</h2>

Bug | Fix
-- | --
IloWarning ("No Asset Tag Information") polluting HA logs | Suppressed via warnings.catch_warnings() around every API call
Storage sensor crash when health['storage'] is None | Added isinstance(..., dict) guard
NIC sensor showing unknown | Falls back to MAC address when IP is N/A
NIC MAC mismatch skipping network_settings merge | Removed cross-check — management port and shared NIC use adjacent MACs by design
Storage Health binary sensor showing unknown | Returns False instead of None when data is absent
Memory sensor crash on Gen8 | Rewrote to parse memory_components tuple structure instead of memory_details_summary
Memory Other status triggering health fault | Other excluded from _FAULT_STATUSES
Firmware sensors not found on Gen8 | Dynamic key discovery replaces hardcoded Gen8+ key names
Temperature labels with number prefix | ^\d+- stripped from display name, original kept as unique ID
Entity names missing device prefix | _attr_has_entity_name = True added to base classes
Health/config entities not in diagnostics panel | EntityCategory.DIAGNOSTIC applied to all non-primary entities

<h2>Tested On</h2>
<ul>
<li>HP ProLiant MicroServer Gen8</li>
<li>iLO 4 firmware <code>2.82 Feb 06 2023</code></li>
<li>Intel Xeon E3-1220 V2, mixed DDR3 DIMMs</li>
<li>Home Assistant with <code>python-hpilo</code></li>
</ul>


