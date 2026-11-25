"""Sensor platform for 栖息地智能家庭."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import HabitatAPI
from .const import (
    AC_MODELS,
    CLOUD_WATER_TYPE,
    DOMAIN,
    FA_MODEL,
    GA_MODEL,
    SENSOR_MODELS,
)
from .helpers import HabitatAvailabilityMixin, is_main_panel

_LOGGER = logging.getLogger(__name__)

# 四合一水处理器（SHX-ECL1-V1）的属性 → 传感器。
# 该设备**不在 Zigbee 网关上**，只能从厂商云端读取，且 16 个属性全部只读
# （control_cd=1，对照：可写的灯属性是 3），所以只做传感器、没有控制实体。
# 字段：属性名, 实体名, 倍率, 单位, device_class, state_class, 图标
# 倍率与单位依据设备自带的 describe 字段（例如 ins_fr「1111 表示 11.11 立方」→ ×0.01）。
WATER_SENSORS: tuple[tuple, ...] = (
    ("ro_rwq", "原水 TDS", 1, "ppm", None, SensorStateClass.MEASUREMENT, "mdi:water-percent"),
    ("ro_pwq", "纯水 TDS", 1, "ppm", None, SensorStateClass.MEASUREMENT, "mdi:water-percent"),
    ("ins_fr", "软水瞬时流量", 0.01, UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR, None, SensorStateClass.MEASUREMENT, "mdi:waves-arrow-right"),
    ("pw_ifr", "净水瞬时流量", 0.1, UnitOfVolumeFlowRate.LITERS_PER_MINUTE, None, SensorStateClass.MEASUREMENT, "mdi:water-pump"),
    ("rw_pc", "软水剩余制水量", 0.01, UnitOfVolume.CUBIC_METERS, None, SensorStateClass.MEASUREMENT, "mdi:water-minus"),
    ("total_wcs", "软水总用水量", 0.01, UnitOfVolume.CUBIC_METERS, None, SensorStateClass.TOTAL_INCREASING, "mdi:water"),
    ("wpfe_pct", "净化滤芯寿命", 1, PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:filter"),
    ("pce_pct", "后置活性炭滤芯寿命", 1, PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:filter"),
    ("rof_pct", "RO 滤芯寿命", 1, PERCENTAGE, None, SensorStateClass.MEASUREMENT, "mdi:filter"),
    ("rw_hardness", "原水硬度", 1, "mg/L", None, SensorStateClass.MEASUREMENT, "mdi:water-opacity"),
    ("running_state", "运行状态", 1, None, None, None, "mdi:state-machine"),
    ("regrn_interval", "软水再生间隔", 1, "d", None, None, "mdi:calendar-clock"),
    ("regrn_time", "软水再生时间", 1, None, None, None, "mdi:clock-outline"),
    ("notice", "告警", 1, None, None, None, "mdi:alert-circle-outline"),
)


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
    
    # --- 云端设备（Zigbee 网关上没有的）：四合一水处理器 -------------------
    cloud_coordinator = data.get("cloud_coordinator")
    if cloud_coordinator is not None:
        for cloud_device in cloud_coordinator.data or []:
            if cloud_device.get("type_code") != CLOUD_WATER_TYPE:
                continue
            for spec in WATER_SENSORS:
                sensors.append(
                    HabitatCloudWaterSensor(
                        cloud_coordinator, cloud_device, gateway_device_id, *spec
                    )
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


class HabitatCloudWaterSensor(CoordinatorEntity, SensorEntity):
    """云端设备（四合一水处理器）的传感器。

    数据来自 HabitatCloudCoordinator（厂商云端 API），不是本地网关。
    """

    def __init__(
        self,
        coordinator,
        device: dict,
        gateway_device_id: str,
        key: str,
        name: str,
        scale: float,
        unit,
        device_class,
        state_class,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._gateway_device_id = gateway_device_id
        self._device_id = device.get("device_id", "")
        self._device_number = device.get("device_number", "")
        self._device_name = device.get("name", "水处理")
        self._model_name = device.get("model_name") or device.get("model") or "水处理"
        self._room = device.get("room") or None
        self._key = key
        self._scale = scale
        self._device_class = device_class
        self._attr_name = name
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"habitat_cloud_{self._device_number}_{key}"

    def _current(self) -> dict | None:
        for dev in self.coordinator.data or []:
            if dev.get("device_id") == self._device_id:
                return dev
        return None

    @property
    def available(self) -> bool:
        device = self._current()
        return super().available and bool(device and device.get("online"))

    @property
    def native_value(self):
        device = self._current()
        if not device:
            return None
        raw = (device.get("attrs") or {}).get(self._key)
        if raw is None or raw == "":
            return None
        # 倍率 1 时尽量保持原类型（例如 "1 ; 5" 这种时刻串）
        if self._scale == 1:
            try:
                number = float(raw)
            except (TypeError, ValueError):
                return str(raw)
            return int(number) if number.is_integer() else number
        try:
            return round(float(raw) * self._scale, 2)
        except (TypeError, ValueError):
            return None

    @property
    def device_class(self):
        return self._device_class

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"cloud_{self._device_number}")},
            name=self._device_name,
            manufacturer="栖息地",
            model=self._model_name,
            suggested_area=self._room,
            via_device_id=self._gateway_device_id,
        )
