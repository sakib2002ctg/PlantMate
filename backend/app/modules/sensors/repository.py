"""Database operations for timestamped sensor readings."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sensor_reading import SensorReading
from app.modules.sensors.schemas import SensorReadingCreate


def create_reading(db: Session, payload: SensorReadingCreate) -> SensorReading:
    """Persist a validated reading and return it with its server timestamp."""

    reading = SensorReading(**payload.model_dump())
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def get_latest_reading(db: Session) -> SensorReading | None:
    return db.scalar(select(SensorReading).order_by(SensorReading.recorded_at.desc()).limit(1))


def list_readings(
    db: Session, *, since: datetime | None, until: datetime | None, limit: int
) -> list[SensorReading]:
    statement = select(SensorReading)
    if since is not None:
        statement = statement.where(SensorReading.recorded_at >= since)
    if until is not None:
        statement = statement.where(SensorReading.recorded_at <= until)
    return list(
        db.scalars(statement.order_by(SensorReading.recorded_at.desc()).limit(limit)).all()
    )
