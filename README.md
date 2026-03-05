# Bresser 6-in-1 SIGNALduino / CUL v3 Integration

Custom Home Assistant integration for reading **Bresser 6-in-1 Weather Station** sensors via a **SIGNALduino** (tested with a CUL v3) receiver.

---

## Features

- Automatic detection of Bresser sensors  
- Supports multiple sensors per receiver  
- Real-time updates of temperature, humidity, wind, rain, UV and signal strength  
- Battery low and battery changed notifications (binary sensors)  
- Rain rate smoothing over 15 minutes  
- Full ConfigFlow and OptionsFlow for sensor activation  

---

## Supported Hardware

### Weather Sensor

- Bresser **6-in-1 (or new 5-in-1) Weather Sensor**  
  Provides:
  - Temperature  
  - Humidity  
  - Wind speed & gust  
  - Wind direction  
  - Rain total & rain rate  
  - UV index  

### Receiver Options

This integration supports:

1. **SIGNALduino** (with v3.35 dev firmware)  
2. tested with a **CUL v3** with following firmware:

```
SIGNALduino_culV3CC1101_onlyFsk_335dev20220521.hex
```

> Flash your CUL using the [Busware CUL Flasher](https://prov.busware.de/culflasher/).

### Testing your Receiver

After connecting your SIGNALduino or CUL v3, check that Home Assistant can see it:

```bash
ls /dev/serial/by-id/
```

Expected output for a CUL v3 might look like:

```
usb-SparkFun_SparkFun_Pro_Micro-if00
```

Ensure the device exists before configuring the integration.

---

## Installation

### HACS

1. Add this repository as a **Custom Repository** in HACS:
   - Category: **Integration**  
2. Install `Bresser6in1_SD`  
3. Restart Home Assistant

### Manual

1. Copy the `custom_components/bresser6in1_sd` folder into your `config/custom_components/` directory  
2. Restart Home Assistant  

---

## Configuration

### Config Flow

1. Add the integration via **Settings → Devices & Services → Add Integration → Bresser6in1 SIGNALduino**  
2. Select your device from the list of available serial ports  
3. Home Assistant validates the firmware and sets up the receiver  
4. Optionally configure **sensor activation** in the OptionsFlow  

### Options Flow

- Allows activating/deactivating individual sensors  
- Changes are applied immediately, without restarting Home Assistant  
- Binary sensors (Battery Low / Battery Changed) are always created

---

## Sensors

### Normal Sensors

| Type         | Unit | Notes |
|--------------|------|-------|
| temperature  | °C   | Temperature reading |
| humidity     | %    | Relative humidity |
| wind_speed   | m/s  | Average wind speed |
| wind_gust    | m/s  | Wind gusts |
| wind_dir     | °    | Wind direction |
| rain         | mm   | Total rain (increasing) |
| rain_rate    | mm/h | Smoothed over 15 minutes |
| uv           | UV index | UV radiation |
| rssi         | dBm  | Signal strength (diagnostic) |

### Binary Sensors

| Type            | Description |
|-----------------|------------|
| battery_low     | True = battery low |
| battery_changed | True = battery was replaced |

---

## Logging

Enable debug logging for troubleshooting:

```yaml
logger:
  default: info
  logs:
    custom_components.bresser6in1_sd: debug
```

---

## Rain Rate Calculation

- Rain rate is computed over the last 15 minutes  
- Smoothed to avoid spikes  
- Updated whenever a new rain reading is received  

---


## Notes

- Integration supports multiple Bresser 6-in-1 sensors per receiver  
- Sensor activation can be changed anytime via **OptionsFlow**  
- Ensure serial permissions are set correctly (`/dev/serial/by-id/*`)  

---



