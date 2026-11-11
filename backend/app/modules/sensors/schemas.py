"""Validated API contracts for device readings and dashboard data."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SensorReadingCreate(BaseModel):
    """ESP32 payload. The server assigns the authoritative recorded timestamp."""

    model_config = ConfigDict(allow_inf_nan=False)

    device_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    soil_moisture: float | None = Field(default=None, ge=0, le=100)
    soil_moisture_raw_adc: int | None = Field(default=None, ge=0, le=4095)
    temperature_c: float = Field(ge=-40, le=85)
    humidity: float = Field(ge=0, le=100)
    light_lux: float | None = Field(default=None, ge=0, le=200_000)
    light_raw_adc: int | None = Field(default=None, ge=0, le=4095)
    tds_ppm: float = Field(ge=0, le=10_000)

    @model_validator(mode="after")
    def require_calibrated_or_raw_soil_and_light(self) -> SensorReadingCreate:
        """Require a real calibrated or raw value for both analog sensors."""

        if self.soil_moisture is None and self.soil_moisture_raw_adc is None:
            raise ValueError("soil_moisture or soil_moisture_raw_adc is required")
        if self.light_lux is None and self.light_raw_adc is None:
            raise ValueError("light_lux or light_raw_adc is required")
        return self


class SensorReadingOut(BaseModel):
    """Stored measurement returned by public read-only dashboard routes."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: str
    soil_moisture: float | None
    soil_moisture_raw_adc: int | None
    temperature_c: float
    humidity: float
    light_lux: float | None
    light_raw_adc: int | None
    light_percent: float | None
    tds_ppm: float
    recorded_at: datetime


class IngestionResult(BaseModel):
    accepted: bool = True
    reading: SensorReadingOut


class CareStatus(BaseModel):
    status: str
    message: str


class DashboardLatest(BaseModel):
    reading: SensorReadingOut | None
    connection_status: str
    last_updated: datetime | None
    plant_health: CareStatus
