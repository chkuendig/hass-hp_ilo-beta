# Notice

This is a WIP component for an updated HP Integrated Lights-Out (ILO) component in Home Assistant.  The goal is to add a proper config flow with discovery and expose as much of the functonality of ILO as possible.

There's still a lot from `custom-components/integration_blueprint` in this repo to keep track of a few missing things. It will eventually be cleaned up.

# Features

## Discovery
**Status: Done ✅ **
For Auto Discovery to work, it has to be enabled: 
![ILO Screenshot](/screenshot_ilo_discovery.png?raw=true )

For development & testing it also makes sense to set the interval low enough (default seems to be 10min)

ILO servers are anouncing themselves on a few of SSDP search targets:

* `urn:schemas-upnp-org:device:Basic:1` with details at `http://[IP]/upnp/BasicDevice.xml` (this implements the [UPnP 
Basic:1.0 Device Definition](http://upnp.org/specs/basic/UPnP-basic-Basic-v1-Device.pdf) standard ). Luckily Home Assistant already implements this as part of the existing SSDP discovery mechanism.
* `urn:dmtf-org:service:redfish-rest:1` with details at `https://[IP]/redfish/v1/` (this implements the [DMTF’s Redfish Standard](https://www.dmtf.org/standards/redfish)). See also https://stackoverflow.com/a/39153603 and https://hewlettpackard.github.io/ilo-rest-api-docs/ilo5/?shell#introduction. This could be added to Home Assistant with [python-redfish-library](https://pypi.org/project/redfish/  ) 
* `urn:www-hp-com:service:Federation:2` - not clear where the details for this will end up at. I also didn't look into the underlying standard.

These all return slightly different data, but none seems to include all the information necessary. Basic Device seems to be the one most common and is already supported by Home Assistant, so I picked that.


# Configuration
**Status: WIP ⏳ ** 

The goal is to implement a clean config flow supporting a few things:
- Regular setup flow for discovered devices as well as a manual setup flow.
- Update of IPs and Hostname from discovery in case any of them change.
- Import of existing sensors from configuration.yaml
- It should be possible to enable/disable what sensors and other entities/platforms are added. (since this can quickly get out of hand)


# Platforms
**Status: WIP ⏳ *
The existing sensors only implement the sensor entity. Ideally a few more things would be nice:
- Automatically generate all supported entities automatically. 
- Device entity with as much information as possile about the system configuration
- Binary sensor for firmware update status, power
- Buttons for [Firmware upgrades](
https://seveas.github.io/python-hpilo/firmware.html) and [reboots/restarts](https://seveas.github.io/python-hpilo/power.html) etc.
- Switches for Power on/Off
- Fan entities for fans
There's already a few PRs to improve on this:  https://github.com/home-assistant/core/pull/65900,  https://github.com/home-assistant/core/pull/32209


# Caching 
*Status: Planned 🔜 *
Startup and refresh is currently not optimized, slowing this integration down quite a bit.

# Tests
**Status: Planned 🔜 **
There's actually no tests at all in Home Assistant for this component right now.
Most features should be able to be tested with the existing mock data in `python-hpilo`. 

# Strings and Translations
**Status: Planned 🔜 **
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

**This component will set up the following platforms.**

Platform | Description
-- | --
`binary_sensor` | Show something `True` or `False`.
`sensor` | Show info from blueprint API.
`switch` | Switch something `True` or `False`.

![example][exampleimg]
