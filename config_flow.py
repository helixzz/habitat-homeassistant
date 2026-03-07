"""Config flow for 栖息地智能家庭."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import area_registry as ar

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


def _options_data_from_input(
    user_input: dict[str, Any],
    inverted_cover_uids: list[str],
    current_options: dict[str, Any],
) -> dict[str, Any]:
    """从选项表单生成 options 数据，含窗帘反向与子网关。"""
    data = {"inverted_cover_uids": inverted_cover_uids}
    host = (user_input.get("child_gateway_host") or "").strip()
    uid = (user_input.get("child_gateway_uid") or "").strip()
    key = (user_input.get("child_gateway_key") or "").strip() if user_input.get("child_gateway_key") is not None else ""
    pwd = (user_input.get("child_gateway_pwd") or "").strip() if user_input.get("child_gateway_pwd") is not None else ""
    if host and uid and key and pwd:
        data["additional_gateways"] = [{
            "host": host,
            "port": int(user_input.get("child_gateway_port", 80) or 80),
            "uid": uid,
            "key": key,
            "pwd": pwd,
        }]
    else:
        data["additional_gateways"] = (current_options.get("additional_gateways") or [])[:1]
    return data


def _get_cover_devices(hass: HomeAssistant, entry_id: str) -> list[tuple[str, str]]:
    """返回 (device_uid, 显示名) 的窗帘列表；显示名含网关名 + HA 内命名与房间（若有）。"""
    data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    coordinator = data.get("coordinator")
    if not coordinator or not coordinator.data:
        return []
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    ar_reg = ar.async_get(hass)
    covers = []
    for device in coordinator.data:
        if device.get("model", "") not in COVER_MODELS:
            continue
        uid = device.get("deviceUid", "")
        gateway_name = uid
        for attr in device.get("dev_attrs", []):
            if attr.get("name") == "devName":
                gateway_name = attr.get("value", uid)
                break
        gateway_name = str(gateway_name)
        # HA 内实体名（用户可在实体设置中修改）
        ha_name: str | None = None
        entity_id = ent_reg.async_get_entity_id("cover", DOMAIN, f"habitat_cover_{uid}")
        if entity_id:
            entry = ent_reg.async_get(entity_id)
            if entry:
                ha_name = entry.name or entry.original_name
        # 设备所在区域（房间）
        area_name: str | None = None
        dev = dev_reg.async_get_device(identifiers={(DOMAIN, uid)})
        if dev and dev.area_id:
            area = ar_reg.async_get_area(dev.area_id)
            if area:
                area_name = area.name
        # 显示：优先 HA 名 + 房间，便于辨别
        if ha_name or area_name:
            parts = [p for p in ("HA: " + ha_name if ha_name else None, "房间: " + area_name if area_name else None) if p]
            label = f"{gateway_name} ({' | '.join(parts)})"
        else:
            label = f"{gateway_name} ({uid[-8:]})"
        covers.append((uid, label))
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
        opts = entry.options or {}
        inverted = set(opts.get("inverted_cover_uids") or [])
        child_list = opts.get("additional_gateways") or []
        child0 = child_list[0] if child_list else {}

        if not covers:
            schema = {
                vol.Optional("_no_covers", default=True): bool,
                vol.Optional("child_gateway_host", default=child0.get("host", "")): str,
                vol.Optional("child_gateway_port", default=child0.get("port", 80)): int,
                vol.Optional("child_gateway_uid", default=child0.get("uid", "")): str,
                vol.Optional("child_gateway_key", default=child0.get("key", "")): str,
                vol.Optional("child_gateway_pwd", default=child0.get("pwd", "")): str,
            }
            if user_input is not None:
                data = _options_data_from_input(user_input, list(inverted), opts)
                return self.async_create_entry(title="", data=data)
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(schema),
                description_placeholders={"msg": "当前未发现窗帘设备。下方可配置子网关（设备在子网关下时控制会发往子网关）。"},
            )
        def key_for(uid: str, name: str) -> str:
            return f"反向 - {name} ({uid[-8:]})"

        schema = {vol.Optional(key_for(uid, name), default=uid in inverted): bool for uid, name in covers}
        schema["child_gateway_host"] = vol.Optional(str, default=child0.get("host", ""))
        schema["child_gateway_port"] = vol.Optional(int, default=child0.get("port", 80))
        schema["child_gateway_uid"] = vol.Optional(str, default=child0.get("uid", ""))
        schema["child_gateway_key"] = vol.Optional(str, default=child0.get("key", ""))
        schema["child_gateway_pwd"] = vol.Optional(str, default=child0.get("pwd", ""))
        data_schema = vol.Schema(schema)

        if user_input is not None:
            inverted_cover_uids = [
                uid for uid, name in covers
                if user_input.get(key_for(uid, name), False)
            ]
            data = _options_data_from_input(user_input, inverted_cover_uids, opts)
            return self.async_create_entry(title="", data=data)
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={"msg": "勾选需要反向的窗帘。下方可填子网关（若设备在子网关下，控制会发往子网关）。"},
        )
