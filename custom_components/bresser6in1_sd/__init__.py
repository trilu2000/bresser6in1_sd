import asyncio
import serial
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, CONF_PORT, INIT_STRING
from .sensor import BresserSensor
from .binary_sensor import BresserBatteryLowSensor, BresserBatteryChangeSensor
from .coordinator import BresserCoordinator


_LOGGER = logging.getLogger(__name__)

# Singleton für die serielle Schnittstelle
_ser_instance = None
_ser_lock = asyncio.Lock()
_read_task = None

# Globale Sensor-Daten
sensors_data = []  # {"id": str, "active": bool}



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Setup des SignalDuino nach der Konfiguration."""
    global _ser_instance, _read_task, sensors_data

    port = entry.data[CONF_PORT]

    # gespeicherte Sensoren laden
    stored_sensors = entry.options.get("sensors_data", [])
    sensors_data = [{"id": s["id"], "active": s.get("active", False)} for s in stored_sensors]
    _LOGGER.debug("Loaded sensors_data from entry: %s", sensors_data)


    # Coordinator erstellen
    coordinator = BresserCoordinator(hass, entry)

    # Coordinator speichern (wichtig für sensor.py)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator


    async with _ser_lock:
        if _ser_instance is not None:
            _LOGGER.debug("SIGNALduino already initialized, reusing existing port")
            return True

        try:
            _ser_instance = serial.Serial(port, 115200, timeout=0.2)
            _ser_instance.write(b"E\n")
            _LOGGER.debug("Sent 'E' to SIGNALduino on %s", port)
            _ser_instance.write((INIT_STRING + "\n").encode())
            _LOGGER.debug("Sent initialization string to SIGNALduino on %s", port)
        except Exception as e:
            _LOGGER.error("Could not open SIGNALduino on %s: %s", port, e)
            _ser_instance = None
            return False

    # Read loop starten und coordinator übergeben
    _read_task = hass.async_create_background_task(
        _read_loop(_ser_instance, hass, entry, coordinator),
        "bresser6in1_signald_read_loop",
    )

    entry.runtime_data = {
        "read_task": _read_task,
        "coordinator": coordinator,
    }

    # Sensor-Plattform laden
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor"])

    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Cleanup when integration is removed or reloaded."""
    global _ser_instance, _read_task, sensors_data

    async with _ser_lock:


        # serial read abbrechen 
        if _ser_instance is not None:
            try:
                await hass.async_add_executor_job(_ser_instance.cancel_read)
            except Exception:
                pass

        # Read loop stoppen
        if _read_task is not None:
            _LOGGER.debug("Stopping SIGNALduino read loop")
            _read_task.cancel()
            try:
                await _read_task
            except asyncio.CancelledError:
                pass
            _read_task = None


        # Seriellen Port schließen
        if _ser_instance is not None:
            try:
                port = _ser_instance.port
                _ser_instance.close()
                _LOGGER.debug("Closed SIGNALduino port %s", port)
            except Exception as e:
                _LOGGER.error("Error closing SIGNALduino port: %s", e)
            finally:
                _ser_instance = None


        # Letztes Speichern der Sensor-Daten
        if sensors_data:
            _LOGGER.debug("Saving sensors_data on unload: %s", sensors_data)
            hass.config_entries.async_update_entry(entry, options={"sensors_data": sensors_data})

    return True


async def _read_loop(ser, hass: HomeAssistant, entry, coordinator):
    """Asynchron eingehende Nachrichten vom SignalDuino loggen, prüfen und Sensor-IDs speichern."""
    global sensors_data
    
    loop = asyncio.get_running_loop()

    try:
        while True:

            try:
                line = await loop.run_in_executor(None, ser.readline)
            except serial.SerialException:
                break

            if not line:
                await asyncio.sleep(0.01)
                continue

            # Daten holen und bereinigen
            msg = line.decode(errors="ignore").strip()
            msg = msg.lstrip("\x02").rstrip("\x03")

            if not msg.startswith("MN;D="):
                _LOGGER.debug("received %s - MN;D= missing", msg)
                continue

            # Hex-Daten extrahieren und prüfen
            hex_data = msg.split(";")[1].replace("D=", "")
            status = _check_message(hex_data)

            if status != "OK":
                _LOGGER.debug("received %s - %s", msg, status)
                continue

            # RSSI extrahieren
            rssi = None
            parts = msg.split(";")
            for part in parts:
                if part.startswith("R="):
                    try:
                        rssi = int(part.replace("R=", ""))
                        rssi = rssi - 256
                    except:
                        pass


            # station_id aus hex payload
            sensor_id = hex_data[4:12]  # die 8 Nibbles, passt je nach Dokumentation

            # Aktuelle sensors_data aus entry.options lesen
            sensors_data = entry.options.get("sensors_data", [])

            # Prüfen, ob Sensor schon in sensors_data existiert
            sensor_entry = next((s for s in sensors_data if s["id"] == sensor_id), None)

                        # --------------------------------------------------
            # NEUE SENSOR-ID ENTDECKT
            # --------------------------------------------------
            if sensor_entry is None:

                sensor_active = len(sensors_data) == 0

                sensors_data.append({
                    "id": sensor_id,
                    "active": sensor_active
                })

                await hass.config_entries.async_update_entry(
                    entry,
                    options={"sensors_data": sensors_data},
                )

                _LOGGER.info("New Bresser6in1 sensor discovered: %s", sensor_id)

                # Integration neu laden → Entities werden erzeugt
                await hass.config_entries.async_reload(entry.entry_id)

                continue
                
            #if sensor_entry is None:

                # Erste Sensor-ID automatisch auswählen, falls noch keine gesetzt
            #    sensor_active = False
            #    if len(sensors_data) == 0:
            #        sensor_active = True
            
            #    sensors_data.append({"id": sensor_id, "active": sensor_active})

                # Zentrale Speicherung und Sync
            #    await save_sensors_data(hass, entry, sensors_data, coordinator)
            #    sensor_entry = next((s for s in sensors_data if s["id"] == sensor_id), None)

            # Nur ausgewählten Sensor verarbeiten
            #if not (sensor_entry and sensor_entry["active"]):
            #    _LOGGER.debug("received %s - not active", msg)
            #    continue
            #else:
            #    _LOGGER.debug("received %s - to process", msg)

            try:
                parsed = parse_bresser6in1(hex_data)
                if rssi is not None:
                    parsed["rssi"] = rssi
                _LOGGER.debug("%s", parsed)
                
                if coordinator:
                    coordinator.update_from_parser(sensor_id, parsed)
                else:
                    _LOGGER.error("Coordinator is None, cannot update")
                
                #coordinator.update_from_parser(sensor_id, parsed)
                
            except ValueError:
                continue            

            await asyncio.sleep(0.01)

    except asyncio.CancelledError:
        _LOGGER.debug("SIGNALduino read loop cancelled")
    except Exception as e:
        _LOGGER.error("Error reading from SIGNALduino: %s", e)


def check_crc16(hex_data: str) -> int:
    """CRC16-CCITT Berechnung für Bresser 6in1."""
    data_bytes = bytes.fromhex(hex_data[4:34])
    crc = 0x0000
    for b in data_bytes:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _check_message(hex_data: str) -> str:
    """Prüft Länge, Checksumme und CRC der Nachricht."""
    nibbles = len(hex_data)
    if nibbles not in (36, 40):
        return "MISMATCH LEN"

    data_bytes = [int(hex_data[i:i+2], 16) for i in range(0, nibbles, 2)]
    if len(data_bytes) < 18:
        return "MISMATCH LEN"

    checksum_calc = sum(data_bytes[2:18]) & 0xFF
    if checksum_calc != 0xFF:
        return f"MISMATCH CHKSUM (calc 0x{checksum_calc:02X}, not 0xFF)"

    recv_crc = int(hex_data[:4], 16)
    calc_crc = check_crc16(hex_data)

    if calc_crc == recv_crc:
        return "OK"

    return f"MISMATCH CRC (calc 0x{calc_crc:04X}, msg 0x{recv_crc:04X})"


def hex_bcd_invert(hex_str: str) -> int:
    """Invertiere BCD-codierte Nibbles und konvertiere zu int."""
    inverted = hex_str.translate(str.maketrans("0123456789ABCDEF","FEDCBA9876543210"))
    return int(inverted)

def parse_bresser6in1(hex_str: str) -> dict:
    """Parse einen SIGNALduino-Hexstring der Bresser 6-in-1 Sensoren."""
    result = {}

    MODEL_MAP = {
        1: 'weathe sensor',
        2: 'indoor sensor',
        3: 'pool thermometer',
        4: 'soil probe',
    }

#   012345678901234567890123456789012345
#   CCCCIIIIIIIIFFGGGWWWDDD?TTTFHHVVVXSS0000  message type 0, 40 Nibble
#   CCCCIIIIIIIIFFGGGWWWDDD?TTTFHHVVVXSS      message type 0, 36 Nibble 
#   CCCCIIIIIIIIFFGGGWWWDDD?RRRRRR???XSS      message type 1, 36 Nibble
#   
#   C = CRC16
#   I = station ID
#   F = 8 bit, flags (nibble 12 1: weather station, 2: indoor, 3: pool thermometer, 4: soil probe, nibble 13 1 bit battery change, 3 bit channel)
#   G = wind gust in 1/10 m/s, inverted, BCD coded, GGG = FE6 =~ 019 => 1.9 m/s.
#   W = wind speed in 1/10 m/s, inverted, BCD coded, LSB first nibble, MSB last two nibble, WWW = EFE =~ 101 => 1.1 m/s.
#   D = wind direction in grad, BCD coded, DDD = 158 => 158 °
#   ? = unknown, 0x0, 0x8 or 0xE
#   T = temperature in 1/10 °C, TTT = 312 => 31.2 °C
#   F = flags, 4 bit - bit 3 temperature (0=positive, 1=negative), bit 2 ?, bit 1 battery (1=ok, 0=low), bit 0 ?
#   H = humidity in percent, BCD coded, HH = 23 => 23 %
#   R = rain counter, inverted, BCD coded
#   V = uv,  inverted, BCD coded
#   X = message type, 0 = temp, hum, wind, uv, 1 = wind, rain
#   S = checksum (sum over byte 2 - 17 must be 255)

    # 40 Nibble → 36 Nibble kürzen, da nur 0000 angehängt
    #if len(hex_str) == 40 and hex_str[-4:] == "0000":
    #    hex_str = hex_str[:36]
#    _LOGGER.debug("message type: %s", result["message_type"])


    # X = message type, 0 = temp, hum, wind, uv, 1 = wind, rain
    result["message_type"] = int(hex_str[33], 16)


    # C = CRC16
    #_LOGGER.debug("CRC16           0: 3: %s", hex_str[0:4])

    # I = station ID
    result["station_id"] = hex_str[4:12]
    #_LOGGER.debug("Staion_id       4:12: %s", hex_str[4:12])

    # F = 8 bit, flags (nibble 12 1: weather station, 2: indoor, 3: pool thermometer, 4: soil probe, nibble 13 1 bit battery change, 3 bit channel)
    model_id = int(hex_str[12],16)
    result["model_stat"] = MODEL_MAP.get(model_id, 'SD_WS_115')
    
    nib13 = int(hex_str[13],16)
    result["channel"] = (nib13 >> 1) & 0b111
    result["batChange"] = True if (nib13 & 1) else False

    #_LOGGER.debug("Flag_1         12:14: %s, channel: %s, batChange: %s", hex_str[12:14], result["channel"], result["batChange"])


    # only weather station provides weather data
    if model_id != 1:
        return result


    # G = wind gust in 1/10 m/s, inverted, BCD coded, GGG = FE6 =~ 019 => 1.9 m/s.
    result["wind_gust"] = hex_bcd_invert(hex_str[14:17]) * 0.1
    #_LOGGER.debug("Wind_guest     14:17: %s, %s", hex_str[14:17], result["wind_gust"])

    # W = wind speed in 1/10 m/s, inverted, BCD coded, LSB first nibble, MSB last two nibble, WWW = EFE =~ 101 => 1.1 m/s.
    windspeed_bcd = hex_str[18:19] + hex_str[17]
    result["wind_speed"] = hex_bcd_invert(windspeed_bcd) * 0.1
    #_LOGGER.debug("Wind_speed     17:20: %s, %s", hex_str[17:20], result["wind_speed"])

    # D = wind direction in grad, BCD coded, DDD = 158 => 158 °
    result["wind_dir"] = int(hex_str[20:23])
    #_LOGGER.debug("Wind_direction 20:23: %s, %s", hex_str[20:23], result["wind_dir"])


    if result["message_type"] == 0:
        # T = temperature in 1/10 °C, TTT = 312 => 31.2 °C, F = flags, 4 bit - bit 3 temperature (0=positive, 1=negative)
        temp_bcd = int(hex_str[24:27]) * 0.1
        temp_flag = (int(hex_str[27], 16) >> 3) & 0x1
        if temp_flag:  # negative
            result["temperature"] = -(100 - temp_bcd)
        else:
            result["temperature"] = temp_bcd
        #_LOGGER.debug("Temperature    24:27: %s, temp_bcd: %s, temp_flag: %s, temp: %s", hex_str[24:27], temp_bcd, temp_flag, result["temperature"])

        # F = flags, 4 bit - bit 3 temperature (0=positive, 1=negative), bit 2 ?, bit 1 battery (1=ok, 0=low), bit 0 ?
        flag_nibble = hex_str[27]
        temp_flag = (int(flag_nibble, 16) >> 3) & 0x1
        battery_bit = (int(flag_nibble, 16) >> 1) & 0x1
        result["battery"] = "ok" if battery_bit else "low"
        #_LOGGER.debug("Flag_2         27:    %s, bin: %s, temp_flag: %s, battery: %s", hex_str[27], bin(int(hex_str[27], 16))[2:].zfill(4), temp_flag, battery_bit)

        # H = humidity in percent, BCD coded, HH = 23 => 23 %
        result["humidity"] = int(hex_str[28:30])
        #_LOGGER.debug("Humidity       28:30: %s, %s", hex_str[28:30], result["humidity"])

        # V = uv,  inverted, BCD coded
        result["uv"] = hex_bcd_invert(hex_str[30:33]) * 0.1
        #_LOGGER.debug("UV             30:33: %s, inv: %s, %s", hex_str[30:33], hex_bcd_invert(hex_str[30:33]), result["uv"])

        result["rain"] = None

    elif result["message_type"] == 1:
        result["temperature"] = None
        result["battery"] = None
        result["humidity"] = None
        result["uv"] = None

        # R = rain counter, inverted, BCD coded
        result["rain"] = hex_bcd_invert(hex_str[24:30]) * 0.1
        #_LOGGER.debug("Rain_counter   24:30: %s, inv: %s, %s", hex_str[24:30], hex_bcd_invert(hex_str[24:30]), result["rain"])

    else:
        raise ValueError(f"Unknown message type: {result['message_type']}")

    return result

async def save_sensors_data(hass, entry, new_data, coordinator):
    global sensors_data
    sensors_data = new_data

    # nur Coordinator refresh triggern
    coordinator.async_set_updated_data(coordinator.latest_data.copy())
    
    
#async def save_sensors_data(hass, entry, new_data, coordinator):
#
#    global sensors_data
#    sensors_data = new_data
#
    #hass.config_entries.async_update_entry(
    #    entry,
    #    options={"sensors_data": sensors_data},
    #)

#    if coordinator.async_add_entities is None:
#        return

#    for idx, s in enumerate(sensors_data, start=1):

#        sid = s["id"]
#        active = s["active"]

        # --- Alle vorhandenen Entities der Station entfernen ---
        #remove_keys = [uid for uid in coordinator.entities if uid.startswith(sid)]
        #for uid in remove_keys:
        #    entity = coordinator.entities.pop(uid)
        #    await entity.async_remove()
        #    _LOGGER.debug("Entity removed %s", uid)

        


#        entity_exists = any(sid in uid for uid in coordinator.entities)

#        if active:

#            new_entities = []

            # normale Sensoren
#            for sensor_type in [
#                "temperature",
#                "humidity",
#                "wind_speed",
#                "wind_gust",
#                "wind_dir",
#                "rain",
#                "rain_rate",  
#                "uv",
#                "rssi",
#            ]:

#                entity = BresserSensor(coordinator, sid, idx, sensor_type)
#                coordinator.entities[entity.unique_id] = entity
#                new_entities.append(entity)

            # Binary Sensoren hinzufügen
#            binary_low = BresserBatteryLowSensor(coordinator, sid, idx)
#            binary_change = BresserBatteryChangeSensor(coordinator, sid, idx)

#            for entity in [binary_low, binary_change]:
#                coordinator.entities[entity.unique_id] = entity
#                new_entities.append(entity)


#            coordinator.async_add_entities(new_entities)
#            _LOGGER.debug("Entities created for %s", sid)

