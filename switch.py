"""Switch platform for 栖息地智能家庭."""

import logging
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
    gateway_identifier: str = data["gateway_identifier"]
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
            
            if switch_count > 1:
                for i in range(switch_count):
                    channel_label = _channel_label_for_switch(dev_attrs, model, i)
                    switch_name = f"{name} {channel_label}"
                    switches.append(
                        HabitatSwitch(apis_by_uid, primary_uid, default_api, coordinator, gateway_identifier, device_uid, switch_name, device, i)
                    )
            else:
                switches.append(HabitatSwitch(apis_by_uid, primary_uid, default_api, coordinator, gateway_identifier, device_uid, name, device, 0))
    
    async_add_entities(switches)


class HabitatSwitch(SwitchEntity):
    """Representation of a Habitat switch."""

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
        switch_index: int,
    ):
        """Initialize the switch. 控制时按设备当前所属网关(childGatewayId)选 API。"""
        self._apis_by_uid = apis_by_uid or {}
        self._primary_uid = primary_uid
        self._default_api = default_api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._switch_index = switch_index
        self._state = False
        
        self._update_state()

    def _update_state(self):
        """Update state from device data."""
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
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        success = await self._get_api().set_switch(self._device_uid, 1, self._switch_index)
        
        if success:
            self._state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        success = await self._get_api().set_switch(self._device_uid, 0, self._switch_index)
        
        if success:
            self._state = False
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
