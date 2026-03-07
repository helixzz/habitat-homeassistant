"""Humidifier 平台：五合一面板新风加湿 — 湿度目标，归入 HA 原生「加湿器」类别。"""

import asyncio
import logging

from homeassistant.components.humidifier import HumidifierEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, PANEL_5IN1_MODELS
from .helpers import get_attr_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """为五合一面板创建 Humidifier 实体（湿度目标，新风按此加湿）。"""
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

        if model not in PANEL_5IN1_MODELS or not online:
            continue

        name = device_uid
        for attr in dev_attrs:
            if attr.get("name") == "devName":
                name = attr.get("value", device_uid)
                break

        entities.append(
            HabitatHumidifier(
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


class HabitatHumidifier(HumidifierEntity):
    """五合一面板加湿器实体：当前湿度、目标湿度可读写，新风按目标加湿。"""

    _attr_min_humidity = 0
    _attr_max_humidity = 100
    _attr_target_humidity_step = 1

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
        cur = get_attr_value(dev_attrs, "humidity")
        tgt = get_attr_value(dev_attrs, "newWindSetHumi")
        try:
            self._attr_current_humidity = (
                int(cur) / 10.0 if cur is not None else None
            )
            self._attr_target_humidity = (
                int(tgt) / 10.0 if tgt is not None else None
            )
        except (TypeError, ValueError):
            self._attr_current_humidity = None
            self._attr_target_humidity = None
        # 有目标即视为“开启”加湿逻辑
        self._attr_is_on = self._attr_target_humidity is not None

    @property
    def unique_id(self) -> str:
        return f"habitat_humidifier_{self._device_uid}"

    @property
    def name(self) -> str:
        return "湿度目标"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._device_name,
            manufacturer="栖息地",
            model="五合一面板",
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_set_humidity(self, humidity: int) -> None:
        api = self._get_api()
        ok = await api.set_device_attribute(
            self._device_uid, "newWindSetHumi", int(round(humidity * 10))
        )
        if not ok:
            await self._coordinator.async_request_refresh()
            self._refresh_device_data()
            self.async_write_ha_state()
            return
        self._attr_target_humidity = float(humidity)
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
