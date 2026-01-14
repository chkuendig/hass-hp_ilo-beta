"""Constants for hp_ilo tests."""
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_USERNAME,
)

# Mock config data to be used across multiple tests
MOCK_CONFIG_USER_INPUT = {
    CONF_HOST: "192.168.1.100",
    CONF_PORT: "443",
    CONF_PROTOCOL: "https",
}

MOCK_CONFIG_AUTH_INPUT = {
    CONF_USERNAME: "Administrator",
    CONF_PASSWORD: "test_password",
}

MOCK_CONFIG_FULL = {
    CONF_HOST: "192.168.1.100",
    CONF_PORT: "443",
    CONF_PROTOCOL: "https",
    CONF_USERNAME: "Administrator",
    CONF_PASSWORD: "test_password",
    "name": "192.168.1.100",
    "unique_id": "192.168.1.100",
}

# Mock HP iLO data responses
# These are based on real iLO API responses from python-hpilo test data
# and match the data structures returned by the hpilo library methods.

# Mock HP iLO data responses based on python-hpilo test patterns
# get_fw_version() response
MOCK_ILO_FW_VERSION = {
    "firmware_date": "Feb 17 2017",
    "firmware_version": "2.53",
    "license_type": "iLO Standard",
    "management_processor": "iLO4",
}

# get_host_data() response - returns list of dicts with SMBIOS data
MOCK_ILO_HOST_DATA = [
    {"Product Name": "ProLiant DL360 Gen10"},
    {"Serial Number": "ABC123DEF456"},
    {"UUID": "12345678-1234-1234-1234-123456789012"},
    {"Server Name": "TESTSERVER"},
    {"Power Management Controller Firmware Version": "1.0.0"},
    {"cDNA Asset Tag": "Not Set"},
]

# get_embedded_health() response with realistic health data structure
MOCK_ILO_EMBEDDED_HEALTH = {
    "health_at_a_glance": {
        "battery": {"status": "Not Installed"},
        "bios_hardware": {"status": "OK"},
        "fans": {"status": "OK", "redundancy": "Redundant"},
        "memory": {"status": "OK"},
        "network": {"status": "Link Down"},
        "power_supplies": {"status": "OK", "redundancy": "Redundant"},
        "processor": {"status": "OK"},
        "storage": {"status": "OK"},
        "temperature": {"status": "OK"},
    },
    "fans": {
        "Fan 1": {
            "label": "Fan 1",
            "location": "System",
            "status": "OK",
            "speed": ["18", "Percentage"],
            "zone": "System",
        },
        "Fan 2": {
            "label": "Fan 2",
            "location": "System",
            "status": "OK",
            "speed": ["18", "Percentage"],
            "zone": "System",
        },
    },
    "temperature": {
        "01-Inlet Ambient": {
            "label": "01-Inlet Ambient",
            "location": "Ambient",
            "status": "OK",
            "currentreading": ["21", "Celsius"],
            "caution": ["42", "Celsius"],
            "critical": ["46", "Celsius"],
        },
        "02-CPU 1": {
            "label": "02-CPU 1",
            "location": "CPU",
            "status": "OK",
            "currentreading": ["40", "Celsius"],
            "caution": ["70", "Celsius"],
            "critical": ["N/A", "N/A"],
        },
    },
    "power_supplies": {
        "Power Supply 1": {
            "label": "Power Supply 1",
            "status": "OK",
            "pds": "OK",
            "capacity": "500",
            "firmware_version": "1.00",
        },
        "Power Supply 2": {
            "label": "Power Supply 2",
            "status": "OK",
            "pds": "OK",
            "capacity": "500",
            "firmware_version": "1.00",
        },
    },
    "firmware_information": {
        "System ROM": "U32 v2.42 (01/22/2020)",
        "iLO": "2.53 Feb 17 2017",
        "Power Management Controller": "1.0.0",
    },
    "glance-seperator": None,
}

