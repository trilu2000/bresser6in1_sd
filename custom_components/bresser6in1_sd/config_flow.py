import logging
import os
import serial
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode
from .const import DOMAIN, CONF_PORT, SIGNALDUINO_FIRMWARE
from . import _ser_instance, save_sensors_data


_LOGGER = logging.getLogger(__name__)


class Bresser6in1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Bresser6in1 SIGNALduino using /dev/serial/by-id/."""

    VERSION = 2  # Version 2: Options für Sensor IDs hinzugefügt

    def __init__(self):
        self._selected_port = None

    async def async_step_user(self, user_input=None):
        """Initial step: Port auswählen."""
        if user_input is None:
            # Liste der Ports ermitteln
            all_ports = await self.hass.async_add_executor_job(self.list_by_id)
            candidate_ports = {}

            for port in all_ports:
                if not os.path.exists(port):
                    continue
                # Firmware prüfen
                is_valid = await self.hass.async_add_executor_job(
                    self.validate_firmware, port
                )
                if is_valid:
                    display = port
                    if _ser_instance is not None and _ser_instance.port == port:
                        display += " (in use)"
                    candidate_ports[display] = port

            if not candidate_ports:
                return self.async_abort(reason="no_signalduino_found")

            schema = vol.Schema({vol.Required(CONF_PORT): vol.In(candidate_ports)})
            return self.async_show_form(step_id="user", data_schema=schema)

        # User hat einen Port ausgewählt
        self._selected_port = user_input[CONF_PORT]
        is_valid = await self.hass.async_add_executor_job(
            self.validate_firmware, self._selected_port
        )

        if is_valid:
            # Standardmäßig "auto" als Sensor-ID
            return self.async_create_entry(
                title=f"Bresser6in1 SIGNALduino ({self._selected_port})",
                data={CONF_PORT: self._selected_port},
                options={"sensor_ids": ["auto"]},
            )

        return self.async_abort(
            reason=f"{self._selected_port} is not a SIGNALDuino or has wrong firmware"
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Option flow für Sensor IDs."""
        return Bresser6in1OptionsFlowHandler(config_entry)

    async def async_migrate_entry(self, hass, entry):
        """Migriere alte Config-Einträge auf Version 2 (Sensor-IDs)."""
        _LOGGER.debug(
            "Migrating Bresser6in1 entry %s to version %s", entry.title, self.VERSION
        )
        if entry.version < 2:
            options = dict(entry.options)
            options.setdefault("sensor_ids", ["auto"])
            entry.version = 2
            hass.config_entries.async_update_entry(entry, options=options)
        return True

    def list_by_id(self):
        """Liste alle Geräte unter /dev/serial/by-id/."""
        try:
            return [
                os.path.join("/dev/serial/by-id", p)
                for p in os.listdir("/dev/serial/by-id")
            ]
        except FileNotFoundError:
            return []

    def validate_firmware(self, port):
        """Öffnet den Port kurz zum Firmware-Check und schließt danach."""
        try:
            with serial.Serial(port, 115200, timeout=2) as ser:
                ser.write(b"V\n")
                line = ser.readline().decode(errors="ignore").strip()
                if SIGNALDUINO_FIRMWARE in line:
                    return True
        except Exception:
            return False
        return False


class Bresser6in1OptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow Handler für die Auswahl der Sensoren."""

    def __init__(self, config_entry):
        """Speichere ConfigEntry intern, ohne die Property zu überschreiben."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Step zur Auswahl der Sensoren."""
        
        entry = self._config_entry

        # gespeicherte Sensoren laden
        stored_sensors = entry.options.get("sensors_data", [])
        sensors_data = [{"id": s["id"], "active": s.get("active", False)} for s in stored_sensors]
        _LOGGER.debug("Loaded sensors_data from entry: %s", sensors_data)


        # Liste aller Sensor IDs
        sensor_ids = [s["id"] for s in sensors_data]

        # Default = aktive Sensoren
        selected_default = [s["id"] for s in sensors_data if s["active"]]


        # Wenn Benutzer Auswahl getroffen hat → speichern
        if user_input is not None:
            selected_ids = user_input.get("selected_sensors", [])

            new_sensors_data = []
            for sid in sensor_ids:
                new_sensors_data.append({
                    "id": sid,
                    "active": sid in selected_ids
                })

            # Zentrale Speicherung und Sync
            coordinator = self.hass.data[DOMAIN][self._config_entry.entry_id]

            # Entities sofort synchronisieren
            await save_sensors_data(
                self.hass,
                self._config_entry,
                new_sensors_data,
                coordinator
            )

            # Optionen korrekt speichern!
            return self.async_create_entry(
                title="",
                data={
                    "sensors_data": new_sensors_data
                },
            )
            
            
            #await save_sensors_data(self.hass, self._config_entry, new_sensors_data, coordinator)

            #_LOGGER.debug("Saving sensors_data: %s", new_sensors_data)
            #return self.async_create_entry(title="", data={})
            
            #return self.async_create_entry(
            #    title="",
            #    data={},
            #    options={
            #        "sensors_data": new_sensors_data
            #    },
            #)


        # Multi-Select anzeigen
        schema = vol.Schema({
            vol.Optional(
                "selected_sensors",
                default=selected_default
            ): SelectSelector(
                SelectSelectorConfig(
                    options=sensor_ids,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )