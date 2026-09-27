"""Select platform for 栖息地智能家庭 — 窗帘电机方向 (curtainDir)。

栖息地 App 未暴露窗帘方向设置，但网关本地 API 的 `curtainDir` 属性即为该参数：
写入 0=正常、1=反向；写入后电机会重新校准行程（方向有变化时通常会整程运行一次）。

注意：**网关不持久化该值**（它只把命令转发给电机，不写数据库），所以方向可能在
网关重启或云端同步后被重置。为了让方向「存得住」，本实体会把期望值记进
config entry options，并由 `__init__.py` 的看护逻辑在网关重连/集成启动时自动补发。
"""

import asyncio
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import (
    CONF_CURTAIN_DIR_OVERRIDES,
    COVER_MODELS,
    CURTAIN_DIR_ATTR,
    CURTAIN_DIR_NORMAL,
    CURTAIN_DIR_REVERSED,
    DOMAIN,
)
from .helpers import get_attr_value

_LOGGER = logging.getLogger(__name__)

OPTION_NORMAL = "正常"
OPTION_REVERSED = "反向"
OPTIONS = [OPTION_NORMAL, OPTION_REVERSED]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为支持 curtainDir 的窗帘创建方向选择实体。"""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid: dict = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_identifier: str = data["gateway_identifier"]
    devices = coordinator.data or []

    entities = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)
        dev_attrs = device.get("dev_attrs", [])

        if model not in COVER_MODELS or not online:
            continue
        # 仅当网关为该型号提供了方向参数时才创建实体
        if get_attr_value(dev_attrs, CURTAIN_DIR_ATTR) is None:
            continue

        name = device_uid
        for attr in dev_attrs:
            if attr.get("name") == "devName":
                name = attr.get("value", device_uid)
                break

        entities.append(
            HabitatCurtainDirection(
                config_entry,
                apis_by_uid,
                primary_uid,
                default_api,
                coordinator,
                gateway_identifier,
                device_uid,
                name,
                device,
            )
        )

    async_add_entities(entities)


class HabitatCurtainDirection(SelectEntity, RestoreEntity):
    """窗帘电机方向：正常 / 反向。"""

    _attr_options = OPTIONS
    # 这是本集成对 App 缺失能力的补充，默认显示
    _attr_entity_registry_visible_default = True

    def __init__(
        self,
        entry: ConfigEntry,
        apis_by_uid: dict,
        primary_uid: str,
        default_api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_identifier: str,
        device_uid: str,
        device_name: str,
        device_data: dict,
    ):
        """方向存在电机内，网关只回报默认值 0。

        为了让方向「存得住」，期望值同时写进 config entry options，作为真值源；
        网关重启/重连后由 __init__ 的看护逻辑自动重新下发。
        """
        self._entry = entry
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._device_name = device_name
        self._device_data = device_data
        self._attr_current_option = self._gateway_option()

    def _gateway_option(self) -> str | None:
        """从网关 dev_attrs 读取（通常恒为 0，仅作初值）。"""
        raw = get_attr_value(self._device_data.get("dev_attrs", []), CURTAIN_DIR_ATTR)
        if raw is None:
            return None
        try:
            return (
                OPTION_REVERSED
                if int(raw) == CURTAIN_DIR_REVERSED
                else OPTION_NORMAL
            )
        except (TypeError, ValueError):
            return None

    def _get_api(self) -> HabitatAPI:
        """按设备当前所属网关选 API。"""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return (
                    self._apis_by_uid.get(child_uid)
                    or self._apis_by_uid.get(self._primary_uid)
                    or self._default_api
                )
        return self._default_api

    @property
    def unique_id(self) -> str:
        return f"habitat_curtain_dir_{self._device_uid}"

    @property
    def name(self) -> str:
        return "窗帘方向"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._device_name,
            manufacturer="栖息地",
            model="电动窗帘",
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_added_to_hass(self) -> None:
        """恢复期望方向：优先 config entry options（真值源），其次实体历史状态。"""
        await super().async_added_to_hass()
        overrides = (self._entry.options or {}).get(CONF_CURTAIN_DIR_OVERRIDES) or {}
        if self._device_uid in overrides:
            try:
                stored = int(overrides[self._device_uid])
            except (TypeError, ValueError):
                stored = None
            if stored is not None:
                self._attr_current_option = (
                    OPTION_REVERSED if stored == CURTAIN_DIR_REVERSED else OPTION_NORMAL
                )
                return
        last = await self.async_get_last_state()
        if last is not None and last.state in OPTIONS:
            self._attr_current_option = last.state
            # 迁移 v0.2.0 用户：那时方向只存在实体状态里，没写进 options。
            # 补写一次，否则看护逻辑「无值可补」，网关重启后方向仍会被重置。
            if last.state == OPTION_REVERSED:
                self.hass.async_create_task(self._backfill_override())

    async def _backfill_override(self) -> None:
        """把旧版本实体里记录的「反向」补写进 options（延迟执行，避开初始化阶段）。"""
        await asyncio.sleep(5.0)
        if self._attr_current_option != OPTION_REVERSED:
            return
        overrides = (self._entry.options or {}).get(CONF_CURTAIN_DIR_OVERRIDES) or {}
        if self._device_uid in overrides:
            return
        _LOGGER.info("把已有方向记录迁移到 options: %s -> 反向", self._device_uid)
        self._store_override(CURTAIN_DIR_REVERSED)

    def _store_override(self, value: int) -> None:
        """把期望方向写入 config entry options，网关重启后据此自动补发。"""
        options = dict(self._entry.options or {})
        overrides = dict(options.get(CONF_CURTAIN_DIR_OVERRIDES) or {})
        overrides[self._device_uid] = int(value)
        options[CONF_CURTAIN_DIR_OVERRIDES] = overrides
        self.hass.config_entries.async_update_entry(self._entry, options=options)

    async def async_select_option(self, option: str) -> None:
        """写入网关 curtainDir；电机会重新校准行程。"""
        if option not in OPTIONS:
            return
        value = (
            CURTAIN_DIR_REVERSED if option == OPTION_REVERSED else CURTAIN_DIR_NORMAL
        )
        ok = await self._get_api().set_device_attribute(
            self._device_uid, CURTAIN_DIR_ATTR, value
        )
        if not ok:
            _LOGGER.warning("设置窗帘方向失败: %s -> %s", self._device_uid, option)
            return
        self._attr_current_option = option
        self._store_override(value)
        self.async_write_ha_state()
        self.hass.async_create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        """方向改变后电机通常整程运行一次，短时间内多次刷新位置。"""
        for _ in range(8):
            await asyncio.sleep(5.0)
            await self._coordinator.async_request_refresh()
        self.async_write_ha_state()
