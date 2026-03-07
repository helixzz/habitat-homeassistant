"""Config flow for 栖息地智能家庭."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import HabitatAPI, HabitatAPIError
from .const import DEFAULT_HOST, DEFAULT_PORT, DOMAIN, COVER_MODELS

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


def _get_cover_devices(hass: HomeAssistant, entry_id: str) -> list[tuple[str, str]]:
    """返回 (device_uid, 显示名) 的窗帘列表，用于选项流程。"""
    data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    coordinator = data.get("coordinator")
    if not coordinator or not coordinator.data:
        return []
    covers = []
    for device in coordinator.data:
        if device.get("model", "") not in COVER_MODELS:
            continue
        uid = device.get("deviceUid", "")
        name = uid
        for attr in device.get("dev_attrs", []):
            if attr.get("name") == "devName":
                name = attr.get("value", uid)
                break
        covers.append((uid, str(name)))
    return sorted(covers, key=lambda x: x[1])


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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HabitatOptionsFlow:
        return HabitatOptionsFlow()


class HabitatOptionsFlow(config_entries.OptionsFlow):
    """栖息地集成的选项流程：窗帘反向。"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """窗帘反向：勾选则 HA 开=物理关、HA 关=物理开。"""
        entry = self.config_entry
        covers = _get_cover_devices(self.hass, entry.entry_id)
        inverted = set(entry.options.get("inverted_cover_uids") or [])
        if not covers:
            data_schema = vol.Schema({vol.Optional("_no_covers", default=True): bool})
            if user_input is not None:
                return self.async_create_entry(title="", data=entry.options or {})
            return self.async_show_form(
                step_id="init",
                data_schema=data_schema,
                description_placeholders={"msg": "当前未发现窗帘设备（网关可能离线或尚未添加窗帘）。请稍后重试。"},
            )
        # 键用「反向 - 名称 (uid 后 8 位)」保证唯一且可读；提交时根据键反查 uid
        def key_for(uid: str, name: str) -> str:
            return f"反向 - {name} ({uid[-8:]})"

        data_schema = vol.Schema(
            {vol.Optional(key_for(uid, name), default=uid in inverted): bool for uid, name in covers}
        )
        if user_input is not None:
            inverted_cover_uids = [
                uid for uid, name in covers
                if user_input.get(key_for(uid, name), False)
            ]
            return self.async_create_entry(
                title="",
                data={"inverted_cover_uids": inverted_cover_uids},
            )
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={"msg": "勾选需要反向的窗帘：在 HA 中「开」时实际闭合、「关」时实际拉开。"},
        )
