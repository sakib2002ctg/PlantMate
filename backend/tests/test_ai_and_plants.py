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


def test_prompt_bounds_readings_and_includes_seven_day_summaries() -> None:
    readings = [
        {
            "recorded_at": str(i),
            "soil_moisture_percent": float(i),
            "temperature_c": 20 + i,
            "air_humidity_percent": 40 + i,
            "light_relative_percent": 50 + i,
            "approx_tds_soil_water_extract_ppm": 10 + i,
        }
        for i in range(30)
    ]
    prompt = service.grounded_prompt({}, readings, "Advice")
    assert prompt.count("'recorded_at'") == 20
    assert len(prompt) < service.MAX_PROMPT_CHARS
    assert "soil moisture (%)" in prompt
    assert "temperature (°C)" in prompt
    assert "humidity (%)" in prompt
    assert "relative light (% relative brightness)" in prompt
    assert "TDS (ppm soil-water extract)" in prompt
    assert "not soil EC or NPK" in prompt


def test_retry_after_is_bounded() -> None:
    assert service._retry_after(httpx.Response(503, headers={"Retry-After": "8"})) == 5
    assert service._retry_after(httpx.Response(503, headers={"Retry-After": "2"})) == 2
    assert service._retry_after(httpx.Response(503, headers={})) == 1


@pytest.mark.parametrize(
    ("statuses", "expected_calls"),
    [([503, 200], 2), ([503, 503], 2), ([401], 1), ([403], 1), ([404], 1), ([400], 1)],
)
@pytest.mark.anyio
async def test_provider_retry_policy(monkeypatch, caplog, statuses, expected_calls) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, status):
            self.status_code = status
            self.headers = {"Retry-After": "99"}
            self.is_error = status >= 400

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            calls.append(kwargs)
            return FakeResponse(statuses[min(len(calls) - 1, len(statuses) - 1)])

    delays = []
    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(service.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(service, "retry_sleep", fake_sleep)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        gemini_api_key=SecretStr("private-api-key"), gemini_model="gemini-test"
    ))
    if statuses[0] >= 400 and statuses[0] != 503:
        with pytest.raises(service.AIUnavailableError):
            await service.generate("private complete prompt", "en")
    elif statuses == [503, 503]:
        with pytest.raises(service.AIUnavailableError):
            await service.generate("private complete prompt", "en")
    else:
        assert await service.generate("private complete prompt", "en") == "ok"
    assert len(calls) == expected_calls
    assert delays == ([5.0] if statuses[0] == 503 else [])
    assert all("x-goog-api-key" in call["headers"] for call in calls)
    assert "private-api-key" not in caplog.text
    assert "private complete prompt" not in caplog.text


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("private"), httpx.ReadTimeout("secret")])
@pytest.mark.anyio
async def test_provider_timeout_is_not_retried(monkeypatch, error, caplog):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            calls.append(1)
            raise error

    monkeypatch.setattr(service.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(
        gemini_api_key=SecretStr("private-api-key"), gemini_model="gemini-test"
    ))
    with pytest.raises(service.AIUnavailableError):
        await service.generate("private complete prompt", "en")
    assert len(calls) == 1
    assert "private-api-key" not in caplog.text
    assert "private complete prompt" not in caplog.text


def test_oversized_prompt_preserves_question_and_instructions_or_fails_safely() -> None:
    profile = {"description": "plant details " * 1200}
    prompt = service.grounded_prompt(
        profile, [{"recorded_at": str(i)} for i in range(20)], "FINAL QUESTION"
    )
    assert len(prompt) <= service.MAX_PROMPT_CHARS
    assert prompt.endswith("User question: FINAL QUESTION")
    assert "Interpretation rules" in prompt
    assert "not soil EC or NPK" in prompt


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
