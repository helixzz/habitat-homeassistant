"""The 栖息地智能家庭 integration."""

import asyncio
import logging
import time
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BIND_RELAY_LIST_ATTR,
    BIND_RELAY_LIST_NONE,
    CONF_CURTAIN_DIR_OVERRIDES,
    CONF_CURTAIN_DIR_WATCHDOG,
    CONF_DECOUPLE_PANEL_BUTTONS,
    CONF_POLL_INTERVAL,
    CURTAIN_DIR_ATTR,
    DECOUPLE_DELAY,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
    SERVICE_REAPPLY_CURTAIN_DIR,
    SERVICE_REAPPLY_PANEL_DECOUPLE,
    SWITCH_MODELS,
)
from .api import HabitatAPI

_LOGGER = logging.getLogger(__name__)

# 网关重启后重新下发方向前的等待时间：等 Zigbee 网络与设备恢复
REAPPLY_DELAY = 45.0

# 发现新设备后自动重载的冷却时间，避免设备闪进闪出时反复重载
NEW_DEVICE_RELOAD_COOLDOWN = 300.0

SERVICE_REAPPLY_SCHEMA = vol.Schema(
    {
        vol.Optional("device_uid"): cv.string,
    }
)


def _build_apis_by_uid(entry: ConfigEntry) -> dict[str, HabitatAPI]:
    """主网关来自 entry.data，子网关来自 entry.options.additional_gateways。每个网关使用各自的 UID/密码登录；控制时按设备 childGatewayId 选 API，设备在网关间迁移后无需重载。"""
    config = entry.data
    primary_uid = config.get("uid", "")
    apis: dict[str, HabitatAPI] = {}
    primary_api = HabitatAPI(
        host=config.get("host", "172.16.33.72"),
        access_id=config.get("access_id", "FBee.key"),
        key=config.get("key"),
        uid=primary_uid,
        pwd=config.get("pwd"),
        port=config.get(CONF_PORT, DEFAULT_PORT),
    )
    apis[primary_uid] = primary_api
    for g in (getattr(entry, "options", None) or {}).get("additional_gateways") or []:
        uid = g.get("uid")
        if not uid or not g.get("host") or g.get("key") is None or g.get("pwd") is None:
            continue
        apis[uid] = HabitatAPI(
            host=g["host"],
            access_id="FBee.key",
            key=g["key"],
            uid=uid,
            pwd=g["pwd"],
            port=g.get("port", DEFAULT_PORT),
        )
    return apis


def _resolve_api(
    device_uid: str,
    apis_by_uid: dict,
    primary_uid: str,
    default_api: HabitatAPI,
    devices: list | None,
) -> HabitatAPI:
    """按设备当前所属网关解析 API。"""
    for device in devices or []:
        if device.get("deviceUid") == device_uid:
            child_uid = device.get("childGatewayId") or primary_uid
            return (
                apis_by_uid.get(child_uid)
                or apis_by_uid.get(primary_uid)
                or default_api
            )
    return apis_by_uid.get(primary_uid) or default_api


async def _reapply_curtain_directions(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_uid: str | None = None,
    delay: float = 0.0,
) -> int:
    """把 options 里记录的方向重新下发给电机。

    网关本身不保存 curtainDir（只转发），所以网关重启或云端同步后可能被重置；
    这里以 HA 的 config entry options 作为「真值源」补齐。
    """
    overrides: dict = (entry.options or {}).get(CONF_CURTAIN_DIR_OVERRIDES) or {}
    if device_uid:
        overrides = (
            {device_uid: overrides[device_uid]}
            if device_uid in overrides
            else {}
        )
    if not overrides:
        return 0

    if delay:
        await asyncio.sleep(delay)

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    coordinator: DataUpdateCoordinator | None = data.get("coordinator")
    apis_by_uid: dict = data.get("apis_by_uid") or {}
    primary_uid: str = data.get("primary_uid", "")
    default_api: HabitatAPI | None = data.get("api")
    if default_api is None:
        return 0
    devices = (coordinator.data if coordinator else None) or []

    written = 0
    for uid, value in overrides.items():
        api = _resolve_api(uid, apis_by_uid, primary_uid, default_api, devices)
        try:
            ok = await api.set_device_attribute(uid, CURTAIN_DIR_ATTR, int(value))
        except Exception:  # noqa: BLE001 - 网络异常不应影响看护流程
            _LOGGER.exception("重新下发窗帘方向失败: %s", uid)
            continue
        if ok:
            written += 1
        else:
            _LOGGER.warning("重新下发窗帘方向被网关拒绝: %s -> %s", uid, value)
    if written:
        _LOGGER.info("已重新下发 %s 个窗帘的方向", written)
    return written


async def _reapply_panel_decouple(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_uid: str | None = None,
    delay: float = 0.0,
) -> int:
    """解除「按键不该切继电器」的面板上的本地继电器绑定。

    面板固件里有两套彼此独立的绑定：
      ① 组绑定      —— 按键向 Zigbee 组发组播命令（ownGroupList）
      ② 继电器绑定  —— bindRelayList，按键直接吸合面板自己的继电器（纯本地行为）

    判断该面板需不需要 ②：看它名下所有 Zigbee 组的成员里**有没有它自己**。
      * 组里**没有**自己 → 负载是独立的智能灯控器（常火供电），按键只需发组播；
        此时如果 ② 还在，按键会顺带切断灯控器的供电，灯控器靠电容撑几分钟后掉线
        （用户看到的就是「灯忽然不可用」）→ 必须解绑。
      * 组里**有**自己 → 负载就是它自己的继电器输出（普通灯），切继电器是唯一能
        开关那盏灯的方式 → 必须保留，跳过。

    下发时值必须传**字符串** "[]"，不能传 Python 列表 —— 列表虽然也能下发，但网关
    拼 HTTP 响应时会崩（500），反复触发会把它的 HTTP 服务压死；字符串形式返回 200、
    同样下发 zgb_val:0，而且不受「值没变就跳过」限制，一条请求即可。
    """
    if delay:
        await asyncio.sleep(delay)

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    coordinator: DataUpdateCoordinator | None = data.get("coordinator")
    apis_by_uid: dict = data.get("apis_by_uid") or {}
    primary_uid: str = data.get("primary_uid", "")
    default_api: HabitatAPI | None = data.get("api")
    if default_api is None:
        return 0

    try:
        groups = await default_api.get_groups()
    except Exception:  # noqa: BLE001 - 看护失败不应影响集成加载
        _LOGGER.exception("读取分组失败，跳过面板按键解绑")
        return 0

    # deviceUid -> 该面板名下各组的成员列表
    owned: dict[str, list[list[str]]] = {}
    for group in groups or []:
        owner = ((group.get("belongToDevSection") or {}).get("deviceUid")) or ""
        if not owner:
            continue
        members = [
            (m.get("deviceUid") if isinstance(m, dict) else m)
            for m in (group.get("members") or [])
        ]
        owned.setdefault(owner, []).append([m for m in members if m])

    devices = (coordinator.data if coordinator else None) or []
    written = 0
    seen: set[str] = set()
    for device in devices:
        uid = device.get("deviceUid") or ""
        if not uid or uid in seen:  # 主网关的列表里已包含子网设备，去重
            continue
        seen.add(uid)
        if device_uid and uid != device_uid:
            continue
        if device.get("model") not in SWITCH_MODELS:
            continue
        attr_names = {a.get("name") for a in (device.get("dev_attrs") or [])}
        if BIND_RELAY_LIST_ATTR not in attr_names:
            continue  # 该型号没有继电器绑定字段
        panel_groups = owned.get(uid)
        if not panel_groups:
            continue  # 按键没有任何组绑定，不处理
        if any(uid in members for members in panel_groups):
            _LOGGER.debug(
                "面板 %s 的按键负载是自身继电器（普通灯），保留继电器绑定", uid
            )
            continue

        api = _resolve_api(uid, apis_by_uid, primary_uid, default_api, devices)
        try:
            code = await api.set_device_attribute_raw(
                uid, BIND_RELAY_LIST_ATTR, BIND_RELAY_LIST_NONE
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("解绑面板 %s 的按键继电器绑定失败", uid)
            continue
        if code == 200:
            written += 1
            _LOGGER.info(
                "已解除面板 %s 的按键继电器绑定（按键改为只发 Zigbee 组播）", uid
            )
        else:
            _LOGGER.warning("解绑面板 %s 失败，网关返回 %s", uid, code)
        await asyncio.sleep(0.5)  # 稍微错开，别把网关的 HTTP 服务打满
    return written


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 栖息地 from a config entry."""
    config = entry.data
    apis_by_uid = _build_apis_by_uid(entry)
    primary_uid = config.get("uid", "")
    api = apis_by_uid.get(primary_uid)

    # 记录上一次拉取是否失败：由失败转为成功 = 网关重启/重连过
    gateway_was_down = False

    async def _async_fetch_devices() -> list:
        """从主网关拉取设备列表（主网关可返回主+子网下设备）。"""
        nonlocal gateway_was_down
        try:
            devices = await api.get_devices()
        except Exception:
            gateway_was_down = True
            raise
        if not devices:
            gateway_was_down = True
            raise UpdateFailed("Gateway returned no devices")
        if gateway_was_down:
            gateway_was_down = False
            if (entry.options or {}).get(CONF_CURTAIN_DIR_WATCHDOG, True):
                _LOGGER.info("网关重新上线，稍后重新下发窗帘方向")
                hass.async_create_task(
                    _reapply_curtain_directions(hass, entry, delay=REAPPLY_DELAY)
                )
            if (entry.options or {}).get(CONF_DECOUPLE_PANEL_BUTTONS, True):
                _LOGGER.info("网关重新上线，稍后重新解绑面板的按键继电器绑定")
                hass.async_create_task(
                    _reapply_panel_decouple(hass, entry, delay=DECOUPLE_DELAY)
                )
        return devices

    # 轮询间隔可配置：网关没有推送接口，非 HA 发起的变更（物理开关/面板/栖息地 App）
    # 只能等下一次轮询才会反映到 HA，所以间隔直接决定「看起来有多及时」。
    try:
        poll_interval = int(
            (entry.options or {}).get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            or DEFAULT_POLL_INTERVAL
        )
    except (TypeError, ValueError):
        poll_interval = DEFAULT_POLL_INTERVAL
    if poll_interval < 1:
        poll_interval = DEFAULT_POLL_INTERVAL

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_fetch_devices,
        update_interval=timedelta(seconds=poll_interval),
    )
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("Found %s devices on gateway", len(coordinator.data))

    dev_reg = dr.async_get(hass)
    gateway_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="栖息地",
        model="Zigbee 网关",
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "apis_by_uid": apis_by_uid,
        "primary_uid": primary_uid,
        "coordinator": coordinator,
        "gateway_device_id": gateway_device.id,
        "gateway_identifier": entry.entry_id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ⚠️ 必须保留一个监听者，否则协调器只刷新一次就永久停摆。
    # DataUpdateCoordinator._async_refresh() 的 finally 分支是：
    #     if not auth_failed and self._listeners and not self.hass.is_stopping:
    #         self._schedule_refresh()
    # 也就是说「没有监听者 => 不再安排下一次刷新」。本集成的实体是普通实体
    # （自己在 async_update 里读 coordinator.data），从不调用 async_add_listener，
    # 所以 _listeners 一直为空 —— 结果是集成加载后除了首次拉取之外再也不会轮询，
    # 所有传感器/开关/灯的状态会永久停在加载那一刻。
    #
    # 下面这个监听者一举两得：既把周期性轮询打开，又负责发现「后入网」的新设备。
    known_device_uids = {d.get("deviceUid") for d in (coordinator.data or [])}
    last_reload = 0.0

    @callback
    def _async_check_new_devices() -> None:
        """设备可能在集成启动之后才入网（Zigbee 配网、固件重置后重新入网等）。

        各平台只在 setup 时按 coordinator.data 创建实体，所以这些新设备会一直没有
        实体（HA 里只留一个 restored 空壳），必须手动重载集成才会出现。
        这里监听协调器更新，一旦发现新设备就自动重载一次。
        """
        nonlocal known_device_uids, last_reload
        current = {d.get("deviceUid") for d in (coordinator.data or [])}
        new_uids = current - known_device_uids
        if new_uids:
            known_device_uids = current
            now = time.monotonic()
            if now - last_reload < NEW_DEVICE_RELOAD_COOLDOWN:
                return  # 冷却中：设备在闪进闪出，避免反复重载
            last_reload = now
            _LOGGER.info("发现新入网设备 %s，重载集成以创建实体", sorted(new_uids))
            hass.config_entries.async_schedule_reload(entry.entry_id)
        else:
            known_device_uids = current

    entry.async_on_unload(coordinator.async_add_listener(_async_check_new_devices))

    # 启动时也补一次（HA 与网关一起断电重启时，「重连」事件可能观察不到）
    if (entry.options or {}).get(CONF_CURTAIN_DIR_WATCHDOG, True):
        hass.async_create_task(
            _reapply_curtain_directions(hass, entry, delay=REAPPLY_DELAY)
        )

    # 同理：面板固件更新/重置会清掉本地的继电器绑定，启动时补一次
    if (entry.options or {}).get(CONF_DECOUPLE_PANEL_BUTTONS, True):
        hass.async_create_task(
            _reapply_panel_decouple(hass, entry, delay=DECOUPLE_DELAY)
        )

    async def _async_reapply_service(call: ServiceCall) -> None:
        """手动重新下发窗帘方向。"""
        target = call.data.get("device_uid")
        for config_entry in hass.config_entries.async_entries(DOMAIN):
            await _reapply_curtain_directions(hass, config_entry, device_uid=target)

    if not hass.services.has_service(DOMAIN, SERVICE_REAPPLY_CURTAIN_DIR):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REAPPLY_CURTAIN_DIR,
            _async_reapply_service,
            schema=SERVICE_REAPPLY_SCHEMA,
        )

    async def _async_decouple_service(call: ServiceCall) -> None:
        """手动重新解绑面板的按键继电器绑定。"""
        target = call.data.get("device_uid")
        for config_entry in hass.config_entries.async_entries(DOMAIN):
            await _reapply_panel_decouple(hass, config_entry, device_uid=target)

    if not hass.services.has_service(DOMAIN, SERVICE_REAPPLY_PANEL_DECOUPLE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REAPPLY_PANEL_DECOUPLE,
            _async_decouple_service,
            schema=SERVICE_REAPPLY_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # 用 pop(..., None)：正常卸载时 entry.async_on_unload 已经跑过，
        # 这里只是兜底，不应该因为键缺失而抛 KeyError 让卸载失败。
        data = (hass.data.get(DOMAIN) or {}).pop(entry.entry_id, None) or {}
        coordinator = data.get("coordinator")
        if coordinator is not None:
            await coordinator.async_shutdown()
    return unload_ok
