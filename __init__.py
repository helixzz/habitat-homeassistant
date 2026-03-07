"""The 栖息地智能家庭 integration."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_PORT, DOMAIN, PLATFORMS
from .api import HabitatAPI

_LOGGER = logging.getLogger(__name__)


def _build_apis_by_uid(entry: ConfigEntry) -> dict[str, HabitatAPI]:
    """主网关来自 entry.data，子网关来自 entry.options.additional_gateways。每个网关使用各自的 UID/密码登录；控制时按设备 childGatewayId 选 API，设备在网关间迁移后无需重载。"""
    config = entry.data
    primary_uid = config.get("uid", "")
    apis: dict[str, HabitatAPI] = {}
    primary_api = HabitatAPI(
        host=config.get("host", "172.16.33.72"),
        access_id=config.get("access_id", "FBee.key"),
        key=config.get("key"),
        uid=primary_uid,
        pwd=config.get("pwd"),
        port=config.get(CONF_PORT, DEFAULT_PORT),
    )
    apis[primary_uid] = primary_api
    for g in (getattr(entry, "options", None) or {}).get("additional_gateways") or []:
        uid = g.get("uid")
        if not uid or not g.get("host") or g.get("key") is None or g.get("pwd") is None:
            continue
        apis[uid] = HabitatAPI(
            host=g["host"],
            access_id="FBee.key",
            key=g["key"],
            uid=uid,
            pwd=g["pwd"],
            port=g.get("port", DEFAULT_PORT),
        )
    return apis


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 栖息地 from a config entry."""
    config = entry.data
    apis_by_uid = _build_apis_by_uid(entry)
    primary_uid = config.get("uid", "")
    api = apis_by_uid.get(primary_uid)

    async def _async_fetch_devices() -> list:
        """从主网关拉取设备列表（主网关可返回主+子网下设备）。"""
        devices = await api.get_devices()
        if not devices:
            raise UpdateFailed("Gateway returned no devices")
        return devices

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_fetch_devices,
        update_interval=timedelta(seconds=60),
    )
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("Found %s devices on gateway", len(coordinator.data))

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
        "apis_by_uid": apis_by_uid,
        "primary_uid": primary_uid,
        "coordinator": coordinator,
        "gateway_device_id": gateway_device.id,
        "gateway_identifier": entry.entry_id,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
