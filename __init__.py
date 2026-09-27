"""The 栖息地智能家庭 integration."""

import asyncio
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CURTAIN_DIR_OVERRIDES,
    CONF_CURTAIN_DIR_WATCHDOG,
    CURTAIN_DIR_ATTR,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
    SERVICE_REAPPLY_CURTAIN_DIR,
)
from .api import HabitatAPI

_LOGGER = logging.getLogger(__name__)

# 网关重启后重新下发方向前的等待时间：等 Zigbee 网络与设备恢复
REAPPLY_DELAY = 45.0

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
        return devices

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_fetch_devices,
        update_interval=timedelta(seconds=60),
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
    # 这里挂一个空监听者，把周期性轮询真正打开。
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))

    # 启动时也补一次（HA 与网关一起断电重启时，「重连」事件可能观察不到）
    if (entry.options or {}).get(CONF_CURTAIN_DIR_WATCHDOG, True):
        hass.async_create_task(
            _reapply_curtain_directions(hass, entry, delay=REAPPLY_DELAY)
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
