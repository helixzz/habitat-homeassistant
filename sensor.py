"""Sensor platform for 栖息地智能家庭."""

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, SENSOR_MODELS, AC_MODELS, FA_MODEL, GA_MODEL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_identifier: str = data["gateway_identifier"]
    devices = coordinator.data or []

    sensors = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)
        
        dev_attrs = device.get("dev_attrs", [])
        
        # Get device name
        name = device_uid
        for attr in dev_attrs:
            if attr.get("name") == "devName":
                name = attr.get("value", device_uid)
                break
        
        # 五合一传感器 (environmental sensor)
        if model in SENSOR_MODELS and online:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 温度", device, "temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 湿度", device, "humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} PM2.5", device, "PM2_5U", SensorDeviceClass.PM25, "μg/m³")
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} PM10", device, "PM10U", SensorDeviceClass.PM10, "μg/m³")
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} CO2", device, "CO2M", SensorDeviceClass.CO2, CONCENTRATION_PARTS_PER_MILLION)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} AQI", device, "homeAQI", SensorDeviceClass.AQI, None)
            )
        
        # 空调传感器
        elif model in AC_MODELS and online:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 当前温度", device, "temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 设定温度", device, "roomSettemp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS)
            )
        
        # 新风机
        elif model == FA_MODEL and online:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 湿度", device, "humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE)
            )
            filters_hours = None
            for attr in dev_attrs:
                if attr.get("name") == "newWindFilterelementServicehours":
                    filters_hours = attr.get("value")
            if filters_hours is not None:
                sensors.append(
                    HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 滤芯使用小时", device, "newWindFilterelementServicehours", None, "hours")
                )
        
        # 燃气报警器
        elif model == GA_MODEL and online:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 气体状态", device, "sensor_gas_state", None, None)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_identifier, device_uid, f"{name} 气体浓度", device, "sensor_gas_concentration", None, "ppm")
            )
    
    async_add_entities(sensors)


class HabitatSensor(SensorEntity):
    """Representation of a Habitat sensor."""

    def __init__(
        self,
        api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_identifier: str,
        device_uid: str,
        name: str,
        device_data: dict,
        attr_name: str,
        device_class: str,
        unit: str,
    ):
        """Initialize the sensor."""
        self._api = api
        self._coordinator = coordinator
        self._gateway_identifier = gateway_identifier
        self._device_uid = device_uid
        self._name = name
        self._device_data = device_data
        self._attr_name = attr_name
        self._device_class = device_class
        self._unit = unit
        self._state = None
        
        self._update_state()

    def _update_state(self):
        """Update state from device data."""
        dev_attrs = self._device_data.get("dev_attrs", [])
        for attr in dev_attrs:
            if attr.get("name") == self._attr_name:
                value = attr.get("value")
                if value not in (None, ""):
                    try:
                        # Temperature and roomSettemp: 0.1°C (e.g. 232 -> 23.2)
                        if self._device_class == SensorDeviceClass.TEMPERATURE:
                            value = int(value) / 10
                        # Humidity: 0.1% (e.g. 430 -> 43.0)
                        elif self._device_class == SensorDeviceClass.HUMIDITY:
                            value = int(value) / 10
                    except (TypeError, ValueError):
                        pass
                self._state = value
                break

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"habitat_sensor_{self._device_uid}_{self._attr_name}"

    @property
    def name(self) -> str:
        """Return name."""
        return self._name

    @property
    def native_value(self):
        """Return state."""
        return self._state

    @property
    def device_class(self):
        """Return device class (may be None for AQI/gas state)."""
        return self._device_class

    @property
    def native_unit_of_measurement(self):
        """Return unit (may be None)."""
        return self._unit

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_uid)},
            name=self._name.split(" ")[0],
            manufacturer="栖息地",
            model="传感器",
            via_device=(DOMAIN, self._gateway_identifier),
        )

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
