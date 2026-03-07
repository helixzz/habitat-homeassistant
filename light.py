"""Light platform for 栖息地智能家庭."""

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ColorMode,
    LightEntity,
)
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
    api: HabitatAPI = data["api"]
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
            lights.append(HabitatLight(api, coordinator, gateway_device_id, device_uid, name, device))
    async_add_entities(lights)


class HabitatLight(LightEntity):
    """Representation of a Habitat light."""

    def __init__(
        self,
        api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_device_id: str,
        device_uid: str,
        name: str,
        device_data: dict,
    ):
        """Initialize the light."""
        self._api = api
        self._coordinator = coordinator
        self._gateway_device_id = gateway_device_id
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._state = False
        self._brightness = 0
        self._color_temp = 0
        
        self._update_state()

    def _update_state(self):
        """Update state from device data."""
        dev_attrs = self._device_data.get("dev_attrs", [])
        
        for attr in dev_attrs:
            attr_name = attr.get("name")
            attr_value = attr.get("value")
            
            if attr_name == "state":
                self._state = bool(attr_value)
            elif attr_name == "level":
                self._brightness = attr_value
            elif attr_name == "colorTemp":
                self._color_temp = attr_value

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
    def color_temp(self) -> int:
        """Return color temperature."""
        return self._color_temp

    @property
    def color_mode(self) -> ColorMode:
        """Return color mode."""
        return ColorMode.COLOR_TEMP

    @property
    def supported_color_modes(self):
        """Return supported color modes."""
        return {ColorMode.COLOR_TEMP, ColorMode.BRIGHTNESS}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._name,
            manufacturer="栖息地",
            model="色温灯",
            via_device=(DOMAIN, self._gateway_device_id),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        state = 1
        level = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP)
        
        success = await self._api.set_light(
            self._device_uid,
            state=state,
            level=level,
            color_temp=color_temp
        )
        
        if success:
            self._state = True
            if level is not None:
                self._brightness = level
            if color_temp is not None:
                self._color_temp = color_temp
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        success = await self._api.set_light(self._device_uid, state=0)
        
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
