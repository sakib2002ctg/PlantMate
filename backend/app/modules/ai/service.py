"""Gemini adapter grounded exclusively in supplied PlantMate measurements."""

import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
GEMINI_TIMEOUT_SECONDS = 60.0


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


def _grounding_context(profile: object, readings: list[dict[str, object]]) -> str:
    plant = {
        "name": getattr(profile, "plant_name", ""),
        "species": getattr(profile, "species", ""),
        "type": getattr(profile, "plant_type", ""),
        "planting_date": str(getattr(profile, "planting_date", "") or "not provided"),
        "description": getattr(profile, "description", None) or "not provided",
        "device_id": getattr(profile, "device_id", ""),
    }
    return (
        "Plant profile (user supplied): "
        f"{plant!r}\nActual stored sensor readings (newest first): {readings!r}\n"
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
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    started_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                endpoint,
                headers={"x-goog-api-key": api_key},
                json={
                    "system_instruction": {
                        "parts": [
                            {
                                "text": (
                                    "Answer safely and simply in "
                                    + ("Bangla" if language == "bn" else "English")
                                    + ". Use only the supplied sensor facts."
                                )
                            }
                        ]
                    },
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 700, "temperature": 0.3},
                },
            )
            response.raise_for_status()
            result = response.json()
            answer = result["candidates"][0]["content"]["parts"][0]["text"]
            if not isinstance(answer, str) or not answer.strip():
                raise AIUnavailableError("AI adviser returned no answer")
            return answer.strip()
    except httpx.TimeoutException as exc:
        raise _timeout_error(exc, time.monotonic() - started_at) from None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        logger.warning("Gemini request failed or returned an invalid response")
        raise AIUnavailableError("AI adviser is temporarily unavailable") from None


def grounded_prompt(profile: object, readings: list[dict[str, object]], question: str) -> str:
    return f"{_grounding_context(profile, readings)}\n\nUser question: {question}"
