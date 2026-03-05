import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.components.sensor import (SensorEntity, SensorDeviceClass, SensorStateClass)
from homeassistant.const import (UnitOfTemperature, UnitOfSpeed, UnitOfLength, PERCENTAGE)

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)


class BresserSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator, station_id, index, sensor_type):
        super().__init__(coordinator)

        self.station_id = station_id
        self.index = index
        self.sensor_type = sensor_type

        self._attr_unique_id = f"{station_id}_{sensor_type}"
        self._attr_name = f"Bresser6in1 {index} {sensor_type}"

        # Default
        self._attr_state_class = SensorStateClass.MEASUREMENT

        # spezifische Konfiguration
        if sensor_type == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

        elif sensor_type == "humidity":
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = "%"

        elif sensor_type == "wind_speed":
            self._attr_device_class = SensorDeviceClass.WIND_SPEED
            self._attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND

        elif sensor_type == "wind_gust":
            self._attr_device_class = SensorDeviceClass.WIND_SPEED
            self._attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND

        elif sensor_type == "wind_dir":
            self._attr_native_unit_of_measurement = "°"
            self._attr_icon = "mdi:compass"

        elif sensor_type == "rain":
            self._attr_device_class = SensorDeviceClass.PRECIPITATION
            self._attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        elif sensor_type == "rain_rate":
            self._attr_device_class = SensorDeviceClass.PRECIPITATION_INTENSITY
            self._attr_native_unit_of_measurement = "mm/h"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:weather-rainy"

        elif sensor_type == "uv":
            self._attr_device_class = SensorDeviceClass.IRRADIANCE
            self._attr_native_unit_of_measurement = "UV index"
            self._attr_icon = "mdi:weather-sunny"
            
        elif sensor_type == "rssi":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = "dBm"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_icon = "mdi:signal"

    @property
    def available(self):
        entry = self.coordinator.entry
        sensors_data = entry.options.get("sensors_data", [])

        active_ids = [s["id"] for s in sensors_data if s["active"]]

        return (
            self.station_id in active_ids
            and self.station_id in self.coordinator.data
        )
    
    @property
    def state(self):

        station = self.coordinator.data.get(self.station_id)

        if not station:
            return None

        return station.get(self.sensor_type)
        

    @property
    def device_info(self) -> DeviceInfo:
        """Informationen für Home Assistant Geräteübersicht"""
        return DeviceInfo(
            identifiers={(DOMAIN, self.station_id)},
            name=f"Bresser6in1 Sensor {self.station_id}",
            manufacturer="Bresser",
            model="6-in-1",
        )
        
        
async def async_setup_entry(hass, entry, async_add_entities):

    coordinator = hass.data[DOMAIN][entry.entry_id]
    # async_add_entities speichern
    coordinator.async_add_entities = async_add_entities
    
    sensors_data = entry.options.get("sensors_data", [])
    all_sensors = sensors_data
    active = [s for s in sensors_data if s["active"]]
    entities = []


    for idx, station in enumerate(active, start=1):

        sid = station["id"]

        for sensor_type in [
            "temperature",
            "humidity",
            "wind_speed",
            "wind_gust",
            "wind_dir",
            "rain",
            "rain_rate",  
            "uv",
            "rssi",
        ]:

            entity = BresserSensor(coordinator, sid, idx, sensor_type)

            coordinator.entities[entity.unique_id] = entity
            entities.append(entity)

    async_add_entities(entities)
    


