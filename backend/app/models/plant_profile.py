"""Single public garden profile associated with the sensor device."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlantProfile(Base):
    """Plant profile for the public single-garden demonstration dashboard."""

    __tablename__ = "plant_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    plant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str] = mapped_column(String(120), nullable=False)
    plant_type: Mapped[str] = mapped_column(String(80), nullable=False, default="houseplant")
    planting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
