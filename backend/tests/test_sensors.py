"""Sensor ingestion and public dashboard API tests."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError

from app.api.v1 import dashboard, ingestion
from app.main import app
from app.modules.sensors.calibration import relative_light_percent
from app.modules.sensors.schemas import SensorReadingCreate


@pytest.fixture
def api_settings(monkeypatch):
    monkeypatch.setattr(
        ingestion,
        "get_settings",
        lambda: SimpleNamespace(device_ingestion_key=SecretStr("test-device-key")),
    )
    monkeypatch.setattr(
        dashboard,
        "get_settings",
        lambda: SimpleNamespace(device_online_window_seconds=120),
    )


PAYLOAD = {
    "device_id": "esp32-greenhouse-1",
    "soil_moisture": 42.5,
    "temperature_c": 23.4,
    "humidity": 58,
    "light_lux": 930,
    "tds_ppm": 410,
}

RAW_PAYLOAD = {
    "device_id": "esp32-greenhouse-1",
    "soil_moisture_raw_adc": 2280,
    "temperature_c": 23.4,
    "humidity": 58,
    "light_raw_adc": 3510,
    "tds_ppm": 410,
}


@pytest.mark.parametrize(
    ("raw_adc", "expected"),
    [(4095, 0.0), (60, 100.0), (2078, pytest.approx(50.0, abs=0.02)), (0, 100.0)],
)
def test_relative_light_calibration(raw_adc: int, expected: float) -> None:
    assert relative_light_percent(raw_adc) == expected


@pytest.mark.parametrize("raw_adc", [-1, 4096, 60.5, True])
def test_relative_light_calibration_rejects_invalid_adc(raw_adc: int) -> None:
    with pytest.raises(ValueError, match="integer from 0 through 4095"):
        relative_light_percent(raw_adc)

ESP32_QUICK_DEMO_PAYLOAD = {
    "device_id": "plantmate-esp32-demo",
    "soil_moisture_raw_adc": 2722,
    "temperature_c": 29.3,
    "humidity": 66.3,
    "light_raw_adc": 2709,
    "tds_ppm": 58.5,
}


def test_ingestion_requires_device_key(api_settings) -> None:
    with pytest.raises(HTTPException) as error:
        ingestion.verify_device_key(None)
    assert error.value.status_code == 401


def test_ingestion_rejects_wrong_device_key(api_settings) -> None:
    with pytest.raises(HTTPException) as error:
        ingestion.verify_device_key("incorrect")
    assert error.value.status_code == 401


def test_ingestion_rejects_invalid_measurement(api_settings) -> None:
    with pytest.raises(ValidationError):
        SensorReadingCreate.model_validate({**PAYLOAD, "soil_moisture": 101})


def test_raw_adc_is_range_checked_and_both_analog_sensors_are_required(api_settings) -> None:
    with pytest.raises(ValidationError):
        SensorReadingCreate.model_validate({**RAW_PAYLOAD, "soil_moisture_raw_adc": 4096})
    with pytest.raises(ValidationError):
        SensorReadingCreate.model_validate(
            {key: value for key, value in RAW_PAYLOAD.items() if key != "soil_moisture_raw_adc"}
        )
    with pytest.raises(ValidationError):
        SensorReadingCreate.model_validate(
            {key: value for key, value in RAW_PAYLOAD.items() if key != "light_raw_adc"}
        )


def test_actual_esp32_quick_demo_payload_matches_ingestion_schema() -> None:
    payload = SensorReadingCreate.model_validate(ESP32_QUICK_DEMO_PAYLOAD)
    assert payload.soil_moisture_raw_adc == 2722
    assert payload.temperature_c == 29.3
    assert payload.humidity == 66.3
    assert payload.light_raw_adc == 2709
    assert payload.tds_ppm == 58.5
    assert payload.soil_moisture is None
    assert payload.light_lux is None
def test_ingestion_persists_and_dashboard_returns_real_reading(
    test_session_factory, api_settings
) -> None:
    payload = SensorReadingCreate.model_validate(PAYLOAD)
    ingestion.verify_device_key("test-device-key")
    with test_session_factory() as db:
        accepted = ingestion.ingest_reading(payload, None, db)
        latest = dashboard.latest_reading(db)
        history = dashboard.historical_readings(None, None, 500, db)

    stored = accepted.reading
    assert stored.soil_moisture == 42.5
    assert stored.tds_ppm == 410
    assert stored.recorded_at
    assert latest.reading and latest.reading.id == stored.id
    assert latest.connection_status == "online"
    assert latest.plant_health.status == "healthy"
    assert len(history) == 1
    assert history[0].id == stored.id


def test_ingestion_persists_raw_values_as_adc(test_session_factory, api_settings) -> None:
    payload = SensorReadingCreate.model_validate(RAW_PAYLOAD)
    with test_session_factory() as db:
        accepted = ingestion.ingest_reading(payload, None, db)
        latest = dashboard.latest_reading(db)
        history = dashboard.historical_readings(None, None, 500, db)

    assert accepted.reading.soil_moisture is None
    assert accepted.reading.soil_moisture_raw_adc == 2280
    assert accepted.reading.light_lux is None
    assert accepted.reading.light_raw_adc == 3510
    assert accepted.reading.light_percent == pytest.approx(relative_light_percent(3510))
    assert len(history) == 1
    assert history[0].light_raw_adc == 3510
    assert history[0].light_percent == pytest.approx(relative_light_percent(3510))
    assert history[0].recorded_at == accepted.reading.recorded_at
    assert latest.reading and latest.reading.light_raw_adc == 3510
    assert latest.plant_health.status == "unavailable"
    assert "raw ADC" in latest.plant_health.message


def test_empty_dashboard_does_not_fabricate_readings(test_session_factory, api_settings) -> None:
    with test_session_factory() as db:
        latest = dashboard.latest_reading(db)
        history = dashboard.historical_readings(None, None, 500, db)
    assert latest.reading is None
    assert latest.last_updated is None
    assert latest.connection_status == "never_connected"
    assert latest.plant_health.status == "unavailable"
    assert history == []


def test_device_key_is_not_accepted_by_public_dashboard(test_session_factory, api_settings) -> None:
    with test_session_factory() as db:
        response = dashboard.latest_reading(db)
    assert response.connection_status == "never_connected"


def test_app_has_public_dashboard_and_no_auth_routes() -> None:
    routes = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/v1/dashboard/latest" in routes
    assert "/api/v1/dashboard/readings" in routes
    assert "/api/v1/ingestion/readings" in routes
    assert not any("/auth" in route or route.endswith("/me") for route in routes)
