"""Fan 平台：五合一面板主面板 — 新风送风，归入 HA 原生「风扇」类别。"""

import asyncio
import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, PANEL_5IN1_MODELS, FAN_LEVEL_AUTO
from .helpers import get_attr_value, is_main_panel

_LOGGER = logging.getLogger(__name__)

NEWWIND_PRESET_AUTO = "auto"
# 1-6 档映射到百分比（约 16, 33, 50, 66, 83, 100）
LEVEL_TO_PERCENT = (0, 16, 33, 50, 66, 83, 100)


def _level_from_percentage(percentage: int) -> int:
    """0 -> 0, 1-100 -> 1-6 档。"""
    if percentage <= 0:
        return 0
    for level in range(6, 0, -1):
        if percentage >= LEVEL_TO_PERCENT[level]:
            return level
    return 1


def _percentage_from_level(level: int) -> int:
    if 0 <= level <= 6:
        return LEVEL_TO_PERCENT[level]
    return 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """仅为主面板创建新风 Fan 实体（英文 UI 显示 Fresh Air）。"""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid = data.get("apis_by_uid") or {}
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

        if model not in PANEL_5IN1_MODELS or not online or not is_main_panel(dev_attrs):
            continue

        name = device_uid
        for attr in dev_attrs:
            if attr.get("name") == "devName":
                name = attr.get("value", device_uid)
                break

        entities.append(
            HabitatFan(
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


class HabitatFan(FanEntity):
    """主面板新风送风：0-6 档 + 自动，对应 HA 风扇的 percentage 与 preset_mode。"""

    _attr_translation_key = "fresh_air"
    _attr_preset_modes = [NEWWIND_PRESET_AUTO]
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    )

    def __init__(
        self,
        apis_by_uid: dict,
        primary_uid: str,
        default_api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_identifier: str,
        device_uid: str,
        device_name: str,
        device_data: dict,
    ):
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._device_name = device_name
        self._device_data = device_data
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
        level_raw = get_attr_value(dev_attrs, "newWind11Fanlevel")
        mode_raw = get_attr_value(dev_attrs, "newWindMode")
        try:
            level = int(level_raw) if level_raw is not None else 0
            is_auto = int(mode_raw) == 2 if mode_raw is not None else False
            if level == 0 and is_auto:
                self._attr_percentage = None
                self._attr_preset_mode = NEWWIND_PRESET_AUTO
                self._attr_is_on = True
            elif 0 <= level <= 6:
                self._attr_percentage = _percentage_from_level(level)
                self._attr_preset_mode = None
                self._attr_is_on = level > 0
            else:
                self._attr_percentage = 0
                self._attr_preset_mode = None
                self._attr_is_on = False
        except (TypeError, ValueError):
            self._attr_percentage = 0
            self._attr_preset_mode = None
            self._attr_is_on = False

    @property
    def unique_id(self) -> str:
        return f"habitat_fan_fresh_air_{self._device_uid}"

    @property
    def name(self) -> str:
        return "新风送风"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._device_name,
            manufacturer="栖息地",
            model="五合一面板",
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        if preset_mode == NEWWIND_PRESET_AUTO:
            await self.async_set_preset_mode(NEWWIND_PRESET_AUTO)
            return
        if percentage is not None and percentage > 0:
            await self.async_set_percentage(percentage)
            return
        # turn_on with no args: set level 1
        await self.async_set_percentage(LEVEL_TO_PERCENT[1])

    async def async_turn_off(self) -> None:
        api = self._get_api()
        ok = await api.set_device_attribute(
            self._device_uid, "newWind11Fanlevel", 0
        )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_percentage = 0
        self._attr_preset_mode = None
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.async_create_task(self._delay_refresh())

    async def async_set_percentage(self, percentage: int) -> None:
        level = _level_from_percentage(percentage)
        api = self._get_api()
        ok = await api.set_device_attribute(
            self._device_uid, "newWind11Fanlevel", level
        )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_percentage = percentage if percentage > 0 else 0
        self._attr_preset_mode = None
        self._attr_is_on = level > 0
        self.async_write_ha_state()
        self.hass.async_create_task(self._delay_refresh())

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode != NEWWIND_PRESET_AUTO:
            return
        api = self._get_api()
        ok = await api.set_device_attribute(
            self._device_uid, "newWind11Fanlevel", 0
        )
        if ok:
            ok = await api.set_device_attribute(
                self._device_uid, "newWindMode", 2
            )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_percentage = None
        self._attr_preset_mode = NEWWIND_PRESET_AUTO
        self._attr_is_on = True
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
