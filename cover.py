"""Cover platform for 栖息地智能家庭 (curtains)."""

import logging
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import HabitatAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_TYPE_CURTAIN = "ZT21LGJ"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up covers from a config entry."""
    api: HabitatAPI = hass.data[DOMAIN][config_entry.entry_id]
    devices = api.get_devices()
    
    covers = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)
        
        if model == DEVICE_TYPE_CURTAIN and online:
            dev_attrs = device.get("dev_attrs", [])
            name = device_uid
            for attr in dev_attrs:
                if attr.get("name") == "devName":
                    name = attr.get("value", device_uid)
                    break
            
            covers.append(HabitatCover(api, device_uid, name, device))
    
    async_add_entities(covers)


class HabitatCover(CoverEntity):
    """Representation of a Habitat curtain."""

    def __init__(self, api: HabitatAPI, device_uid: str, name: str, device_data: dict):
        """Initialize the cover."""
        self._api = api
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._state = 2  # 0=open, 1=closing, 2=closed
        self._level = 0  # 0-255, 0=open
        
        self._update_state()

    def _update_state(self):
        """Update state from device data."""
        dev_attrs = self._device_data.get("dev_attrs", [])
        
        for attr in dev_attrs:
            attr_name = attr.get("name")
            attr_value = attr.get("value")
            
            if attr_name == "curtainState":
                self._state = attr_value
            elif attr_name == "curtainLevel":
                self._level = attr_value

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"habitat_cover_{self._device_uid}"

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def is_closed(self) -> bool:
        """Return if cover is closed."""
        # 0 = open, 2 = closed
        return self._state == 2

    @property
    def current_cover_position(self) -> int:
        """Return cover position (0-100)."""
        # level 255 = fully closed, 0 = fully open
        position = int((self._level / 255) * 100)
        return 100 - position  # Invert: HA: 0=closed, 100=open

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Return supported features."""
        return CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._name,
            manufacturer="栖息地",
            model="电动窗帘",
            via_device=(DOMAIN, self._device_uid),
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # state 0 = open
        success = self._api.set_cover(self._device_uid, state=0, level=0)
        
        if success:
            self._state = 0
            self._level = 0
            self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        # state 1 = close
        success = self._api.set_cover(self._device_uid, state=1, level=255)
        
        if success:
            self._state = 2
            self._level = 255
            self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        # state 2 = stop
        success = self._api.set_cover(self._device_uid, state=2)
        
        if success:
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity."""
        devices = self._api.get_devices()
        for device in devices:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
