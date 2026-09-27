"""Switch platform for 栖息地智能家庭."""

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import (
    DOMAIN,
    SWITCH_MODELS,
    SWITCH_CHANNEL_NAME_ATTR_PATTERNS,
    SWITCH_MODEL_CHANNEL_LABELS,
    SWITCH_CHANNEL_FALLBACK,
    SWITCH_MODELS_HIDDEN_BY_DEFAULT,
)

_LOGGER = logging.getLogger(__name__)


def _channel_label_for_switch(dev_attrs: list, model: str, channel_index: int) -> str:
    """从 dev_attrs 或模型默认值解析该通道的显示名称（如 按键1、情景、左键）。"""
    for pattern in SWITCH_CHANNEL_NAME_ATTR_PATTERNS:
        attr_name = pattern.format(i=channel_index)
        for attr in dev_attrs:
            if attr.get("name") == attr_name:
                val = attr.get("value") or attr.get("valueStr")
                if val is not None and str(val).strip():
                    return str(val).strip()
                break
    defaults = SWITCH_MODEL_CHANNEL_LABELS.get(model)
    if defaults and 0 <= channel_index < len(defaults):
        return defaults[channel_index]
    return SWITCH_CHANNEL_FALLBACK.format(i=channel_index + 1)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_device_id: str = data["gateway_device_id"]
    devices = coordinator.data or []

    switches = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)
        
        if model in SWITCH_MODELS and online:
            dev_attrs = device.get("dev_attrs", [])
            name = device_uid
            for attr in dev_attrs:
                if attr.get("name") == "devName":
                    name = attr.get("value", device_uid)
                    break
            
            # Check if it's a multi-button switch (like 4+1 panel)
            switch_count = 0
            for attr in dev_attrs:
                if attr.get("name", "").startswith("state") and not attr.get("name", "").startswith("stateOffset"):
                    try:
                        idx = int(attr.get("name", "").replace("state", ""))
                        if idx >= switch_count:
                            switch_count = idx + 1
                    except:
                        pass
            
            hidden_by_default = model in SWITCH_MODELS_HIDDEN_BY_DEFAULT
            if switch_count > 1:
                for i in range(switch_count):
                    channel_label = _channel_label_for_switch(dev_attrs, model, i)
                    switch_name = f"{name} {channel_label}"
                    switches.append(
                        HabitatSwitch(apis_by_uid, primary_uid, default_api, coordinator, gateway_device_id, device_uid, switch_name, device, i, hidden_by_default)
                    )
            else:
                switches.append(HabitatSwitch(apis_by_uid, primary_uid, default_api, coordinator, gateway_device_id, device_uid, name, device, 0, hidden_by_default))
    
    async_add_entities(switches)


class HabitatSwitch(SwitchEntity):
    """Representation of a Habitat switch."""

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
        switch_index: int,
        entity_registry_visible_default: bool = True,
    ):
        """Initialize the switch. 情景/五合一/多合一面板可传 entity_registry_visible_default=False 默认隐藏。"""
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_device_id = gateway_device_id
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._switch_index = switch_index
        self._state = False
        self._last_control_time: float = 0.0
        self._attr_entity_registry_visible_default = entity_registry_visible_default

        self._update_state()

    def _update_state(self):
        """Update state from device data；控制后 10s 内不覆盖，与灯/窗帘一致。"""
        if time.monotonic() - self._last_control_time < 10.0:
            return
        dev_attrs = self._device_data.get("dev_attrs", [])
        attr_name = f"state{self._switch_index}" if self._switch_index > 0 else "state0"
        for attr in dev_attrs:
            if attr.get("name") == attr_name:
                self._state = bool(attr.get("value", 0))
                break

    def _get_api(self) -> HabitatAPI:
        """按设备当前所属网关解析 API，设备在网关间迁移后无需重载集成。"""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                child_uid = device.get("childGatewayId") or self._primary_uid
                return self._apis_by_uid.get(child_uid) or self._apis_by_uid.get(self._primary_uid) or self._default_api
        return self._apis_by_uid.get(self._primary_uid) or self._default_api

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"habitat_switch_{self._device_uid}_{self._switch_index}"

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._state

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info. All channels share same physical device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._name.rsplit(" ", 1)[0] if " " in self._name else self._name,
            manufacturer="栖息地",
            model="智能开关",
            via_device_id=self._gateway_device_id,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """先乐观更新界面，网关在后台执行。"""
        self._state = True
        self._last_control_time = time.monotonic()
        self.async_write_ha_state()
        self.hass.async_create_task(self._send_switch_and_sync(1))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """先乐观更新界面，网关在后台执行。"""
        self._state = False
        self._last_control_time = time.monotonic()
        self.async_write_ha_state()
        self.hass.async_create_task(self._send_switch_and_sync(0))

    async def _send_switch_and_sync(self, state: int) -> None:
        """后台：发开关指令，失败则拉网关回滚界面。"""
        success = await self._get_api().set_switch(self._device_uid, state, self._switch_index)
        if not success:
            self._last_control_time = 0.0
            await self._coordinator.async_request_refresh()
            for device in self._coordinator.data or []:
                if device.get("deviceUid") == self._device_uid:
                    self._device_data = device
                    self._update_state()
                    break
            self.async_write_ha_state()
            return
        await asyncio.sleep(4.0)
        await self._coordinator.async_request_refresh()
        self._last_control_time = 0.0
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
