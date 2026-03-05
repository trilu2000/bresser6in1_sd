import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class BresserBatteryLowSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary Sensor für Batterie-Status LOW"""

    def __init__(self, coordinator, station_id, index):
        super().__init__(coordinator)
        self.station_id = station_id

        self._attr_unique_id = f"{station_id}_battery_low"
        self._attr_name = f"Bresser6in1 {index} Battery Low"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        """True = Battery LOW"""
        station = self.coordinator.data.get(self.station_id)
        if not station:
            return None
        battery = station.get("battery")
        if battery is None:
            return None
        return battery == "low"

    @property
    def available(self):
        entry = self.coordinator.entry
        sensors_data = entry.options.get("sensors_data", [])

        active_ids = [s["id"] for s in sensors_data if s["active"]]

        return (
            self.station_id in active_ids
            and super().available
        )

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.station_id)},
            name=f"Bresser6in1 Sensor {self.station_id}",
            manufacturer="Bresser",
            model="6-in-1",
        )


class BresserBatteryChangeSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary Sensor für Batterie-Wechsel (batChange)"""

    def __init__(self, coordinator, station_id, index):
        super().__init__(coordinator)
        self.station_id = station_id

        self._attr_unique_id = f"{station_id}_battery_changed"
        self._attr_name = f"Bresser6in1 {index} Battery Changed"
        self._attr_device_class = BinarySensorDeviceClass.BATTERY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self):
        """True = Battery changed"""
        station = self.coordinator.data.get(self.station_id)
        if not station:
            return None
        return bool(station.get("batChange"))

    @property
    def available(self):
        entry = self.coordinator.entry
        sensors_data = entry.options.get("sensors_data", [])

        active_ids = [s["id"] for s in sensors_data if s["active"]]

        return (
            self.station_id in active_ids
            and super().available
        )

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.station_id)},
            name=f"Bresser6in1 Sensor {self.station_id}",
            manufacturer="Bresser",
            model="6-in-1",
        )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up binary sensors für Batterie"""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors_data = entry.options.get("sensors_data", [])
    all_sensors = sensors_data
    active = [s for s in sensors_data if s["active"]]
    entities = []

    for idx, station in enumerate(active, start=1):
        sid = station["id"]

        # beide Binary Sensoren hinzufügen
        entities.append(BresserBatteryLowSensor(coordinator, sid, idx))
        entities.append(BresserBatteryChangeSensor(coordinator, sid, idx))

        # in coordinator registrieren
        for entity in entities[-2:]:
            coordinator.entities[entity.unique_id] = entity

    async_add_entities(entities)