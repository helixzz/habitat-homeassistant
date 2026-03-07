"""Cover platform for 栖息地智能家庭 (curtains)."""

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
    api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_identifier: str = data["gateway_identifier"]
    devices = coordinator.data or []

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
            covers.append(HabitatCover(api, coordinator, gateway_identifier, device_uid, name, device))
    async_add_entities(covers)


class HabitatCover(CoverEntity):
    """Representation of a Habitat curtain."""

    def __init__(
        self,
        api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_identifier: str,
        device_uid: str,
        name: str,
        device_data: dict,
    ):
        """Initialize the cover."""
        self._api = api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._level = 0  # 仅用 curtainLevel：0-255，0=关 255=开（不依赖 curtainState/curtainDir）
        self._attr_device_class = CoverDeviceClass.CURTAIN  # 平开帘

        self._update_state()

    def _update_state(self):
        """仅从 curtainLevel 更新；curtainState、curtainDir 实测常为 2/0 且无需关注。"""
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
                self._level = max(0, min(255, level))
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
        """Return if cover is closed. 与电机方向统一：level 0 = 关闭。"""
        return self._level == 0

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
        """从网关拉取最新设备数据并更新本实体的 level，保证界面显示与网关一致。"""
        await self._coordinator.async_request_refresh()
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break

    async def async_open_cover(self, **kwargs: Any) -> None:
        """开帘：仅下发 curtainLevel=255。"""
        success = await self._api.set_cover(self._device_uid, level=255)
        if success:
            await self._refresh_from_gateway()
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """关帘：仅下发 curtainLevel=0。"""
        success = await self._api.set_cover(self._device_uid, level=0)
        if success:
            await self._refresh_from_gateway()
            self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """停止：下发当前 level 以保持位置（仅用 curtainLevel 时无单独 stop 命令）。"""
        success = await self._api.set_cover(self._device_uid, level=self._level)
        if success:
            await self._refresh_from_gateway()
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """设定开合度：仅下发 curtainLevel。HA 0=关 100=开 → level 0-255。"""
        position = kwargs.get("position", 0)
        level = int((position / 100) * 255)
        level = max(0, min(255, level))
        success = await self._api.set_cover(self._device_uid, level=level)
        if success:
            await self._refresh_from_gateway()
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
