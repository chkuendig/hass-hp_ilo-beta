"""Config flow for HpIlo devices."""
import errno
from functools import partial
import logging
import socket


from urllib.parse import urlparse
import voluptuous as vol
import hpilo 

from homeassistant import config_entries, data_entry_flow
from homeassistant.components import ssdp
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_TIMEOUT, CONF_TYPE, CONF_DESCRIPTION, ATTR_CONFIGURATION_URL, CONF_PORT, CONF_PROTOCOL, CONF_UNIQUE_ID, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers import config_validation as cv
from datetime import timedelta

from homeassistant.helpers.debounce import Debouncer
from .sensor import SENSOR_TYPES, DEFAULT_PORT,  DOMAIN
#from .helpers import format_mac

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
        self.config = {
            CONF_HOST: parsed_url.hostname,
            CONF_PORT: parsed_url.port, # TODO: FIX THIS, shoulnd't be 80 and HTTP 
            CONF_PROTOCOL: parsed_url.scheme ,
            CONF_NAME: discovery_info.upnp[ssdp.ATTR_UPNP_FRIENDLY_NAME],
            CONF_DESCRIPTION: discovery_info.upnp[ssdp.ATTR_UPNP_MODEL_NAME],
            CONF_UNIQUE_ID: discovery_info.ssdp_udn # TODO: This should be tagged as part of "Connections", but the actual device should be identified by it's serial number (after auth)
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
            return await self.async_step_auth()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                CONF_NAME: self.config[ CONF_NAME],
                CONF_DESCRIPTION: self.config[CONF_DESCRIPTION],
                CONF_HOST: self.config[CONF_HOST],
            },
        )

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""

        if user_input is not None:
            self.config = {}
            self.config[CONF_HOST] = user_input[CONF_HOST]
            self.config[CONF_NAME] = user_input[CONF_HOST].upper()
            self.config[CONF_PORT] = user_input[CONF_PORT]
            self.config[CONF_PROTOCOL] = user_input[CONF_PROTOCOL]
            return await self.async_step_confirm(user_input)
        else:
            data_schema = {
                vol.Required(CONF_HOST,  default="host"): str,
                vol.Required(CONF_PORT, default="80"): str,
                vol.Required(CONF_PROTOCOL, default="http"):str
            }
            return self.async_show_form(step_id="user",   data_schema=vol.Schema(data_schema))


    async def _async_get_entry(self):
        """Return config entry or update existing config entry."""
        print("self.async_create_entry")
        return self.async_create_entry(
                    title=self.config[ CONF_NAME],
                    data=self.config,
                )

    async def async_step_auth(self, user_input=None, errors=None):
        """Authenticate to the device."""
        device = self.device

        if user_input is not None:
            try:
                self.ilo = hpilo.Ilo(
                    hostname=self.config[CONF_HOST],
                    port=int(self.config[CONF_PORT]),
                    login=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    ssl=(self.config[CONF_PROTOCOL] == "https")
                ) 
                print(self.ilo)
                print(user_input)
                print(self.ilo.get_host_data())
                self.config[CONF_USERNAME]  = user_input[CONF_USERNAME]
                self.config[CONF_PASSWORD]  = user_input[CONF_PASSWORD]
               
                print(self.ilo.get_embedded_health())
               
                return  await self._async_get_entry()
            except (
                hpilo.IloError,
                hpilo.IloCommunicationError,
                hpilo.IloLoginFailed,
            ) as error:
                #raise ValueError(f"Unable to init HP ILO, {error}") from error
                errors = f"Unable to init HP ILO, {error}"
            

        data_schema = {
            vol.Required(CONF_USERNAME,  default="Administrator"): str,
            vol.Required(CONF_PASSWORD): str,
        }
        return self.async_show_form(step_id="auth",   data_schema=vol.Schema(data_schema), errors=errors)

   
    async def async_step_import(self, import_info):
        """Import config from configuration.yaml."""
        self._async_abort_entries_match({CONF_HOST: import_info[CONF_HOST]})
        return await self.async_step_user(import_info)
