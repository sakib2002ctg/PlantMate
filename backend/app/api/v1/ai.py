"""Rate-limited public AI adviser routes."""

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.plant_profile import PlantProfile
from app.models.sensor_reading import SensorReading
from app.modules.ai.schemas import AIStatus, ChatRequest, ChatResponse, WeeklySummaryResponse
from app.modules.ai.service import AIUnavailableError, generate, grounded_prompt
from app.modules.sensors.care_rules import assess_plant_health

router = APIRouter(prefix="/ai", tags=["AI plant adviser"])
_requests: dict[str, deque[datetime]] = defaultdict(deque)
_WINDOW = timedelta(minutes=1)
_LIMIT = 5


def enforce_rate_limit(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    now = datetime.now(UTC)
    calls = _requests[host]
    while calls and now - calls[0] > _WINDOW:
        calls.popleft()
    if len(calls) >= _LIMIT:
        raise HTTPException(status_code=429, detail="AI request limit reached; try again shortly")
    calls.append(now)


def _provider_error(error: AIUnavailableError) -> HTTPException:
    settings = get_settings()
    configured = any(
        key is not None and bool(key.get_secret_value())
        for key in (settings.groq_api_key, settings.gemini_api_key)
    )
    if not configured:
        return HTTPException(status_code=503, detail="AI adviser is not configured")
    return HTTPException(status_code=502, detail="AI adviser is temporarily unavailable")


def _context(db: Session) -> tuple[PlantProfile, list[SensorReading]]:
    profile = db.scalar(select(PlantProfile).order_by(PlantProfile.updated_at.desc()).limit(1))
    if profile is None:
        raise HTTPException(
            status_code=409, detail="Set up a plant profile before using the adviser"
        )
    readings = list(
        db.scalars(
            select(SensorReading)
            .where(SensorReading.recorded_at >= datetime.now(UTC) - timedelta(days=7))
            .order_by(SensorReading.recorded_at.desc())
            .limit(500)
        ).all()
    )
    return profile, readings


def _reading_context(readings: list[SensorReading]) -> list[dict[str, object]]:
    return [
        {
            "recorded_at": reading.recorded_at.isoformat(),
            "soil_moisture_percent": reading.soil_moisture,
            "soil_raw_adc": reading.soil_moisture_raw_adc,
            "temperature_c": reading.temperature_c,
            "air_humidity_percent": reading.humidity,
            "light_raw_adc": reading.light_raw_adc,
            "light_relative_percent": reading.light_percent,
            "approx_tds_soil_water_extract_ppm": reading.tds_ppm,
            "deterministic_care_status": assess_plant_health(reading).model_dump(),
        }
        for reading in readings
    ]


@router.get("/status", response_model=AIStatus)
def status() -> AIStatus:
    settings = get_settings()
    groq_ready = bool(settings.groq_api_key and settings.groq_api_key.get_secret_value())
    gemini_ready = bool(settings.gemini_api_key and settings.gemini_api_key.get_secret_value())
    return AIStatus(
        configured=groq_ready or gemini_ready,
        model=settings.groq_model if groq_ready else settings.gemini_model,
        provider="groq" if groq_ready else "gemini" if gemini_ready else None,
    )


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(enforce_rate_limit)])
async def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    profile, readings = _context(db)
    prompt = grounded_prompt(profile, _reading_context(readings), payload.question)
    try:
        answer = await generate(prompt, payload.language)
    except AIUnavailableError as error:
        raise _provider_error(error) from None
    return ChatResponse(answer=answer, language=payload.language)


@router.post(
    "/weekly-summary",
    response_model=WeeklySummaryResponse,
    dependencies=[Depends(enforce_rate_limit)],
)
async def weekly_summary(
    language: str = "en", db: Session = Depends(get_db)
) -> WeeklySummaryResponse:
    if language not in {"en", "bn"}:
        raise HTTPException(status_code=422, detail="language must be 'en' or 'bn'")
    profile, readings = _context(db)
    if not readings:
        empty = (
            "No stored sensor readings are available for this week."
            if language == "en"
            else "এই সপ্তাহের জন্য কোনো সংরক্ষিত সেন্সর রিডিং নেই।"
        )
        return WeeklySummaryResponse(summary=empty, language=language, readings_count=0)
    trends = _reading_context(readings)
    try:
        summary = await generate(
            grounded_prompt(
                profile,
                trends,
                "Summarize the last week's observed conditions and practical next checks.",
            ),
            language,
        )
    except AIUnavailableError as error:
        raise _provider_error(error) from None
    return WeeklySummaryResponse(summary=summary, language=language, readings_count=len(readings))
