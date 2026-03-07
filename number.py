"""Number platform for 栖息地智能家庭 — 五合一面板室温目标、湿度目标、空调/新风风速."""

import asyncio
import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, PANEL_5IN1_MODELS, FAN_LEVEL_AUTO
from .helpers import get_attr_value, is_main_panel

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为五合一面板创建设定温度、设定湿度、空调风速；主面板额外新风风速。"""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_identifier: str = data["gateway_identifier"]
    devices = coordinator.data or []

    numbers = []
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

        main = is_main_panel(dev_attrs)

        numbers.append(
            HabitatNumber(
                apis_by_uid,
                primary_uid,
                default_api,
                coordinator,
                gateway_identifier,
                device_uid,
                name,
                "室温目标",
                device,
                "roomSettemp",
                native_min=16.0,
                native_max=30.0,
                step=0.5,
                unit=UnitOfTemperature.CELSIUS,
                scale=10,
            )
        )
        numbers.append(
            HabitatNumber(
                apis_by_uid,
                primary_uid,
                default_api,
                coordinator,
                gateway_identifier,
                device_uid,
                name,
                "湿度目标",
                device,
                "newWindSetHumi",
                native_min=0,
                native_max=100,
                step=1,
                unit=PERCENTAGE,
                scale=10,
            )
        )
        numbers.append(
            HabitatNumber(
                apis_by_uid,
                primary_uid,
                default_api,
                coordinator,
                gateway_identifier,
                device_uid,
                name,
                "空调风速",
                device,
                "airCond11Fanlevel",
                native_min=0,
                native_max=FAN_LEVEL_AUTO,
                step=1,
                unit=None,
                scale=1,
                mode_attr="airCond3Mode",
                mode_value_auto=2,
            )
        )
        if main:
            numbers.append(
                HabitatNumber(
                    apis_by_uid,
                    primary_uid,
                    default_api,
                    coordinator,
                    gateway_identifier,
                    device_uid,
                    name,
                    "新风送风风速",
                    device,
                    "newWind11Fanlevel",
                    native_min=0,
                    native_max=FAN_LEVEL_AUTO,
                    step=1,
                    unit=None,
                    scale=1,
                    mode_attr="newWindMode",
                    mode_value_auto=2,
                )
            )

    async_add_entities(numbers)


class HabitatNumber(NumberEntity):
    """五合一面板可调数值：室温目标、湿度目标、空调/新风风速。"""

    def __init__(
        self,
        apis_by_uid: dict,
        primary_uid: str,
        default_api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_identifier: str,
        device_uid: str,
        device_name: str,
        entity_name: str,
        device_data: dict,
        attr_name: str,
        *,
        native_min: float,
        native_max: float,
        step: float,
        unit: str | None,
        scale: float = 1,
        mode_attr: str | None = None,
        mode_value_auto: int | None = None,
    ):
        """scale: 网关值 = native_value * scale（如 0.1°C 则 scale=10）。风速 7=自动时写 attr=0 并设 mode_attr=mode_value_auto。"""
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._device_name = device_name
        self._entity_name = entity_name
        self._device_data = device_data
        self._attr_name = attr_name
        self._native_min = native_min
        self._native_max = native_max
        self._step = step
        self._unit = unit
        self._scale = scale
        self._mode_attr = mode_attr
        self._mode_value_auto = mode_value_auto
        # 与 Climate/Humidifier/Fan 重复，默认隐藏；可在 设置→实体 中取消隐藏
        self._attr_entity_registry_visible_default = False
        self._update_state()

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

    def _update_state(self) -> None:
        """从 device_data 更新当前显示值。风速 0+自动模式时显示为 7。"""
        dev_attrs = self._device_data.get("dev_attrs", [])
        raw = get_attr_value(dev_attrs, self._attr_name)
        if raw is None:
            self._attr_native_value = None
            return
        try:
            v = int(raw)
            if self._scale != 1:
                self._attr_native_value = v / self._scale
            else:
                self._attr_native_value = float(v)
                if self._mode_attr and self._mode_value_auto is not None:
                    mode_raw = get_attr_value(dev_attrs, self._mode_attr)
                    if mode_raw is not None and int(mode_raw) == self._mode_value_auto and v == 0:
                        self._attr_native_value = float(FAN_LEVEL_AUTO)
        except (TypeError, ValueError):
            self._attr_native_value = None

    @property
    def unique_id(self) -> str:
        return f"habitat_number_{self._device_uid}_{self._attr_name}"

    @property
    def name(self) -> str:
        return self._entity_name

    @property
    def native_value(self) -> float | None:
        return self._attr_native_value

    @property
    def native_min_value(self) -> float:
        return self._native_min

    @property
    def native_max_value(self) -> float:
        return self._native_max

    @property
    def native_step(self) -> float:
        return self._step

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._unit

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._device_name,
            manufacturer="栖息地",
            model="五合一面板",
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_set_native_value(self, value: float) -> None:
        """写入网关：温度/湿度为 value*scale；风速 7=自动时写 0 并设 mode。"""
        api = self._get_api()
        if self._scale != 1:
            gateway_value = int(round(value * self._scale))
        else:
            gateway_value = int(round(value))
            if self._mode_attr and gateway_value == FAN_LEVEL_AUTO:
                ok = await api.set_device_attribute(
                    self._device_uid, self._attr_name, 0
                )
                if ok and self._mode_value_auto is not None:
                    ok = await api.set_device_attribute(
                        self._device_uid,
                        self._mode_attr,
                        self._mode_value_auto,
                    )
                if not ok:
                    await self._coordinator.async_request_refresh()
                    self._refresh_device_data()
                    self.async_write_ha_state()
                    return
                self._attr_native_value = value
                self.async_write_ha_state()
                self.hass.async_create_task(self._delay_refresh())
                return

        ok = await api.set_device_attribute(
            self._device_uid, self._attr_name, gateway_value
        )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_native_value = value
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
