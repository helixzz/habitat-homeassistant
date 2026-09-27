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
from .const import (
    CONF_CURTAIN_DIR_OVERRIDES,
    CONF_CURTAIN_DIR_WATCHDOG,
    CONF_DECOUPLE_PANEL_BUTTONS,
    CONF_POLL_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    COVER_MODELS,
    POLL_INTERVAL_CHOICES,
)

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


def _main_gateway_data_from_input(
    user_input: dict[str, Any],
    current_data: dict[str, Any],
) -> dict[str, Any]:
    """从选项表单生成主网关的 entry.data（host/port/uid/key/pwd）。"""
    raw_port = user_input.get("main_gateway_port")
    port = (
        int(raw_port)
        if raw_port is not None and str(raw_port).strip() != ""
        else current_data.get(CONF_PORT, DEFAULT_PORT)
    )
    return {
        **current_data,
        CONF_HOST: (user_input.get("main_gateway_host") or current_data.get(CONF_HOST, "")).strip(),
        CONF_PORT: port,
        "uid": (user_input.get("main_gateway_uid") or current_data.get("uid", "")).strip(),
        "key": (user_input.get("main_gateway_key") or current_data.get("key", "")).strip(),
        "pwd": (user_input.get("main_gateway_pwd") or current_data.get("pwd", "")).strip(),
    }


def _coerce_poll_interval(value: Any) -> int:
    """把轮询间隔收敛到合法取值（表单是下拉选择，手动改 options 也要容错）。"""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL
    return seconds if seconds in POLL_INTERVAL_CHOICES else DEFAULT_POLL_INTERVAL


def _options_data_from_input(
    user_input: dict[str, Any],
    inverted_cover_uids: list[str],
    current_options: dict[str, Any],
) -> dict[str, Any]:
    """从选项表单生成 options 数据，含窗帘反向、方向看护与子网关。子网关字段留空则清除已有配置。"""
    data = {
        "inverted_cover_uids": inverted_cover_uids,
        # 必须原样保留：这是「窗帘方向」的真值源，保存选项时不能丢
        CONF_CURTAIN_DIR_OVERRIDES: dict(
            current_options.get(CONF_CURTAIN_DIR_OVERRIDES) or {}
        ),
        CONF_CURTAIN_DIR_WATCHDOG: bool(
            user_input.get(
                CONF_CURTAIN_DIR_WATCHDOG,
                current_options.get(CONF_CURTAIN_DIR_WATCHDOG, True),
            )
        ),
        # 面板按键解绑：面板固件更新/重置会清掉本地继电器绑定，勾选后自动补发
        CONF_DECOUPLE_PANEL_BUTTONS: bool(
            user_input.get(
                CONF_DECOUPLE_PANEL_BUTTONS,
                current_options.get(CONF_DECOUPLE_PANEL_BUTTONS, False),
            )
        ),
        CONF_POLL_INTERVAL: _coerce_poll_interval(
            user_input.get(
                CONF_POLL_INTERVAL,
                current_options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )
        ),
    }
    host = (user_input.get("child_gateway_host") or "").strip()
    uid = (user_input.get("child_gateway_uid") or "").strip()
    key = (user_input.get("child_gateway_key") or "").strip() if user_input.get("child_gateway_key") is not None else ""
    pwd = (user_input.get("child_gateway_pwd") or "").strip() if user_input.get("child_gateway_pwd") is not None else ""
    if host and uid and key and pwd:
        raw_port = user_input.get("child_gateway_port")
        port = int(raw_port) if raw_port is not None and str(raw_port).strip() != "" else 80
        data["additional_gateways"] = [{
            "host": host,
            "port": port,
            "uid": uid,
            "key": key,
            "pwd": pwd,
        }]
    else:
        # 任一子网关字段留空视为“不配置子网关”，清除原有配置
        data["additional_gateways"] = []
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
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description="主机可填 IP 或主机名。建议使用路由器中为网关分配的主机名或 DHCP 保留名称，这样网关 IP 因 DHCP 变更后无需修改配置即可自动连接。",
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
        data = entry.data or {}
        inverted = set(opts.get("inverted_cover_uids") or [])
        child_list = opts.get("additional_gateways") or []
        child0 = child_list[0] if child_list else {}

        # 主网关连接信息（可在配置中修改 IP/主机名等）；Schema 的键为 vol.Required/Optional，值为类型
        main_fields = {
            vol.Required("main_gateway_host", default=data.get(CONF_HOST, "")): str,
            vol.Optional("main_gateway_port", default=data.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required("main_gateway_uid", default=data.get("uid", "")): str,
            vol.Required("main_gateway_key", default=data.get("key", "")): str,
            vol.Required("main_gateway_pwd", default=data.get("pwd", "")): str,
        }
        child_fields = {
            vol.Optional("child_gateway_host", default=child0.get("host", "")): str,
            vol.Optional("child_gateway_port", default=child0.get("port", 80)): int,
            vol.Optional("child_gateway_uid", default=child0.get("uid", "")): str,
            vol.Optional("child_gateway_key", default=child0.get("key", "")): str,
            vol.Optional("child_gateway_pwd", default=child0.get("pwd", "")): str,
        }
        # 方向看护：网关不持久化 curtainDir，勾选后在网关重连/集成启动时自动补发
        watchdog_fields = {
            vol.Optional(
                CONF_CURTAIN_DIR_WATCHDOG,
                default=bool(opts.get(CONF_CURTAIN_DIR_WATCHDOG, True)),
            ): bool,
            vol.Optional(
                CONF_DECOUPLE_PANEL_BUTTONS,
                default=bool(opts.get(CONF_DECOUPLE_PANEL_BUTTONS, False)),
            ): bool,
        }
        # 轮询间隔：网关无推送接口，非 HA 发起的变更只能靠轮询发现；
        # 间隔越短越及时，代价是更多局域网流量（设备列表约 85 KB / 次）。
        poll_fields = {
            vol.Optional(
                CONF_POLL_INTERVAL,
                default=_coerce_poll_interval(
                    opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
                ),
            ): vol.In(POLL_INTERVAL_CHOICES),
        }

        if not covers:
            schema = {
                vol.Optional("_no_covers", default=True): bool,
                **watchdog_fields,
                **poll_fields,
                **main_fields,
                **child_fields,
            }
            if user_input is not None:
                new_data = _main_gateway_data_from_input(user_input, data)
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                options_data = _options_data_from_input(user_input, list(inverted), opts)
                return self.async_create_entry(title="", data=options_data)
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(schema),
                description_placeholders={"msg": "当前未发现窗帘设备。上方可修改主网关连接（主机/IP、端口、UID、key、密码）；下方可配置子网关。主机建议填主机名或 DHCP 保留名。「poll_interval」= 状态轮询间隔（秒，默认 15）：网关没有推送接口，物理开关/面板/栖息地 App 的变更只能靠轮询发现，间隔越短越及时（设备列表约 85 KB/次）。第二个勾选 = 自动解除「按键不该切继电器」的面板上的本地继电器绑定。机制：按键默认直接吸合自己的继电器（会切断灯控器供电），写空 `bindRelayList` 后改为只发 Zigbee 组播控制智能灯。**安全前提**：该面板所属网关上必须已存在它的按键分组，否则写空会让按键失去全部输出（哑键）—— 集成现在会先检查这一点，不满足就跳过并告警。默认关闭。"},
            )
        def key_for(uid: str, name: str) -> str:
            return f"反向 - {name} ({uid[-8:]})"

        schema = {vol.Optional(key_for(uid, name), default=uid in inverted): bool for uid, name in covers}
        schema.update(watchdog_fields)
        schema.update(poll_fields)
        schema.update(main_fields)
        schema.update(child_fields)
        data_schema = vol.Schema(schema)

        if user_input is not None:
            new_data = _main_gateway_data_from_input(user_input, data)
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
            inverted_cover_uids = [
                uid for uid, name in covers
                if user_input.get(key_for(uid, name), False)
            ]
            options_data = _options_data_from_input(user_input, inverted_cover_uids, opts)
            return self.async_create_entry(title="", data=options_data)
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={"msg": "上方可修改主网关连接（主机/IP、端口、UID、key、密码）。勾选需要反向的窗帘；下方可填子网关。主机建议填主机名或 DHCP 保留名。「poll_interval」= 状态轮询间隔（秒，默认 15）：网关没有推送接口，物理开关/面板/栖息地 App 的变更只能靠轮询发现，间隔越短越及时（设备列表约 85 KB/次）。"},
        )
