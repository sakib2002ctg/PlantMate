"""Timestamped sensor values received from a PlantMate device."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.sensors.calibration import relative_light_percent


class SensorReading(Base):
    """One validated ESP32 measurement set, timestamped on the API server."""

    __tablename__ = "sensor_readings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    soil_moisture: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_moisture_raw_adc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    light_lux: Mapped[float | None] = mapped_column(Float, nullable=True)
    light_raw_adc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tds_ppm: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    @property
    def light_percent(self) -> float | None:
        """Relative calibrated brightness derived without changing stored ADC."""

        if self.light_raw_adc is None:
            return None
        return relative_light_percent(self.light_raw_adc)
