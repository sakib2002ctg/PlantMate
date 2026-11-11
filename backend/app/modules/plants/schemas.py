"""Validated plant profile contracts."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlantProfileInput(BaseModel):
    plant_name: str = Field(min_length=1, max_length=100)
    species: str = Field(min_length=1, max_length=120)
    plant_type: str = Field(default="houseplant", min_length=1, max_length=80)
    planting_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    device_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")


class PlantProfileOut(PlantProfileInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    updated_at: datetime
