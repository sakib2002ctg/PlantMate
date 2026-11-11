"""Authenticated device-only sensor ingestion route."""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.modules.sensors.repository import create_reading
from app.modules.sensors.schemas import IngestionResult, SensorReadingCreate

router = APIRouter(prefix="/ingestion", tags=["device ingestion"])


def verify_device_key(x_device_key: str | None = Header(default=None)) -> None:
    """Require the configured device key and compare it without timing leaks."""

    expected = get_settings().device_ingestion_key
    if expected is None or not expected.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device ingestion is not configured",
        )
    if x_device_key is None or not secrets.compare_digest(
        x_device_key, expected.get_secret_value()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device key")


@router.post("/readings", response_model=IngestionResult, status_code=status.HTTP_201_CREATED)
def ingest_reading(
    payload: SensorReadingCreate,
    _authorized: None = Depends(verify_device_key),
    db: Session = Depends(get_db),
) -> IngestionResult:
    """Accept a validated sensor packet from an authorized device."""

    reading = create_reading(db, payload)
    return IngestionResult(reading=reading)
