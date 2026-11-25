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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HabitatAPI, HabitatAPIError
from .cloud import HabitatCloudAPI, HabitatCloudError
from .const import (
    CLOUD_POLL_INTERVAL_CHOICES,
    CONF_CLOUD_ENABLED,
    CONF_CLOUD_HOME_ID,
    CONF_CLOUD_MOBILE,
    CONF_CLOUD_POLL_INTERVAL,
    CONF_CLOUD_TOKEN,
    CONF_CURTAIN_DIR_OVERRIDES,
    CONF_CURTAIN_DIR_WATCHDOG,
    CONF_DECOUPLE_PANEL_BUTTONS,
    CONF_POLL_INTERVAL,
    DEFAULT_CLOUD_POLL_INTERVAL,
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


def _coerce_cloud_interval(value: Any) -> int:
    """云端轮询间隔收敛到合法取值。"""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CLOUD_POLL_INTERVAL
    return seconds if seconds in CLOUD_POLL_INTERVAL_CHOICES else DEFAULT_CLOUD_POLL_INTERVAL


def _cloud_options_from_input(
    user_input: dict[str, Any],
    current_options: dict[str, Any],
) -> dict[str, Any]:
    """云端账号相关选项。关闭时清掉 token，避免留着无效凭据。"""
    enabled = bool(
        user_input.get(CONF_CLOUD_ENABLED, current_options.get(CONF_CLOUD_ENABLED, False))
    )
    mobile = str(
        user_input.get(CONF_CLOUD_MOBILE)
        or current_options.get(CONF_CLOUD_MOBILE)
        or ""
    ).strip()
    token = current_options.get(CONF_CLOUD_TOKEN)
    home_id = current_options.get(CONF_CLOUD_HOME_ID)
    if not enabled:
        token = None
        home_id = None
    return {
        CONF_CLOUD_ENABLED: enabled,
        CONF_CLOUD_MOBILE: mobile,
        CONF_CLOUD_TOKEN: token,
        CONF_CLOUD_HOME_ID: home_id,
        CONF_CLOUD_POLL_INTERVAL: _coerce_cloud_interval(
            user_input.get(
                CONF_CLOUD_POLL_INTERVAL,
                current_options.get(CONF_CLOUD_POLL_INTERVAL, DEFAULT_CLOUD_POLL_INTERVAL),
            )
        ),
    }


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
        **_cloud_options_from_input(user_input, current_options),
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

    # --- 云端登录失效后的重新认证 -----------------------------------------
    # 云端 token 没有刷新接口，过期只能重新短信登录。云端协调器抛
    # ConfigEntryAuthFailed 时，HA 会带着 entry_id 进入下面这个流程。
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    def _reauth_entry(self):
        entry_id = (self.context or {}).get("entry_id")
        return self.hass.config_entries.async_get_entry(entry_id) if entry_id else None

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """确认手机号并发送验证码。"""
        errors: dict[str, str] = {}
        entry = self._reauth_entry()
        options = (entry.options if entry else {}) or {}
        mobile = str(options.get(CONF_CLOUD_MOBILE) or "")

        if user_input is not None:
            mobile = str(user_input.get(CONF_CLOUD_MOBILE) or mobile).strip()
            api = HabitatCloudAPI(async_get_clientsession(self.hass))
            try:
                await api.async_request_sms_code(mobile)
            except HabitatCloudError as err:
                errors["base"] = str(err)
            else:
                self._cloud_mobile = mobile
                return await self.async_step_reauth_code()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_CLOUD_MOBILE, default=mobile): str}
            ),
            errors=errors,
        )

    async def async_step_reauth_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """输入验证码，换取新 token 并写回选项。"""
        errors: dict[str, str] = {}
        entry = self._reauth_entry()
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            code = str(user_input.get("cloud_code") or "").strip()
            api = HabitatCloudAPI(async_get_clientsession(self.hass))
            try:
                token = await api.async_login(self._cloud_mobile, code)
            except HabitatCloudError as err:
                errors["base"] = str(err)
            else:
                options = dict(entry.options or {})
                options[CONF_CLOUD_TOKEN] = token
                options[CONF_CLOUD_HOME_ID] = api.home_id
                options[CONF_CLOUD_MOBILE] = self._cloud_mobile
                options[CONF_CLOUD_ENABLED] = True
                self.hass.config_entries.async_update_entry(entry, options=options)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_code",
            data_schema=vol.Schema({vol.Required("cloud_code"): str}),
            errors=errors,
            description_placeholders={"mobile": self._cloud_mobile},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HabitatOptionsFlow:
        return HabitatOptionsFlow()


class HabitatOptionsFlow(config_entries.OptionsFlow):
    """栖息地集成的选项流程：窗帘反向 / 面板解绑 / 云端账号。"""

    def __init__(self) -> None:
        self._pending_options: dict[str, Any] = {}
        self._cloud_mobile: str = ""

    async def _async_save_or_login(
        self, options_data: dict[str, Any], user_input: dict[str, Any]
    ) -> FlowResult:
        """保存选项；若勾选了「登录云端账号」，则先发验证码再进入验证码步骤。"""
        if not user_input.get("cloud_login"):
            return self.async_create_entry(title="", data=options_data)

        mobile = str(options_data.get(CONF_CLOUD_MOBILE) or "").strip()
        if not mobile:
            # 没填手机号就没法登录，先保存其余选项
            return self.async_create_entry(title="", data=options_data)

        api = HabitatCloudAPI(async_get_clientsession(self.hass))
        try:
            await api.async_request_sms_code(mobile)
        except HabitatCloudError as err:
            _LOGGER.warning("请求云端短信验证码失败：%s", err)
            return self.async_create_entry(title="", data=options_data)

        self._pending_options = options_data
        self._cloud_mobile = mobile
        return await self.async_step_cloud_code()

    async def async_step_cloud_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """输入云端登录的短信验证码。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input.get("cloud_code") or "").strip()
            api = HabitatCloudAPI(async_get_clientsession(self.hass))
            try:
                token = await api.async_login(self._cloud_mobile, code)
            except HabitatCloudError as err:
                errors["base"] = str(err)
            else:
                options = dict(self._pending_options)
                options[CONF_CLOUD_TOKEN] = token
                options[CONF_CLOUD_HOME_ID] = api.home_id
                options[CONF_CLOUD_ENABLED] = True
                options[CONF_CLOUD_MOBILE] = self._cloud_mobile
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="cloud_code",
            data_schema=vol.Schema({vol.Required("cloud_code"): str}),
            errors=errors,
            description_placeholders={"mobile": self._cloud_mobile},
        )

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

        # 云端账号：用于「网关看不到」的设备（四合一水处理器）。
        # 登录只有短信验证码一种方式，且没有刷新接口 —— 过期需重新登录。
        cloud_fields = {
            vol.Optional(
                CONF_CLOUD_ENABLED,
                default=bool(opts.get(CONF_CLOUD_ENABLED, False)),
            ): bool,
            vol.Optional(
                CONF_CLOUD_MOBILE,
                default=str(opts.get(CONF_CLOUD_MOBILE, "")),
            ): str,
            vol.Optional("cloud_login", default=False): bool,
            vol.Optional(
                CONF_CLOUD_POLL_INTERVAL,
                default=_coerce_cloud_interval(
                    opts.get(CONF_CLOUD_POLL_INTERVAL, DEFAULT_CLOUD_POLL_INTERVAL)
                ),
            ): vol.In(CLOUD_POLL_INTERVAL_CHOICES),
        }

        if not covers:
            schema = {
                vol.Optional("_no_covers", default=True): bool,
                **watchdog_fields,
                **poll_fields,
                **cloud_fields,
                **main_fields,
                **child_fields,
            }
            if user_input is not None:
                new_data = _main_gateway_data_from_input(user_input, data)
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                options_data = _options_data_from_input(user_input, list(inverted), opts)
                return await self._async_save_or_login(options_data, user_input)
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
        schema.update(cloud_fields)
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
            return await self._async_save_or_login(options_data, user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={"msg": "上方可修改主网关连接（主机/IP、端口、UID、key、密码）。勾选需要反向的窗帘；下方可填子网关。主机建议填主机名或 DHCP 保留名。「poll_interval」= 状态轮询间隔（秒，默认 15）：网关没有推送接口，物理开关/面板/栖息地 App 的变更只能靠轮询发现，间隔越短越及时（设备列表约 85 KB/次）。"},
        )
