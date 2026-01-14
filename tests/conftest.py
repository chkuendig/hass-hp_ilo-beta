"""Global fixtures for hp_ilo integration."""
from unittest.mock import patch, MagicMock

import pytest
import hpilo

from .const import (
    MOCK_ILO_HOST_DATA,
    MOCK_ILO_EMBEDDED_HEALTH,
    MOCK_ILO_FW_VERSION,
)

pytest_plugins = "pytest_homeassistant_custom_component"


# This fixture enables loading custom integrations in all tests.
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch(
        "homeassistant.components.persistent_notification.async_create"
    ), patch("homeassistant.components.persistent_notification.async_dismiss"):
        yield


# This fixture mocks the hpilo.Ilo class for successful connections
@pytest.fixture(name="mock_hpilo")
def mock_hpilo_fixture():
    """Mock hpilo.Ilo client."""
    with patch("hpilo.Ilo") as mock_ilo_class:
        mock_ilo = MagicMock()
        mock_ilo.get_fw_version.return_value = MOCK_ILO_FW_VERSION
        mock_ilo.get_host_data.return_value = MOCK_ILO_HOST_DATA
        mock_ilo.get_embedded_health.return_value = MOCK_ILO_EMBEDDED_HEALTH
        mock_ilo_class.return_value = mock_ilo
        yield mock_ilo


# This fixture mocks hpilo.Ilo for authentication failures
@pytest.fixture(name="mock_hpilo_auth_error")
def mock_hpilo_auth_error_fixture():
    """Mock hpilo.Ilo client with authentication error."""
    with patch("hpilo.Ilo") as mock_ilo_class:
        mock_ilo_class.side_effect = hpilo.IloLoginFailed("Invalid credentials")
        yield mock_ilo_class


# This fixture mocks hpilo.Ilo for connection errors
@pytest.fixture(name="mock_hpilo_connection_error")
def mock_hpilo_connection_error_fixture():
    """Mock hpilo.Ilo client with connection error."""
    with patch("hpilo.Ilo") as mock_ilo_class:
        mock_ilo_class.side_effect = hpilo.IloCommunicationError("Cannot connect")
        yield mock_ilo_class

