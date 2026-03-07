"""Light platform for 栖息地智能家庭."""

import logging
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
    gateway_identifier: str = data["gateway_identifier"]
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
            lights.append(HabitatLight(apis_by_uid, primary_uid, default_api, coordinator, gateway_identifier, device_uid, name, device))
    async_add_entities(lights)


class HabitatLight(LightEntity):
    """Representation of a Habitat light."""

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
    ):
        """Initialize the light. 控制时按设备当前所属网关(childGatewayId)选 API。"""
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._state = False
        self._brightness = 0

        self._update_state()

    def _get_api(self) -> HabitatAPI:
        """按设备当前所属网关解析 API，设备在网关间迁移后无需重载集成。"""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return self._apis_by_uid.get(child_uid) or self._apis_by_uid.get(self._primary_uid) or self._default_api
        return self._apis_by_uid.get(self._primary_uid) or self._default_api

    def _update_state(self):
        """Update state from device data. 网关 level 为 0-255，与 HA 一致。"""
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
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light. 先乐观更新界面，再发网关，失败则回滚。"""
        level_ha = kwargs.get("brightness")
        # 先写状态再调 API，界面立即刷新，不依赖网关响应
        old_state = self._state
        old_brightness = self._brightness
        self._state = True
        if level_ha is not None:
            self._brightness = level_ha
        elif not self._brightness:
            self._brightness = 255
        self.async_write_ha_state()
        success = await self._get_api().set_light(
            self._device_uid,
            state=1,
            level=level_ha if level_ha is not None else None,
            color_temp=None,
        )
        if not success:
            self._state = old_state
            self._brightness = old_brightness
            self.async_write_ha_state()
            return
        self.hass.async_create_task(self._refresh_and_write_state())

    async def _refresh_and_write_state(self) -> None:
        """后台从 coordinator 拉取最新设备数据并更新实体状态（用于控制后与网关同步）。"""
        await self._coordinator.async_request_refresh()
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light. 先乐观更新界面，再发网关。"""
        old_state = self._state
        self._state = False
        self.async_write_ha_state()
        success = await self._get_api().set_light(self._device_uid, state=0)
        if not success:
            self._state = old_state
            self.async_write_ha_state()
            return
        self.hass.async_create_task(self._refresh_and_write_state())

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
