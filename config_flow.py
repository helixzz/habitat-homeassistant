"""Config flow for 栖息地智能家庭."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import HabitatAPI, HabitatAPIError
from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required("uid"): str,
        vol.Required("key"): str,
        vol.Required("pwd"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    api = HabitatAPI(
        host=data[CONF_HOST],
        access_id="FBee.key",
        key=data["key"],
        uid=data["uid"],
        pwd=data["pwd"],
        port=data.get(CONF_PORT, DEFAULT_PORT),
    )
    devices = await api.get_devices()
    if not devices:
        raise ValueError("网关未返回设备列表，请确认网关已添加子设备")
    return {"title": f"栖息地网关 ({data['uid']})", "devices": len(devices)}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 栖息地智能家庭."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except (ConnectionError, TimeoutError) as e:
                errors["base"] = str(e)
            except HabitatAPIError as e:
                errors["base"] = str(e)
            except ValueError as e:
                errors["base"] = str(e)
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "发生未知错误，请查看日志"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
