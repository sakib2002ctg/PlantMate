# PlantMate

PlantMate is a public plant-monitoring dashboard backed by an ESP32 sensor, FastAPI, and PostgreSQL. The dashboard is read-only and requires no account or login. Only device ingestion is protected.

## Local setup (Windows PowerShell)

1. Copy `.env.example` to `.env`. Keep the PostgreSQL username, password, database, port, and `DATABASE_URL` in sync. The checked-in `.env` is local-only and ignored by Git.
2. Set `DEVICE_INGESTION_KEY` to a long random value. Share that value with the ESP32 firmware through its local build configuration; send it only in the `X-Device-Key` header. Never put it in a `VITE_` variable or frontend file.
3. Start PostgreSQL with `docker compose up -d db`. The compose file uses the existing named volume `plantmate_postgres_data`; do not use `docker compose down -v` unless intentionally resetting local data.
4. Set up and start the backend in PowerShell:

   ```powershell
   cd backend
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

   The API listens on `http://localhost:8000`. Root `.env` is loaded automatically.

5. Start the frontend in another PowerShell window:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

   The public dashboard is at `http://localhost:5173`. `frontend/.env` is optional locally; set `VITE_API_BASE_URL` there only if the API is not at `http://localhost:8000/api/v1`.

6. Run backend checks from `backend` with `pytest` and `ruff check .`; run the frontend production check from `frontend` with `npm run build`.

## API

All application routes use `/api/v1`.

| Method | Route | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/dashboard/latest` | Public, read-only | Latest real reading, update time, device freshness, and deterministic care status |
| `GET` | `/api/v1/dashboard/readings?since=<ISO timestamp>&until=<ISO timestamp>&limit=500` | Public, read-only | Historical readings, newest first; `limit` is 1–2000 |
| `POST` | `/api/v1/ingestion/readings` | ESP32 device key required | Validate and store one sensor packet; returns 201 |
| `GET` | `/health`, `/api/v1/health`, `/api/v1/health/db` | Public | Service and database health |
| `GET` / `PUT` | `/api/v1/plants/profile` | Public demo profile | Read or update the single garden plant profile |
| `GET` | `/api/v1/ai/status` | Public | Gemini configuration status (never returns the key) |
| `POST` | `/api/v1/ai/chat` | Public, rate limited | Ask a plant-care question grounded in stored profile/readings |
| `POST` | `/api/v1/ai/weekly-summary?language=en` | Public, rate limited | Summarize actual sensor data stored in the last week |

The ESP32 POST body is JSON with `device_id`, actual `temperature_c` (−40–85) and `humidity` (0–100), `tds_ppm` (0–10,000), plus soil and light measurements. For calibrated probes, send `soil_moisture` (0–100 percent) and `light_lux` (0–200,000); before calibration, send `soil_moisture_raw_adc` and `light_raw_adc` (each 0–4095). Each analog sensor must have either its calibrated field or raw ADC field. Raw ADC remains stored unchanged and is never displayed as lux; the dashboard derives a separate relative-light percentage from the centralized LDR reference points in `backend/app/modules/sensors/calibration.py`. This percentage is relative brightness, not lux. The timestamp is assigned by the API/database when the packet is received. The device sends the configured key in `X-Device-Key`; keys are never returned by the API.

`tds_ppm` is labelled **Approx. TDS from soil-water extract** in the UI. It is not direct soil electrical conductivity (EC) or NPK. The API rejects measurements outside sensor-domain bounds. The dashboard polls every 8 seconds. A device is online when its latest stored reading is within the configured `DEVICE_ONLINE_WINDOW_SECONDS` (default 120 seconds), offline after that, and “awaiting device” before the first reading.

Plant status is a small deterministic heuristic based only on received calibrated soil moisture, temperature, and humidity: very dry soil (<20%), low moisture (<35%), high temperature (>35 °C), low temperature (<8 °C), and low humidity (<25%) raise an attention message. When soil is raw ADC, moisture-based status is shown as unavailable until calibrated. It does not synthesize missing readings or claim species-specific diagnosis. Adjust these starter ranges for the actual plant and sensor calibration before treating them as horticultural advice.

## ESP32 and cloud deployment

- The Arduino sketch is in `firmware/esp32/PlantMateESP32/PlantMateESP32.ino`. Copy `firmware/esp32/PlantMateESP32/plantmate_secrets.h.example` to `firmware/esp32/PlantMateESP32/plantmate_secrets.h`; the copied file is Git-ignored. Enter Wi-Fi credentials, the device key, device ID, and backend URL only in the ignored local header. Soil and light calibration are optional for ingestion.
- Install Espressif's **esp32** board package in Arduino IDE's Boards Manager, and install **DHT sensor library** by Adafruit and its **Adafruit Unified Sensor** dependency using Library Manager. Select an ESP32 Dev Module board and its USB COM port.
- For a laptop backend on the same Wi-Fi, start FastAPI so it listens on the LAN interface: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. Run `ipconfig` on the laptop and use the IPv4 address for its active Wi-Fi adapter in `API_URL`, for example `http://192.168.1.25:8000/api/v1/ingestion/readings`. The ESP32 and laptop must be on the same reachable network (2.4 GHz Wi-Fi for typical ESP32 DevKit boards); allow Python/port 8000 on the Windows **Private** network firewall if prompted. Do not use `localhost` in the device URL. Router client/AP isolation must be disabled.
- The sketch reports every 12 seconds. Open Arduino IDE's Serial Monitor at 115200 baud. A `201`/accepted message means the API stored that actual sensor packet. A Wi-Fi retry message indicates the device is reconnecting. `401`, `422`, and `503` messages identify a key mismatch, invalid sensor values/schema, or an unconfigured backend key, respectively. The sketch does not print the key or HTTP response body.
- Until measured calibration is supplied, the firmware sends soil-probe and LDR readings as raw ADC counts (0–4095). Raw ADC remains displayed unchanged; the dashboard separately derives **Light (relative %)** using the two documented LDR reference points. This percentage is relative brightness, not lux. To enable soil-care guidance, calibrate dry/wet raw ADC points on your own probe. Do not treat a guessed value as calibrated. The TDS conversion follows the DFRobot Gravity SEN0244 polynomial and uses a configurable calibration factor and soil-water-sample reference temperature; confirm that it matches your analog TDS board and calibrate it with a known solution. The DHT22 is ambient air temperature/humidity, not liquid temperature. TDS is labelled as **Approx. TDS from soil-water extract**, not direct soil EC or NPK; place the probe in the prepared soil-water extract, never directly into soil. See [DFRobot's TDS sensor documentation](https://wiki.dfrobot.com/sen0244) for the formula and calibration process.
- Keep analog outputs at or below 3.3 V at ESP32 pins and share sensor/board ground. The configured analog inputs use ADC1, which remains available while Wi-Fi is active; GPIO34/35 are input-only and are used only as analog inputs. Espressif documents the [ESP32 GPIO/ADC mapping and ADC2 Wi-Fi limitation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html).
- For a cloud backend, set `API_URL` to its HTTPS ingestion URL and place its trusted root CA PEM in `ROOT_CA_CERT` in the ignored header. The firmware verifies TLS certificates and refuses HTTPS if no CA is configured; do not disable certificate validation.
- Deploy FastAPI on a platform that supports Python, environment variables/secrets, and outbound PostgreSQL connections. Configure `DATABASE_URL`, `DEVICE_INGESTION_KEY`, `CORS_ALLOWED_ORIGINS`, and optionally `DEVICE_ONLINE_WINDOW_SECONDS` in the backend environment. Use a managed PostgreSQL service and TLS settings required by that provider.
- Deploy `frontend/` to Vercel. Set `VITE_API_BASE_URL` to the deployed backend origin followed by `/api/v1`. Set backend `CORS_ALLOWED_ORIGINS` to the exact frontend origin, such as `https://your-project.vercel.app` (comma-separated for multiple origins). Dashboard reads are public and the device key is sent only by ESP32.
- For the AI adviser, set backend-only `GEMINI_API_KEY` and optionally `GEMINI_MODEL` (defaults to `gemini-2.0-flash`) in `.env` or the hosting provider's secret manager. Never create a `VITE_GEMINI_API_KEY` or put the provider key in frontend configuration. AI requests are capped at 2,000 question characters, 8 KB request size, 20 seconds provider timeout, and five requests per client IP per minute per backend process. AI routes return a clear unavailable response when no key is configured; the public live dashboard continues to work.

## Database history and migrations

Alembic revision `0001_initial_schema` is the original baseline, `0002_users` is a historical authentication migration, and `0003_sensor_readings` adds the sensor table. Firebase, authentication routes, account models, and frontend sign-in dependencies have been removed from the running application. The historical `0002_users` migration remains in the chain so existing databases can upgrade without rewriting applied migration history; its old table is not used by the application. The sensor migration is additive and does not remove the existing database, volume, or prior table data.

## Project layout

- `backend/` — FastAPI application, SQLAlchemy models, ingestion/dashboard API, migrations, and tests.
- `frontend/` — React, TypeScript, and Vite public dashboard.
- `firmware/esp32/` — Arduino IDE sketch, ignored local secrets, and hardware setup guide.
- `docs/` — reserved for project documentation.
