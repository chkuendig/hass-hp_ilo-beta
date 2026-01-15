[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

# HP Integrated Lights-Out (iLO) Integration

_Custom component to integrate HP iLO servers with Home Assistant._

## Features

**This component will set up the following platforms.**

| Platform | Description |
|----------|-------------|
| `binary_sensor` | Server power state (ON/OFF) |
| `sensor` | Temperature sensors, fan speed sensors, power-on time |
| `switch` | Server power control (turn on/off) |
| `button` | Power button press and hold |

## Installation

1. Click install
2. Restart Home Assistant
3. In the HA UI go to **Settings** → **Devices & Services** → click **+ Add Integration** and search for "HP iLO"

## Auto Discovery

iLO servers can be automatically discovered via SSDP if discovery is enabled in the iLO admin interface.

## Configuration

Configuration is done in the UI. You will need:
- iLO hostname or IP address
- Username and password with appropriate permissions

## ⚠️ Power Control Entities

Power control entities (switch and buttons) are **disabled by default** for safety. Enable them manually in the entity settings if needed.
