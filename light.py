"""Light platform for 栖息地智能家庭."""

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, LIGHT_MODELS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lights from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_device_id: str = data["gateway_device_id"]
    devices = coordinator.data or []

    lights = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)

        if model in LIGHT_MODELS and online:
            dev_attrs = device.get("dev_attrs", [])
            name = device_uid
            for attr in dev_attrs:
                if attr.get("name") == "devName":
                    name = attr.get("value", device_uid)
                    break
            lights.append(HabitatLight(apis_by_uid, primary_uid, default_api, coordinator, gateway_device_id, device_uid, name, device))
    async_add_entities(lights)


class HabitatLight(LightEntity):
    """Representation of a Habitat light."""

    def __init__(
        self,
        apis_by_uid: dict,
        primary_uid: str,
        default_api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_device_id: str,
        device_uid: str,
        name: str,
        device_data: dict,
    ):
        """Initialize the light. 控制时按设备当前所属网关(childGatewayId)选 API。"""
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_device_id = gateway_device_id
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._state = False
        self._brightness = 0
        # 控制后一段时间内不允许多源用网关数据覆盖开关/亮度，避免界面被滞后数据改回
        self._last_control_time: float = 0.0

        self._update_state()

    def _get_api(self) -> HabitatAPI:
        """按设备当前所属网关解析 API，设备在网关间迁移后无需重载集成。"""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return self._apis_by_uid.get(child_uid) or self._apis_by_uid.get(self._primary_uid) or self._default_api
        return self._apis_by_uid.get(self._primary_uid) or self._default_api

    def _update_state(self):
        """Update state from device data. 控制后 10 秒内不覆盖开关/亮度，避免网关滞后数据把界面改回。"""
        if time.monotonic() - self._last_control_time < 10.0:
            return
        dev_attrs = self._device_data.get("dev_attrs", [])
        for attr in dev_attrs:
            attr_name = attr.get("name")
            raw = attr.get("value") if attr.get("value") is not None else attr.get("valueStr")
            if attr_name == "state":
                try:
                    self._state = bool(int(raw)) if raw is not None else False
                except (TypeError, ValueError):
                    self._state = False
            elif attr_name == "level":
                try:
                    val = int(float(raw)) if raw is not None else 0
                    self._brightness = max(0, min(255, val))
                except (TypeError, ValueError):
                    self._brightness = 0

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"habitat_light_{self._device_uid}"

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state

    @property
    def brightness(self) -> int:
        """Return brightness (0-255)."""
        return self._brightness

    @property
    def color_mode(self) -> ColorMode:
        """Return color mode."""
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self):
        """Return supported color modes. 仅开关+亮度，色温由设备侧控制。"""
        return {ColorMode.BRIGHTNESS}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._name,
            manufacturer="栖息地",
            model="色温灯",
            via_device_id=self._gateway_device_id,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light. 立即写状态并返回，网关请求在后台执行，避免前端等半分钟才刷新开关。"""
        level_ha = kwargs.get("brightness")
        old_state = self._state
        old_brightness = self._brightness
        self._state = True
        if level_ha is not None:
            self._brightness = level_ha
        elif not self._brightness:
            self._brightness = 255
        self._last_control_time = time.monotonic()
        self.async_write_ha_state()
        # 不 await 网关，使服务调用立即返回；控制后 10s 内 _update_state 不覆盖，避免滞后数据改回
        self.hass.async_create_task(
            self._send_turn_on_and_sync(level_ha, old_state, old_brightness)
        )

    async def _send_turn_on_and_sync(
        self, level_ha: int | None, old_state: bool, old_brightness: int
    ) -> None:
        """后台：发开灯指令，失败回滚，成功则拉取网关状态同步。"""
        success = await self._get_api().set_light(
            self._device_uid,
            state=1,
            level=level_ha,
            color_temp=None,
        )
        if not success:
            self._state = old_state
            self._brightness = old_brightness
            self.async_write_ha_state()
            return
        # 延迟 4 秒再拉网关，给网关时间更新设备列表，减少用旧数据覆盖界面
        self.hass.async_create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        """等待 4 秒后拉取网关状态并写回实体。"""
        await asyncio.sleep(4.0)
        await self._refresh_and_write_state()

    async def _refresh_and_write_state(self) -> None:
        """后台拉取设备数据并更新实体；本次为延迟同步，允许覆盖。"""
        await self._coordinator.async_request_refresh()
        self._last_control_time = 0.0
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light. 立即写状态并返回，网关在后台执行。"""
        old_state = self._state
        self._state = False
        self._last_control_time = time.monotonic()
        self.async_write_ha_state()
        self.hass.async_create_task(self._send_turn_off_and_sync(old_state))

    async def _send_turn_off_and_sync(self, old_state: bool) -> None:
        """后台：发关灯指令，失败回滚，成功则拉取网关状态同步。"""
        success = await self._get_api().set_light(self._device_uid, state=0)
        if not success:
            self._state = old_state
            self.async_write_ha_state()
            return
        self.hass.async_create_task(self._delayed_refresh())

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
