/*
 * PlantMate ESP32 DevKit sensor uploader.
 *
 * Install the Adafruit DHT sensor library and Adafruit Unified Sensor library.
 * Copy plantmate_secrets.h.example to plantmate_secrets.h, then set the
 * local Wi-Fi, API, and device-key values. Soil and light are sent as raw ADC
 * until measured calibration values are available.
 */

#include <Arduino.h>
#include <DHT.h>
#include <HTTPClient.h>
#include <math.h>
#include <string.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>

#include "plantmate_secrets.h"

#ifndef WIFI_SSID
#error "Set WIFI_SSID in firmware/esp32/plantmate_secrets.h"
#endif
#ifndef WIFI_PASSWORD
#error "Set WIFI_PASSWORD in firmware/esp32/plantmate_secrets.h"
#endif
#ifndef DEVICE_INGESTION_KEY
#error "Set DEVICE_INGESTION_KEY in firmware/esp32/plantmate_secrets.h"
#endif
#ifndef DEVICE_ID
#error "Set DEVICE_ID in firmware/esp32/plantmate_secrets.h"
#endif
#ifndef API_URL
#error "Set API_URL in firmware/esp32/plantmate_secrets.h"
#endif

#ifndef TDS_CALIBRATION_FACTOR
#error "Set TDS_CALIBRATION_FACTOR after calibrating the TDS board"
#endif
#ifndef TDS_REFERENCE_TEMPERATURE_C
#error "Set TDS_REFERENCE_TEMPERATURE_C for the soil-water extract"
#endif

namespace {
constexpr uint8_t SOIL_PIN = 34;
constexpr uint8_t DHT_PIN = 27;
constexpr uint8_t LIGHT_PIN = 35;
constexpr uint8_t TDS_PIN = 32;
constexpr uint32_t REPORT_INTERVAL_MS = 12000;
constexpr uint32_t WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint32_t HTTP_TIMEOUT_MS = 7000;
constexpr uint8_t ADC_SAMPLES = 12;
constexpr float TDS_VOLTAGE_CURVE_A = 133.42f;
constexpr float TDS_VOLTAGE_CURVE_B = 255.86f;
constexpr float TDS_VOLTAGE_CURVE_C = 857.39f;
constexpr float TDS_TEMPERATURE_COEFFICIENT = 0.02f;

DHT dht(DHT_PIN, DHT22);
uint32_t lastReportAt = 0;
uint32_t lastWifiAttemptAt = 0;

struct SensorPacket {
  uint16_t soilRawAdc;
  bool soilCalibrated;
  float soilMoisturePercent;
  float temperatureC;
  float humidityPercent;
  uint16_t lightRawAdc;
  bool lightCalibrated;
  float lightLux;
  float tdsPpm;
};

bool soilCalibrationIsUsable() {
#if defined(SOIL_DRY_ADC_RAW) && defined(SOIL_WET_ADC_RAW)
  return SOIL_DRY_ADC_RAW >= 0 && SOIL_DRY_ADC_RAW <= 4095 &&
         SOIL_WET_ADC_RAW >= 0 && SOIL_WET_ADC_RAW <= 4095 &&
         SOIL_DRY_ADC_RAW != SOIL_WET_ADC_RAW;
#else
  return false;
#endif
}

bool lightCalibrationIsUsable() {
#if defined(LIGHT_DARK_ADC_RAW) && defined(LIGHT_BRIGHT_ADC_RAW) && defined(LIGHT_BRIGHT_LUX)
  return LIGHT_DARK_ADC_RAW >= 0 && LIGHT_DARK_ADC_RAW <= 4095 &&
         LIGHT_BRIGHT_ADC_RAW >= 0 && LIGHT_BRIGHT_ADC_RAW <= 4095 &&
         LIGHT_DARK_ADC_RAW != LIGHT_BRIGHT_ADC_RAW && LIGHT_BRIGHT_LUX > 0.0f;
#else
  return false;
#endif
}

uint16_t averageAdcRaw(uint8_t pin) {
  uint32_t total = 0;
  for (uint8_t sample = 0; sample < ADC_SAMPLES; ++sample) {
    total += static_cast<uint16_t>(analogRead(pin));
    delay(4);
  }
  return static_cast<uint16_t>(total / ADC_SAMPLES);
}

float averageAdcMillivolts(uint8_t pin) {
  uint32_t total = 0;
  for (uint8_t sample = 0; sample < ADC_SAMPLES; ++sample) {
    total += static_cast<uint32_t>(analogReadMilliVolts(pin));
    delay(4);
  }
  return static_cast<float>(total) / ADC_SAMPLES;
}

float soilMoisturePercent(uint16_t raw) {
#if defined(SOIL_DRY_ADC_RAW) && defined(SOIL_WET_ADC_RAW)
  const float scaled = 100.0f * (SOIL_DRY_ADC_RAW - raw) /
                       static_cast<float>(SOIL_DRY_ADC_RAW - SOIL_WET_ADC_RAW);
  return constrain(scaled, 0.0f, 100.0f);
#else
  (void)raw;
  return 0.0f;
#endif
}

float lightLux(uint16_t raw) {
#if defined(LIGHT_DARK_ADC_RAW) && defined(LIGHT_BRIGHT_ADC_RAW) && defined(LIGHT_BRIGHT_LUX)
  const float fraction = (static_cast<float>(raw) - LIGHT_DARK_ADC_RAW) /
                         static_cast<float>(LIGHT_BRIGHT_ADC_RAW - LIGHT_DARK_ADC_RAW);
  return constrain(fraction, 0.0f, 1.0f) * LIGHT_BRIGHT_LUX;
#else
  (void)raw;
  return 0.0f;
#endif
}

float tdsFromMillivolts(float millivolts) {
  const float voltage = millivolts / 1000.0f;
  const float compensation =
      1.0f + TDS_TEMPERATURE_COEFFICIENT * (TDS_REFERENCE_TEMPERATURE_C - 25.0f);
  const float compensatedVoltage = voltage / compensation;
  const float voltageSquared = compensatedVoltage * compensatedVoltage;
  const float voltageCubed = voltageSquared * compensatedVoltage;
  return (TDS_VOLTAGE_CURVE_A * voltageCubed -
          TDS_VOLTAGE_CURVE_B * voltageSquared +
          TDS_VOLTAGE_CURVE_C * compensatedVoltage) * TDS_CALIBRATION_FACTOR;
}

bool readSensors(SensorPacket &packet) {
  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();
  if (!isfinite(temperature) || !isfinite(humidity)) {
    Serial.println(F("DHT22 read failed; packet skipped."));
    return false;
  }

  const uint16_t soilRaw = averageAdcRaw(SOIL_PIN);
  const uint16_t lightRaw = averageAdcRaw(LIGHT_PIN);
  const float tdsMilliVolts = averageAdcMillivolts(TDS_PIN);

  packet.soilRawAdc = soilRaw;
  packet.soilCalibrated = soilCalibrationIsUsable();
  packet.soilMoisturePercent = packet.soilCalibrated ? soilMoisturePercent(soilRaw) : 0.0f;
  packet.temperatureC = temperature;
  packet.humidityPercent = humidity;
  packet.lightRawAdc = lightRaw;
  packet.lightCalibrated = lightCalibrationIsUsable();
  packet.lightLux = packet.lightCalibrated ? lightLux(lightRaw) : 0.0f;
  packet.tdsPpm = tdsFromMillivolts(tdsMilliVolts);

  if ((packet.soilCalibrated && (!isfinite(packet.soilMoisturePercent) ||
                                 packet.soilMoisturePercent < 0.0f ||
                                 packet.soilMoisturePercent > 100.0f)) ||
      packet.temperatureC < -40.0f || packet.temperatureC > 85.0f ||
      packet.humidityPercent < 0.0f || packet.humidityPercent > 100.0f ||
      (packet.lightCalibrated && (!isfinite(packet.lightLux) || packet.lightLux < 0.0f ||
                                  packet.lightLux > 200000.0f)) ||
      !isfinite(packet.tdsPpm) || packet.tdsPpm < 0.0f ||
      packet.tdsPpm > 10000.0f) {
    Serial.println(F("Reading is outside the API's accepted ranges; packet skipped."));
    return false;
  }

  Serial.printf("Soil %u ADC | Air %.1f C | Humidity %.1f%% | Light %u ADC | "
                "Approx. TDS from soil-water extract %.1f ppm\n",
                packet.soilRawAdc, packet.temperatureC, packet.humidityPercent,
                packet.lightRawAdc, packet.tdsPpm);
  return true;
}

void maintainWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  const uint32_t now = millis();
  if (now - lastWifiAttemptAt < WIFI_RETRY_INTERVAL_MS) return;
  lastWifiAttemptAt = now;
  Serial.println(F("Wi-Fi disconnected; reconnecting..."));
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

String makeJson(const SensorPacket &packet) {
  String json;
  json.reserve(224);
  json = F("{\"device_id\":\"");
  json += DEVICE_ID;
  json += F("\",\"soil_moisture_raw_adc\":");
  json += String(packet.soilRawAdc);
  if (packet.soilCalibrated) {
    json += F(",\"soil_moisture\":");
    json += String(packet.soilMoisturePercent, 1);
  }
  json += F(",\"temperature_c\":");
  json += String(packet.temperatureC, 1);
  json += F(",\"humidity\":");
  json += String(packet.humidityPercent, 1);
  json += F(",\"light_raw_adc\":");
  json += String(packet.lightRawAdc);
  if (packet.lightCalibrated) {
    json += F(",\"light_lux\":");
    json += String(packet.lightLux, 1);
  }
  json += F(",\"tds_ppm\":");
  json += String(packet.tdsPpm, 1);
  json += '}';
  return json;
}

template <typename ClientType>
int postWithClient(ClientType &client, const String &json) {
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(client, API_URL)) {
    Serial.println(F("Could not initialize HTTP request."));
    return -1;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader(F("X-Device-Key"), DEVICE_INGESTION_KEY);
  const int status = http.POST(json);
  http.end();
  return status;
}

void sendPacket(const SensorPacket &packet) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("Wi-Fi unavailable; reading not sent."));
    return;
  }

  const String json = makeJson(packet);
  const String url(API_URL);
  int status = -1;

  if (url.startsWith("https://")) {
    if (ROOT_CA_CERT == nullptr || strlen(ROOT_CA_CERT) == 0) {
      Serial.println(F("HTTPS requires the server root CA in ROOT_CA_CERT; request skipped."));
      return;
    }
    WiFiClientSecure client;
    client.setCACert(ROOT_CA_CERT);
    status = postWithClient(client, json);
  } else if (url.startsWith("http://")) {
    WiFiClient client;
    status = postWithClient(client, json);
  } else {
    Serial.println(F("API_URL must begin with http:// or https://."));
    return;
  }

  if (status == HTTP_CODE_CREATED) {
    Serial.println(F("Reading accepted by PlantMate."));
  } else if (status == HTTP_CODE_UNAUTHORIZED) {
    Serial.println(F("HTTP 401: check DEVICE_INGESTION_KEY in local firmware secrets."));
  } else if (status == HTTP_CODE_SERVICE_UNAVAILABLE) {
    Serial.println(F("HTTP 503: backend device ingestion key is not configured."));
  } else if (status == 422) {
    Serial.println(F("HTTP 422: backend rejected the sensor values or JSON schema."));
  } else if (status < 0) {
    Serial.printf("HTTP transport error: %s\n", HTTPClient::errorToString(status).c_str());
  } else {
    Serial.printf("Unexpected HTTP status: %d\n", status);
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  analogReadResolution(12);
  analogSetPinAttenuation(SOIL_PIN, ADC_11db);
  analogSetPinAttenuation(LIGHT_PIN, ADC_11db);
  analogSetPinAttenuation(TDS_PIN, ADC_11db);
  dht.begin();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  Serial.println(F("PlantMate ESP32 sensor uploader starting."));
  Serial.printf("API endpoint: %s\n", API_URL);
  Serial.println(F("Soil and light report raw ADC until calibrated; raw values are not percent or lux."));
  Serial.println(F("TDS is approximate TDS from a soil-water extract, not direct soil EC or NPK."));
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttemptAt = millis();
}

void loop() {
  maintainWifi();
  const uint32_t now = millis();
  if (now - lastReportAt < REPORT_INTERVAL_MS) return;
  lastReportAt = now;

  SensorPacket packet{};
  if (!readSensors(packet)) return;
  sendPacket(packet);
}
