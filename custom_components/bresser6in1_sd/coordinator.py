import logging
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from datetime import timedelta, datetime

from .const import DOMAIN


_LOGGER = logging.getLogger(__name__)


class BresserCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry):
        super().__init__(
            hass,
            logger=_LOGGER,   # FIX
            name=DOMAIN,
            update_interval=None,
        )

        self.entry = entry
        self.latest_data = {}

        self.entities = {}  # key = station_id_sensor_type, value = BresserSensor
        self.async_add_entities = None  
        self._rain_history = {}  
        
        # initialisieren, damit data nie None ist
        self.async_set_updated_data(self.latest_data)


    def update_from_parser(self, station_id, parsed_data):
        """Nur update wenn sich Werte ändern"""
        old = self.latest_data.get(station_id, {})
        merged = old.copy()
        changed = False

        # normale Werte aktualisieren
        for key, value in parsed_data.items():
            if value is None:
                continue
            if merged.get(key) != value:
                merged[key] = value
                changed = True

        # ---- Regenrate über 15 Minuten glätten ----
        if "rain" in parsed_data and parsed_data["rain"] is not None:
            now = datetime.utcnow()
            history = self._rain_history.get(station_id, [])

            # neuen Messpunkt anhängen
            history.append((parsed_data["rain"], now))

            # nur Einträge innerhalb der letzten 15 Minuten behalten
            fifteen_min_ago = now - timedelta(minutes=15)
            history = [(r, t) for r, t in history if t >= fifteen_min_ago]

            self._rain_history[station_id] = history

            # berechne Regenrate aus ältestem und neuestem Wert
            if len(history) >= 2:
                rain_delta = history[-1][0] - history[0][0]
                time_delta = (history[-1][1] - history[0][1]).total_seconds()
                rain_rate = (rain_delta / time_delta * 3600.0) if time_delta > 0 else 0.0
            else:
                rain_rate = 0.0

            merged["rain_rate"] = round(rain_rate, 2)
            changed = True

        if not changed:
            return

        self.latest_data[station_id] = merged
        self.async_set_updated_data(self.latest_data.copy())



