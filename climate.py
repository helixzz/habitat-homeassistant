"""Climate 平台：五合一面板空调 — 温度目标 + 空调风速，归入 HA 原生「气候」类别。"""

import asyncio
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, PANEL_5IN1_MODELS, FAN_LEVEL_AUTO
from .helpers import get_attr_value, is_main_panel

_LOGGER = logging.getLogger(__name__)

# 空调风速：0=关 1-6=档位 7=自动，对应 HA 气候实体的 fan_mode
AC_FAN_MODES = ["off", "1", "2", "3", "4", "5", "6", "auto"]


def _fan_level_from_mode(mode: str) -> int | None:
    """HA fan_mode -> 网关档位。'auto' 需配合 airCond3Mode=2，档位写 0。"""
    if mode == "off":
        return 0
    if mode == "auto":
        return FAN_LEVEL_AUTO  # 调用方写 level=0 + mode=2
    if mode in ("1", "2", "3", "4", "5", "6"):
        return int(mode)
    return None


def _fan_mode_from_attrs(dev_attrs: list) -> str:
    """从 dev_attrs 得到当前空调风速对应的 fan_mode 字符串。"""
    level_raw = get_attr_value(dev_attrs, "airCond11Fanlevel")
    mode_raw = get_attr_value(dev_attrs, "airCond3Mode")
    try:
        level = int(level_raw) if level_raw is not None else 0
        mode_auto = int(mode_raw) == 2 if mode_raw is not None else False
        if level == 0 and mode_auto:
            return "auto"
        if 0 <= level <= 6:
            return "off" if level == 0 else str(level)
    except (TypeError, ValueError):
        pass
    return "off"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为五合一面板创建 Climate 实体（室温目标 + 空调风速）。"""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_device_id: str = data["gateway_device_id"]
    devices = coordinator.data or []

    entities = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)
        dev_attrs = device.get("dev_attrs", [])

        if model not in PANEL_5IN1_MODELS or not online:
            continue

        name = device_uid
        for attr in dev_attrs:
            if attr.get("name") == "devName":
                name = attr.get("value", device_uid)
                break

        entities.append(
            HabitatClimate(
                apis_by_uid,
                primary_uid,
                default_api,
                coordinator,
                gateway_device_id,
                device_uid,
                name,
                device,
            )
        )

    async_add_entities(entities)


class HabitatClimate(ClimateEntity):
    """五合一面板气候实体：当前温度、目标温度、空调风速；仅支持自动制热/制冷。"""

    _attr_hvac_modes = [HVACMode.HEAT_COOL]
    _attr_fan_modes = AC_FAN_MODES
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        apis_by_uid: dict,
        primary_uid: str,
        default_api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_device_id: str,
        device_uid: str,
        device_name: str,
        device_data: dict,
    ):
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_device_id = gateway_device_id
        self._device_uid = device_uid
        self._device_name = device_name
        self._device_data = device_data
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )
        self._update_state()

    def _get_api(self) -> HabitatAPI:
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return (
                    self._apis_by_uid.get(child_uid)
                    or self._apis_by_uid.get(self._primary_uid)
                    or self._default_api
                )
        return self._default_api

    def _update_state(self) -> None:
        dev_attrs = self._device_data.get("dev_attrs", [])
        t = get_attr_value(dev_attrs, "temperature")
        s = get_attr_value(dev_attrs, "roomSettemp")
        try:
            self._attr_current_temperature = int(t) / 10.0 if t is not None else None
            self._attr_target_temperature = int(s) / 10.0 if s is not None else None
        except (TypeError, ValueError):
            self._attr_current_temperature = None
            self._attr_target_temperature = None
        self._attr_fan_mode = _fan_mode_from_attrs(dev_attrs)
        self._attr_hvac_mode = HVACMode.HEAT_COOL

    @property
    def unique_id(self) -> str:
        return f"habitat_climate_{self._device_uid}"

    @property
    def name(self) -> str:
        return "空调"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._device_name,
            manufacturer="栖息地",
            model="五合一面板",
            via_device_id=self._gateway_device_id,
        )

    async def async_set_temperature(self, **kwargs) -> None:
        target = kwargs.get("temperature")
        if target is None:
            return
        api = self._get_api()
        ok = await api.set_device_attribute(
            self._device_uid, "roomSettemp", int(round(target * 10))
        )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_target_temperature = target
        self.async_write_ha_state()
        self.hass.async_create_task(self._delay_refresh())

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        api = self._get_api()
        level = _fan_level_from_mode(fan_mode)
        if level is None:
            return
        if level == FAN_LEVEL_AUTO:
            ok = await api.set_device_attribute(self._device_uid, "airCond11Fanlevel", 0)
            if ok:
                ok = await api.set_device_attribute(
                    self._device_uid, "airCond3Mode", 2
                )
        else:
            ok = await api.set_device_attribute(
                self._device_uid, "airCond11Fanlevel", level
            )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()
        self.hass.async_create_task(self._delay_refresh())

    def _refresh_device_data(self) -> None:
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break

    async def _delay_refresh(self) -> None:
        await asyncio.sleep(4.0)
        await self._coordinator.async_request_refresh()
        self._refresh_device_data()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        self._refresh_device_data()
