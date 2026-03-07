"""Cover platform for 栖息地智能家庭 (curtains)."""

import asyncio
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, COVER_MODELS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up covers from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid: dict = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_identifier: str = data["gateway_identifier"]
    devices = coordinator.data or []

    inverted_uids = set(
        (config_entry.options or {}).get("inverted_cover_uids") or []
    )
    covers = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)

        if model in COVER_MODELS and online:
            dev_attrs = device.get("dev_attrs", [])
            name = device_uid
            for attr in dev_attrs:
                if attr.get("name") == "devName":
                    name = attr.get("value", device_uid)
                    break
            inverted = device_uid in inverted_uids
            covers.append(HabitatCover(apis_by_uid, primary_uid, default_api, coordinator, gateway_identifier, device_uid, name, device, inverted))
    async_add_entities(covers)


class HabitatCover(CoverEntity):
    """Representation of a Habitat curtain."""

    def __init__(
        self,
        apis_by_uid: dict,
        primary_uid: str,
        default_api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_identifier: str,
        device_uid: str,
        name: str,
        device_data: dict,
        inverted: bool = False,
    ):
        """Initialize the cover. 控制时按设备当前所属网关(childGatewayId)选 API，设备迁移后无需重载。inverted=True 时 HA 开=物理关、HA 关=物理开。"""
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._inverted = inverted
        self._level = 0  # 显示用 0-255：0=关 255=开（与 HA 一致，反向时内部已换算）
        self._attr_device_class = CoverDeviceClass.CURTAIN  # 平开帘
        self._polling_task: asyncio.Task | None = None  # 控制后的短期轮询任务

        self._update_state()

    def _gateway_to_display_level(self, gateway_level: int) -> int:
        """网关 level -> HA 显示 level（0=关 255=开）。"""
        gateway_level = max(0, min(255, gateway_level))
        return (255 - gateway_level) if self._inverted else gateway_level

    def _display_to_gateway_level(self, display_level: int) -> int:
        """HA 显示 level -> 发往网关的 level。"""
        display_level = max(0, min(255, display_level))
        return (255 - display_level) if self._inverted else display_level

    def _get_api(self) -> HabitatAPI:
        """按设备当前所属网关解析 API，设备在网关间迁移后无需重载集成。"""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return self._apis_by_uid.get(child_uid) or self._apis_by_uid.get(self._primary_uid) or self._default_api
        return self._apis_by_uid.get(self._primary_uid) or self._default_api

    def _update_state(self):
        """仅从 curtainLevel 更新；反向时 0/255 对调。"""
        dev_attrs = self._device_data.get("dev_attrs", [])
        for attr in dev_attrs:
            if attr.get("name") != "curtainLevel":
                continue
            raw = attr.get("value") or attr.get("valueStr")
            if raw is None:
                continue
            try:
                level = int(float(raw))
                if 0 <= level <= 100:
                    level = int((level / 100) * 255)
                self._level = self._gateway_to_display_level(max(0, min(255, level)))
            except (TypeError, ValueError):
                pass
            break

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"habitat_cover_{self._device_uid}"

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def is_closed(self) -> bool:
        """Return if cover is closed. 与显示位置一致：0% 即视为关闭，避免 level 舍入后仍显示「已打开」。"""
        return self.current_cover_position == 0

    @property
    def current_cover_position(self) -> int:
        """Return cover position (0-100). HA: 0=closed, 100=open；网关 level 0=关 255=开。"""
        return int((self._level / 255) * 100) if self._level is not None else 0

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return supported features."""
        return (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._name,
            manufacturer="栖息地",
            model="电动窗帘",
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def _refresh_from_gateway(self) -> None:
        """从网关拉取最新设备数据并更新本实体的 level。"""
        await self._coordinator.async_request_refresh()
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break

    def _start_position_polling(self) -> None:
        """控制后启动短期轮询（约 30 秒内每 0.5 秒从网关拉一次），使界面跟上窗帘实际开度。"""
        if self._polling_task is not None:
            self._polling_task.cancel()
        async def _poll_loop() -> None:
            try:
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    await self._refresh_from_gateway()
                    self.async_write_ha_state()
            except asyncio.CancelledError:
                pass
            finally:
                self._polling_task = None
        self._polling_task = self.hass.async_create_task(_poll_loop())

    async def async_open_cover(self, **kwargs: Any) -> None:
        """开帘：HA 开 → 发 gateway level（反向时发 0）。"""
        gw = self._display_to_gateway_level(255)
        success = await self._get_api().set_cover(self._device_uid, level=gw)
        if success:
            self._level = 255
            self.async_write_ha_state()
            self._start_position_polling()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """关帘：HA 关 → 发 gateway level（反向时发 255）。"""
        gw = self._display_to_gateway_level(0)
        success = await self._get_api().set_cover(self._device_uid, level=gw)
        if success:
            self._level = 0
            self.async_write_ha_state()
            self._start_position_polling()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """停止：下发 curtainState=2（停止），网关据此停止电机。"""
        success = await self._get_api().set_cover(self._device_uid, state=2)
        if success:
            await self._refresh_from_gateway()
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """设定开合度：HA 0-100% → 网关 level（反向时已换算）。"""
        position = kwargs.get("position", 0)
        display_level = int((position / 100) * 255)
        display_level = max(0, min(255, display_level))
        gw = self._display_to_gateway_level(display_level)
        success = await self._get_api().set_cover(self._device_uid, level=gw)
        if success:
            self._level = display_level
            self.async_write_ha_state()
            self._start_position_polling()

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
