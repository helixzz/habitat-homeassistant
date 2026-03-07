"""The 栖息地智能家庭 integration."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_PORT, DOMAIN, PLATFORMS, UPDATE_INTERVAL_SEC
from .api import HabitatAPI

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 栖息地 from a config entry."""
    config = entry.data
    api = HabitatAPI(
        host=config.get("host", "172.16.33.72"),
        access_id=config.get("access_id", "FBee.key"),
        key=config.get("key"),
        uid=config.get("uid"),
        pwd=config.get("pwd"),
        port=config.get(CONF_PORT, DEFAULT_PORT),
    )

    async def _async_fetch_devices() -> list:
        """Fetch device list from gateway."""
        devices = await api.get_devices()
        if not devices:
            raise UpdateFailed("Gateway returned no devices")
        return devices

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_fetch_devices,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SEC),
    )
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("Found %s devices on gateway", len(coordinator.data))

    # Register gateway as a device so sub-devices can use via_device
    dev_reg = dr.async_get(hass)
    gateway_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="栖息地",
        model="Zigbee 网关",
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "gateway_device_id": gateway_device.id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
