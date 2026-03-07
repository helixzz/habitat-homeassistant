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
from .const import DOMAIN, SWITCH_MODELS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    api: HabitatAPI = data["api"]
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
            
            if switch_count > 1:
                for i in range(switch_count):
                    switch_name = f"{name} {i+1}" if switch_count > 1 else name
                    switches.append(
                        HabitatSwitch(api, coordinator, gateway_device_id, device_uid, switch_name, device, i)
                    )
            else:
                switches.append(HabitatSwitch(api, coordinator, gateway_device_id, device_uid, name, device, 0))
    
    async_add_entities(switches)


class HabitatSwitch(SwitchEntity):
    """Representation of a Habitat switch."""

    def __init__(
        self,
        api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_device_id: str,
        device_uid: str,
        name: str,
        device_data: dict,
        switch_index: int,
    ):
        """Initialize the switch."""
        self._api = api
        self._coordinator = coordinator
        self._gateway_device_id = gateway_device_id
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
            via_device=(DOMAIN, self._gateway_device_id),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        success = await self._api.set_switch(self._device_uid, 1, self._switch_index)
        
        if success:
            self._state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        success = await self._api.set_switch(self._device_uid, 0, self._switch_index)
        
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
