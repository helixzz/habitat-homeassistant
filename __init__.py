"""The 栖息地智能家庭 integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .api import HabitatAPI

_LOGGER = logging.getLogger(__name__)

habitat_config = {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 栖息地 from a config entry."""
    
    config = entry.data
    api = HabitatAPI(
        host=config.get("host", "172.16.33.72"),
        access_id=config.get("access_id", "FBee.key"),
        key=config.get("key"),
        uid=config.get("uid"),
        pwd=config.get("pwd")
    )
    
    # Test connection
    devices = api.get_devices()
    if not devices:
        _LOGGER.error("Failed to connect to Habitat gateway")
        return False
    
    _LOGGER.info(f"Found {len(devices)} devices on gateway")
    
    # Store API instance
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = api
    
    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
