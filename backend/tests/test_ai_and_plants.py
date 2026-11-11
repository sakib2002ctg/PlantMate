"""Plant profile and AI adviser behavior tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.api.v1 import ai, plants
from app.models.plant_profile import PlantProfile
from app.modules.ai import service
from app.modules.ai.schemas import ChatRequest
from app.modules.plants.schemas import PlantProfileInput


def test_chat_request_bounds_and_language() -> None:
    assert ChatRequest(question="Explain the sensor data", language="en").language == "en"
    assert ChatRequest(question="আমার গাছের যত্ন কীভাবে নেব?", language="bn").language == "bn"
    with pytest.raises(ValidationError):
        ChatRequest(question="x" * 2001)
    with pytest.raises(ValidationError):
        ChatRequest(question="Hello", language="fr")


def test_gemini_missing_key_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key=None, gemini_model="gemini-test"),
    )
    with pytest.raises(service.AIUnavailableError, match="not configured"):
        service.require_api_key()


def test_gemini_timeout_is_sanitized_and_logged_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = service._timeout_error(httpx.ReadTimeout("private request details"), 60.127)

    assert service.GEMINI_TIMEOUT_SECONDS == 60.0
    assert error.args == ("AI adviser is temporarily unavailable",)
    assert "Gemini request timed out" in caplog.text
    assert "private request details" not in caplog.text
    assert "private sensor prompt" not in caplog.text
    assert "test-provider-key" not in caplog.text
    record = caplog.records[-1]
    assert record.event == "gemini_timeout"
    assert record.exception_class == "ReadTimeout"
    assert record.elapsed_seconds == 60.127


def test_prompt_marks_raw_adc_and_tds_as_estimates() -> None:
    prompt = service.grounded_prompt(
        {"species": "basil"},
        [{"soil_raw_adc": 2722, "light_raw_adc": 2709, "approx_tds_soil_water_extract_ppm": 58.5}],
        "What should I do?",
    )
    assert "raw ADC is uncalibrated" in prompt
    assert "not soil EC or NPK" in prompt
    assert "soil_raw_adc" in prompt


def test_provider_error_does_not_expose_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ai,
        "get_settings",
        lambda: SimpleNamespace(gemini_api_key=SecretStr("hidden")),
    )
    error = ai._provider_error(service.AIUnavailableError("private upstream detail"))
    assert error.status_code == 502
    assert error.detail == "AI adviser is temporarily unavailable"
    assert "private" not in error.detail


def test_plant_profile_validates_device_and_lengths() -> None:
    profile = PlantProfileInput(
        plant_name="Basil",
        species="Ocimum basilicum",
        plant_type="herb",
        planting_date=datetime.now(UTC).date(),
        device_id="plantmate-esp32-demo",
    )
    assert profile.species == "Ocimum basilicum"
    with pytest.raises(ValidationError):
        PlantProfileInput(plant_name="", species="Basil", device_id="bad id")


def test_plant_profile_can_be_created_and_edited(test_session_factory) -> None:
    with test_session_factory() as db:
        first = plants.save_profile(
            PlantProfileInput(plant_name="Basil", species="Ocimum basilicum", device_id="sensor-1"),
            db,
        )
        changed = plants.save_profile(
            PlantProfileInput(
                plant_name="Sweet basil", species="Ocimum basilicum", device_id="sensor-1"
            ),
            db,
        )
        assert first.id == changed.id
        assert plants.get_profile(db).plant_name == "Sweet basil"
        assert len(list(db.scalars(select(PlantProfile)).all())) == 1


