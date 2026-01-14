"""Config flow for HpIlo devices."""
import logging
from urllib.parse import urlparse
import voluptuous as vol
import hpilo 

from homeassistant import config_entries, data_entry_flow
from homeassistant.components import ssdp
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_DESCRIPTION, ATTR_CONFIGURATION_URL, CONF_PORT, CONF_PROTOCOL, CONF_UNIQUE_ID, CONF_USERNAME, CONF_PASSWORD
from .sensor import SENSOR_TYPES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HpIloFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a HpIlo config flow."""

    VERSION = 1

    def __init__(self):
        """Initialize the HpIlo flow."""
        self.device = None
        self.config = None

    async def async_set_device(self, device, raise_on_progress=True):
        """Define a device for the config flow."""
        if device.type not in SENSOR_TYPES:
            _LOGGER.error(
                "Unsupported device: %s. If it worked before, please open "
                "an issue at https://github.com/home-assistant/core/issues",
                hex(device.devtype),
            )
            raise data_entry_flow.AbortFlow("not_supported")

        await self.async_set_unique_id(
            device.mac.hex(), raise_on_progress=raise_on_progress
        )
        self.device = device

        self.context["title_placeholders"] = {
            "name": device.name,
            "model": device.model,
            "host": device.host[0],
        }
    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> FlowResult:
        """Handle a discovered HP iLO device."""
        _LOGGER.info(
                "discovery_info : %s.",
                discovery_info,
            )

        # this is some extra security in case there are other HP Enterprise devices without ILO anouncing themselves.
        if(not discovery_info.ssdp_server or not discovery_info.ssdp_server.startswith("HP-iLO")):
            _LOGGER.error("Not an HP-iLO server")
            return self.async_abort(reason="ssdp_server_error")

   
        parsed_url = urlparse(discovery_info.ssdp_location)
        # Store discovered information without defaults - user will confirm/edit in next step
        # Note: hpilo always uses SSL/TLS, the port determines the connection
        discovered_port = parsed_url.port
        
        self.config = {
            CONF_HOST: parsed_url.hostname,
            CONF_NAME: discovery_info.upnp[ssdp.ATTR_UPNP_FRIENDLY_NAME],
            CONF_DESCRIPTION: discovery_info.upnp[ssdp.ATTR_UPNP_MODEL_NAME],
            CONF_PORT: discovered_port,
            CONF_UNIQUE_ID: discovery_info.ssdp_udn # Will be updated with serial number during auth step
        }
        # we assume port 80 and same IP here. In theory this could also be inferred from a) using friendly name as a hostname or listening for  
        # DSSP NT urn:dmtf-org:service:redfish-rest:1 which announces the admin URL directly (but misses other fields so it would be annoying to combine)
        self.context[ATTR_CONFIGURATION_URL] = parsed_url.scheme + "://"+ parsed_url.netloc

        self._async_abort_entries_match({CONF_HOST: self.config[CONF_HOST]})

        await self.async_set_unique_id(self.config[CONF_UNIQUE_ID])
        self._abort_if_unique_id_configured(updates=self.config)



        self.context["title_placeholders"] = {
            CONF_HOST: self.config[CONF_HOST],
            CONF_NAME: self.config[CONF_NAME],
            CONF_DESCRIPTION: self.config[CONF_DESCRIPTION]
        }


        return await self.async_step_confirm()
        
    async def async_step_confirm(self, user_input=None):
        """Handle user-confirmation of discovered node."""
        if user_input is not None:
            # Update config with user-confirmed values
            self.config[CONF_HOST] = user_input[CONF_HOST]
            self.config[CONF_PORT] = int(user_input[CONF_PORT])
            return await self.async_step_auth()
        
        # Prepare default values from discovery
        data_schema = {
            vol.Required(CONF_HOST, default=self.config.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=self.config.get(CONF_PORT, "")): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
        }
        
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(data_schema),
            description_placeholders={
                CONF_NAME: self.config[CONF_NAME],
                CONF_DESCRIPTION: self.config[CONF_DESCRIPTION],
            },
        )

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""

        if user_input is not None:
            self.config = {}
            self.config[CONF_HOST] = user_input[CONF_HOST]
            self.config[CONF_NAME] = user_input[CONF_HOST].upper()
            # Convert port to integer
            self.config[CONF_PORT] = int(user_input[CONF_PORT])
            # Initialize unique_id with host (will be updated with serial number during auth)
            self.config[CONF_UNIQUE_ID] = user_input[CONF_HOST]
            
            # Check for existing entries with the same host to prevent duplicates
            self._async_abort_entries_match({CONF_HOST: self.config[CONF_HOST]})
            
            return await self.async_step_confirm(user_input)
        else:
            data_schema = {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
            }
            return self.async_show_form(step_id="user",   data_schema=vol.Schema(data_schema))


    async def _async_get_entry(self):
        """Return config entry or update existing config entry."""
        # Set unique ID based on host if not already set
        if self.unique_id is None:
            await self.async_set_unique_id(self.config[CONF_HOST])
        
        # Store unique_id in config data for sensor access
        self.config['unique_id'] = self.unique_id
        
        return self.async_create_entry(
                    title=self.config[CONF_NAME],
                    data=self.config,
                )

    async def async_step_auth(self, user_input=None, errors=None):
        """Authenticate to the device."""
        device = self.device
        errors_dict = {}

        if user_input is not None:
            try:
                self.ilo = hpilo.Ilo(
                    hostname=self.config[CONF_HOST],
                    port=int(self.config[CONF_PORT]),
                    login=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD]
                ) 
                # Verify connection and get serial number for unique_id
                try:
                    host_data = self.ilo.get_host_data()
                    # Extract serial number from host data for stable unique_id
                    # host_data is a list with one dict containing 'Serial Number' field
                    if host_data and len(host_data) > 0:
                        serial_number = host_data[0].get("Serial Number")
                        if serial_number:
                            # Use combination of host and serial number for unique_id
                            # This ensures uniqueness across network changes
                            self.config[CONF_UNIQUE_ID] = f"{self.config[CONF_HOST]}_{serial_number}"
                except Exception as e:
                    _LOGGER.error("Failed to get host data from iLO: %s", e)
                
                self.config[CONF_USERNAME] = user_input[CONF_USERNAME]
                self.config[CONF_PASSWORD] = user_input[CONF_PASSWORD]
               
                return await self._async_get_entry()
                
            except hpilo.IloLoginFailed as error:
                _LOGGER.warning("Authentication failed for %s: %s", self.config[CONF_HOST], error)
                errors_dict["base"] = "invalid_auth"
            except hpilo.IloCommunicationError as error:
                _LOGGER.warning("Communication error with %s: %s", self.config[CONF_HOST], error)
                errors_dict["base"] = "cannot_connect"
            except (hpilo.IloError, hpilo.IloNotARackServer) as error:
                _LOGGER.error("iLO error for %s: %s", self.config[CONF_HOST], error)
                errors_dict["base"] = "unknown"
            except ConnectionError as error:
                _LOGGER.warning("Connection error to %s: %s", self.config[CONF_HOST], error)
                errors_dict["base"] = "cannot_connect"
            except OSError as error:
                _LOGGER.warning("OS error connecting to %s: %s", self.config[CONF_HOST], error)
                if "Name or service not known" in str(error) or "nodename nor servname provided" in str(error):
                    errors_dict["base"] = "invalid_host"
                else:
                    errors_dict["base"] = "cannot_connect"
            except Exception as error:
                _LOGGER.exception("Unexpected error setting up iLO for %s: %s", self.config[CONF_HOST], error)
                errors_dict["base"] = "unknown"
            

        data_schema = {
            vol.Required(CONF_USERNAME, default="Administrator"): str,
            vol.Required(CONF_PASSWORD): str,
        }
        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(data_schema),
            errors=errors_dict,
            description_placeholders={
                CONF_HOST: self.config[CONF_HOST],
            }
        )

   
    async def async_step_import(self, import_info):
        """Import config from configuration.yaml."""
        self._async_abort_entries_match({CONF_HOST: import_info[CONF_HOST]})
        return await self.async_step_user(import_info)
