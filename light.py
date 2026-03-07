"""Light platform for 栖息地智能家庭."""

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.color import (
    color_temperature_kelvin_to_mired,
    color_temperature_mired_to_kelvin,
)

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
        # 网关通常使用 mired 表示色温，内部保存 mired
        self._color_temp_mired = 0

        self._update_state()

    def _get_api(self) -> HabitatAPI:
        """按设备当前所属网关解析 API，设备在网关间迁移后无需重载集成。"""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return self._apis_by_uid.get(child_uid) or self._apis_by_uid.get(self._primary_uid) or self._default_api
        return self._apis_by_uid.get(self._primary_uid) or self._default_api

    def _update_state(self):
        """Update state from device data."""
        dev_attrs = self._device_data.get("dev_attrs", [])
        for attr in dev_attrs:
            attr_name = attr.get("name")
            attr_value = attr.get("value")
            if attr_name == "state":
                self._state = bool(attr_value)
            elif attr_name == "level":
                try:
                    self._brightness = int(attr_value) if attr_value is not None else 0
                except (TypeError, ValueError):
                    self._brightness = 0
            elif attr_name == "colorTemp":
                try:
                    self._color_temp_mired = int(attr_value) if attr_value is not None else 0
                except (TypeError, ValueError):
                    self._color_temp_mired = 0

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
    def color_temp_kelvin(self) -> int | None:
        """Return color temperature in Kelvin (gateway uses mired)."""
        if self._color_temp_mired <= 0:
            return None
        return int(color_temperature_mired_to_kelvin(self._color_temp_mired))

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return minimum color temperature in Kelvin."""
        return 2000

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return maximum color temperature in Kelvin."""
        return 6500

    @property
    def color_mode(self) -> ColorMode:
        """Return color mode."""
        return ColorMode.COLOR_TEMP

    @property
    def supported_color_modes(self):
        """Return supported color modes. CCT light: COLOR_TEMP 已包含亮度调节，不可与 BRIGHTNESS 同时声明。"""
        return {ColorMode.COLOR_TEMP}

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
        """Turn on the light. 栖息地色温灯亮度与色温绑定，每次只下发一个量（优先亮度），另一量由设备联动。"""
        state = 1
        level = kwargs.get("brightness")
        color_temp_kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        color_temp_mired = (
            int(color_temperature_kelvin_to_mired(color_temp_kelvin))
            if color_temp_kelvin is not None
            else None
        )
        # 只传用户本次修改的量，避免同时设两个导致设备行为异常；若两个都有则优先亮度
        send_level = level if level is not None else None
        send_color_temp = None
        if color_temp_kelvin is not None:
            send_color_temp = color_temp_mired
        if level is not None and color_temp_mired is not None:
            send_color_temp = None  # 两样都传时只发亮度，色温由设备联动
        success = await self._get_api().set_light(
            self._device_uid,
            state=state,
            level=send_level,
            color_temp=send_color_temp,
        )
        if success:
            await self._coordinator.async_request_refresh()
            for device in self._coordinator.data or []:
                if device.get("deviceUid") == self._device_uid:
                    self._device_data = device
                    self._update_state()
                    break
            self._state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        success = await self._get_api().set_light(self._device_uid, state=0)
        if success:
            await self._coordinator.async_request_refresh()
            for device in self._coordinator.data or []:
                if device.get("deviceUid") == self._device_uid:
                    self._device_data = device
                    self._update_state()
                    break
            self._state = False
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
