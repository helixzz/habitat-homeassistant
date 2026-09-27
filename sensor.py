"""Sensor platform for 栖息地智能家庭."""

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HabitatAPI
from .const import DOMAIN, SENSOR_MODELS, AC_MODELS, FA_MODEL, GA_MODEL
from .helpers import HabitatAvailabilityMixin, is_main_panel

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    apis_by_uid = data.get("apis_by_uid") or {}
    primary_uid = data.get("primary_uid", "")
    default_api: HabitatAPI = data["api"]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    gateway_device_id: str = data["gateway_device_id"]
    devices = coordinator.data or []

    sensors = []
    for device in devices:
        model = device.get("model", "")
        device_uid = device.get("deviceUid", "")
        online = device.get("online", False)
        child_uid = device.get("childGatewayId") or primary_uid
        api = apis_by_uid.get(child_uid) if apis_by_uid else default_api
        api = api or apis_by_uid.get(primary_uid) or default_api
        dev_attrs = device.get("dev_attrs", [])
        
        # Get device name
        name = device_uid
        for attr in dev_attrs:
            if attr.get("name") == "devName":
                name = attr.get("value", device_uid)
                break
        
        # 五合一传感器：实体名仅保留类型（温度、湿度等），设备名单独传入 device_info
        if model in SENSOR_MODELS:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "温度", device, "temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "湿度", device, "humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "PM2.5", device, "PM2_5U", SensorDeviceClass.PM25, "μg/m³")
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "PM10", device, "PM10U", SensorDeviceClass.PM10, "μg/m³")
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "CO2", device, "CO2M", SensorDeviceClass.CO2, "ppm")
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "AQI", device, "homeAQI", SensorDeviceClass.AQI, None)
            )
            # 主面板：地暖状态只读；滤芯/加湿器使用小时（若有）
            if is_main_panel(dev_attrs):
                sensors.append(
                    HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "地暖状态", device, "homeFloorheatState", None, None)
                )
                for attr_name, label in (
                    ("newWindFilterelementServicehours", "滤芯使用小时"),
                    ("newWindHumidifierServicehours", "加湿器使用小时"),
                ):
                    if any(a.get("name") == attr_name for a in dev_attrs):
                        sensors.append(
                            HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, label, device, attr_name, None, "hours")
                        )
        
        # 空调传感器
        elif model in AC_MODELS:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "当前温度", device, "temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "设定温度", device, "roomSettemp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS)
            )
        
        # 新风机
        elif model == FA_MODEL:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "湿度", device, "humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE)
            )
            filters_hours = None
            for attr in dev_attrs:
                if attr.get("name") == "newWindFilterelementServicehours":
                    filters_hours = attr.get("value")
            if filters_hours is not None:
                sensors.append(
                    HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "滤芯使用小时", device, "newWindFilterelementServicehours", None, "hours")
                )
        
        # 燃气报警器
        elif model == GA_MODEL:
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "气体状态", device, "sensor_gas_state", None, None)
            )
            sensors.append(
                HabitatSensor(api, coordinator, gateway_device_id, device_uid, name, "气体浓度", device, "sensor_gas_concentration", None, "ppm")
            )
    
    async_add_entities(sensors)


class HabitatSensor(HabitatAvailabilityMixin, SensorEntity):
    """Representation of a Habitat sensor."""

    def __init__(
        self,
        api: HabitatAPI,
        coordinator: DataUpdateCoordinator,
        gateway_device_id: str,
        device_uid: str,
        device_name: str,
        name: str,
        device_data: dict,
        attr_name: str,
        device_class: str,
        unit: str,
    ):
        """Initialize the sensor. device_name 为设备显示名（如 书房面板），name 为实体名（如 温度、湿度）。"""
        self._api = api
        self._coordinator = coordinator
        self._gateway_device_id = gateway_device_id
        self._device_uid = device_uid
        self._device_name = device_name
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
            name=self._device_name,
            manufacturer="栖息地",
            model="传感器",
            via_device_id=self._gateway_device_id,
        )

    async def async_update(self) -> None:
        """Update the entity from coordinator data."""
        for device in self._coordinator.data or []:
            if device.get("deviceUid") == self._device_uid:
                self._device_data = device
                self._update_state()
                break
