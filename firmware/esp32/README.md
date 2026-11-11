# PlantMate ESP32 DevKit

Sketch: `PlantMateESP32/PlantMateESP32.ino`

## Wiring

| Sensor | ESP32 DevKit | Notes |
|---|---|---|
| Capacitive soil sensor analog output | GPIO34 | ADC1 input-only pin |
| DHT22 data | GPIO27 | Use a 3.3 V pull-up for a bare DHT22; many breakout boards include one |
| LDR divider analog output | GPIO35 | ADC1 input-only pin; use a divider so the output never exceeds 3.3 V |
| TDS board analog output | GPIO32 | ADC1, so analog sampling remains available while Wi-Fi is active |
| All sensor grounds | ESP32 GND | Grounds must be common |

Power modules according to their own specifications. Verify each analog output voltage is no higher than 3.3 V before connecting it to the ESP32. GPIO34 and GPIO35 are input-only; this firmware uses them only as ADC inputs. The three analog inputs use ADC1, avoiding ESP32 ADC2's Wi-Fi conflict. See [Espressif's GPIO and ADC reference](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html).

## Arduino IDE on Windows

1. Install Arduino IDE 2 and the Espressif **esp32** boards package using **File → Preferences → Additional boards manager URLs** and **Tools → Board → Boards Manager**. Select **ESP32 Dev Module** (or the exact DevKit variant) and the COM port for the board.
2. In **Sketch → Include Library → Manage Libraries**, install **DHT sensor library** by Adafruit and **Adafruit Unified Sensor**.
3. In PowerShell at the repository root, copy the local settings template:

   ```powershell
   $localSecrets = 'firmware\esp32\PlantMateESP32\plantmate_secrets.h'
   if (-not (Test-Path $localSecrets)) { Copy-Item firmware\esp32\PlantMateESP32\plantmate_secrets.h.example $localSecrets }
   ```

   `plantmate_secrets.h` is Git-ignored. In this workspace its `DEVICE_INGESTION_KEY` was copied locally from root `.env` without printing it. On another checkout, copy the setting into this ignored header. Enter Wi-Fi SSID/password there too. Never paste the device key into the `.ino`, this README, the frontend, or a committed file.

4. Connect the ESP32 to USB. Open `firmware/esp32/PlantMateESP32/PlantMateESP32.ino` in Arduino IDE. Edit the copied header's `API_URL` with the laptop's Wi-Fi IPv4 address and ingestion path. Do not use `localhost` for the ESP32 URL.
5. Soil and light calibration are optional for ingestion. With calibration fields unset (zero), the sketch sends the measured soil and LDR ADC counts as raw ADC fields. Open **Tools → Serial Monitor** at **115200 baud**.
6. Calibrate using your actual sensors and update the ignored header:
   - Record `SOIL_DRY_ADC_RAW` for the probe in the dry condition you define as 0%, then `SOIL_WET_ADC_RAW` in your target wet soil condition defined as 100%. Do not submerge the capacitive board unless its manufacturer permits it.
   - Record `LIGHT_DARK_ADC_RAW` with the LDR dark, then `LIGHT_BRIGHT_ADC_RAW` while measuring that same light with a lux reference meter; enter the meter value as `LIGHT_BRIGHT_LUX`. This is a calibrated linear approximation; an LDR's response is nonlinear.
   - Confirm your analog TDS board's conversion curve. For a DFRobot Gravity SEN0244, calibrate `TDS_CALIBRATION_FACTOR` with a known TDS solution, and set `TDS_REFERENCE_TEMPERATURE_C` to the measured soil-water-extract temperature. The DHT22 measures air and is not used as liquid temperature. If your TDS board is a different model, use its documented conversion instead of assuming the SEN0244 curve. The [DFRobot reference](https://wiki.dfrobot.com/sen0244) describes its formula and solution calibration.
7. Upload again and watch the monitor. Readings are sampled and sent every **12 seconds**. “Reading accepted” means the server returned HTTP 201. A 401 points to a key mismatch; 422 means a reading failed backend validation; 503 means the backend has no ingestion key configured. Wi-Fi reconnects automatically after dropouts.

## Connect to the laptop backend over Wi-Fi

1. Put the laptop and ESP32 on the same reachable 2.4 GHz Wi-Fi network. Some guest networks block device-to-device traffic; disable AP/client isolation or use a normal private network.
2. In a backend PowerShell window, run this from `backend` so FastAPI listens on the laptop's LAN interface:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Run `ipconfig`; find the IPv4 address for the active Wi-Fi adapter. Set the header template's `API_URL` to `http://<that-ip>:8000/api/v1/ingestion/readings`, replacing the angle-bracket text with the actual address.
4. If Windows Firewall asks, allow Python on **Private networks** only. If it does not prompt and connection times out, add an inbound TCP 8000 rule limited to the Private profile. Do not expose the development server to public networks.
5. With the backend running, verify from the laptop that `http://<that-ip>:8000/health` returns `{"status":"ok"}`. Upload the sketch; the Serial Monitor should report a 201 acceptance, and the dashboard should update within one 8-second polling interval after that.

For hosted use, set `API_URL` to the HTTPS ingestion endpoint and install the provider's trusted root CA PEM in `ROOT_CA_CERT`. The firmware verifies TLS and skips HTTPS requests if the CA is absent; it never disables certificate verification. Local same-Wi-Fi HTTP is for development only.

## Measurement meaning

The request uses exactly the backend fields: `device_id`, `temperature_c`, `humidity`, `tds_ppm`, and either the calibrated pair `soil_moisture`/`light_lux` or the raw pair `soil_moisture_raw_adc`/`light_raw_adc` (calibrated fields are optional). The backend adds `recorded_at`; do not send it from the ESP32. `tds_ppm` means approximate TDS from the prepared soil-water extract, not direct soil EC or NPK. Keep the probe in the extract solution and use a known solution to calibrate it.
