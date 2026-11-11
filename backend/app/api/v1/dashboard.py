"""Public read-only dashboard endpoints for current and historical readings."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.modules.sensors import repository
from app.modules.sensors.care_rules import assess_plant_health
from app.modules.sensors.schemas import DashboardLatest, SensorReadingOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/latest", response_model=DashboardLatest)
def latest_reading(db: Session = Depends(get_db)) -> DashboardLatest:
    """Return the latest real reading, connection freshness, and deterministic care status."""

    reading = repository.get_latest_reading(db)
    now = datetime.now(UTC)
    last_updated = reading.recorded_at if reading else None
    if reading is None:
        connection = "never_connected"
    else:
        recorded_at = reading.recorded_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)
        online_window = timedelta(seconds=get_settings().device_online_window_seconds)
        connection = "online" if now - recorded_at <= online_window else "offline"

    return DashboardLatest(
        reading=SensorReadingOut.model_validate(reading) if reading else None,
        connection_status=connection,
        last_updated=last_updated,
        plant_health=assess_plant_health(reading),
    )


@router.get("/readings", response_model=list[SensorReadingOut])
def historical_readings(
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[SensorReadingOut]:
    """Return stored measurements only, newest first, with bounded query size."""

    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must be earlier than or equal to until")
    readings = repository.list_readings(db, since=since, until=until, limit=limit)
    return [SensorReadingOut.model_validate(reading) for reading in readings]
