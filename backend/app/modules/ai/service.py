"""Gemini adapter grounded exclusively in supplied PlantMate measurements."""

import asyncio
import email.utils
import logging
import statistics
import time
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
GEMINI_TIMEOUT_SECONDS = 60.0
MAX_PROMPT_CHARS = 12_000
MAX_READING_CONTEXT = 20
MAX_RETRY_AFTER_SECONDS = 5.0
retry_sleep = asyncio.sleep


class AIUnavailableError(Exception):
    """Provider key is absent or Gemini failed safely."""


def require_api_key() -> tuple[str, str]:
    settings = get_settings()
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not key:
        raise AIUnavailableError("AI adviser is not configured")
    return key, settings.gemini_model


def _timeout_error(exc: httpx.TimeoutException, elapsed_seconds: float) -> AIUnavailableError:
    logger.warning(
        "Gemini request timed out",
        extra={
            "event": "gemini_timeout",
            "exception_class": type(exc).__name__,
            "elapsed_seconds": round(elapsed_seconds, 3),
        },
    )
    return AIUnavailableError("AI adviser is temporarily unavailable")


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "")
    try:
        delay = float(value)
    except ValueError:
        try:
            retry_at = email.utils.parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            delay = (retry_at - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return 1.0
    return min(max(delay, 0.0), MAX_RETRY_AFTER_SECONDS)


def _log_failure(
    category: str, exception_class: str, elapsed: float, status: int | None = None
) -> None:
    logger.warning(
        "Gemini provider request failed",
        extra={
            "event": "gemini_provider_failure",
            "http_status": status,
            "exception_class": exception_class,
            "elapsed_seconds": round(elapsed, 3),
            "error_category": category,
        },
    )


def _grounding_context(profile: object, readings: list[dict[str, object]]) -> str:
    plant = {
        "name": getattr(profile, "plant_name", ""),
        "species": getattr(profile, "species", ""),
        "type": getattr(profile, "plant_type", ""),
        "planting_date": str(getattr(profile, "planting_date", "") or "not provided"),
        "description": getattr(profile, "description", None) or "not provided",
        "device_id": getattr(profile, "device_id", ""),
    }
    metrics = {
        "soil moisture": ("soil_moisture_percent", "%"),
        "temperature": ("temperature_c", "°C"),
        "humidity": ("air_humidity_percent", "%"),
        "relative light": ("light_relative_percent", "% relative brightness"),
        "TDS": ("approx_tds_soil_water_extract_ppm", "ppm soil-water extract"),
    }
    summaries = []
    for label, (field, unit) in metrics.items():
        values = [r.get(field) for r in readings if isinstance(r.get(field), (int, float))]
        if values:
            summaries.append(
                f"{label} ({unit}): min {min(values):.1f}, max {max(values):.1f}, "
                f"average {statistics.fmean(values):.1f}, latest {values[0]:.1f}"
            )
        else:
            summaries.append(f"{label} ({unit}): no calibrated readings available")
    trend_summary = "\n7-day summaries from supplied readings: " + "; ".join(summaries)
    return (
        "Plant profile (user supplied): "
        f"{plant!r}\nActual stored sensor readings (newest first): "
        f"{readings[:MAX_READING_CONTEXT]!r}\n"
        f"{trend_summary}\n"
        "Measurement units: calibrated soil moisture is percent; soil_raw_adc and "
        "light_raw_adc are 0–4095 ADC counts; light_relative_percent is relative "
        "brightness derived from the documented LDR ADC references, not lux; "
        "temperature is degrees C; humidity is percent; TDS is approximate ppm "
        "from soil-water extract. Deterministic care status is attached per reading.\n"
        "Interpretation rules: raw ADC is uncalibrated and is not a percent or lux value. "
        "TDS is approximate TDS from soil-water extract, not soil EC or NPK. "
        "Explicitly say when a measurement is missing. Never invent measurements, trends, "
        "diagnoses, or calibration. Distinguish observation from general plant-care advice."
    )


async def generate(prompt: str, language: str) -> str:
    api_key, model = require_api_key()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    if len(prompt) > MAX_PROMPT_CHARS:
        raise AIUnavailableError("AI adviser context is too large")
    started_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_SECONDS) as client:
            for attempt in range(2):
                response = await client.post(
                    endpoint,
                    headers={"x-goog-api-key": api_key},
                    json={
                        "system_instruction": {
                            "parts": [
                                {
                                    "text": "Answer safely and simply in "
                                    + ("Bangla" if language == "bn" else "English")
                                    + ". Use only the supplied sensor facts."
                                }
                            ]
                        },
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": 700, "temperature": 0.3},
                    },
                )
                if response.status_code == 503 and attempt == 0:
                    await retry_sleep(_retry_after(response))
                    continue
                if response.is_error:
                    elapsed = time.monotonic() - started_at
                    category = {
                        401: "authentication",
                        403: "authorization",
                        404: "model_or_endpoint",
                        429: "rate_limit",
                        503: "service_unavailable",
                    }.get(response.status_code, "http_error")
                    _log_failure(category, "HTTPStatusError", elapsed, response.status_code)
                    raise AIUnavailableError("AI adviser is temporarily unavailable")
                break
            result = response.json()
            answer = result["candidates"][0]["content"]["parts"][0]["text"]
            if not isinstance(answer, str) or not answer.strip():
                raise AIUnavailableError("AI adviser returned no answer")
            return answer.strip()
    except httpx.TimeoutException as exc:
        raise _timeout_error(exc, time.monotonic() - started_at) from None
    except AIUnavailableError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        _log_failure(
            "transport_or_invalid_response", type(exc).__name__, time.monotonic() - started_at
        )
        raise AIUnavailableError("AI adviser is temporarily unavailable") from None


def grounded_prompt(profile: object, readings: list[dict[str, object]], question: str) -> str:
    bounded = readings[:MAX_READING_CONTEXT]
    # Compact the oldest raw records first while retaining summaries computed from all
    # supplied seven-day readings and keeping the question and safety notes intact.
    for count in range(len(bounded), -1, -1):
        context = _grounding_context(profile, readings)
        marker = "Actual stored sensor readings (newest first): "
        start = context.index(marker) + len(marker)
        end = context.index("\n", start)
        compact_context = context[:start] + repr(bounded[:count]) + context[end:]
        prompt = f"{compact_context}\n\nUser question: {question}"
        if len(prompt) <= MAX_PROMPT_CHARS:
            return prompt
    raise AIUnavailableError("AI adviser context is too large to preserve required instructions")
