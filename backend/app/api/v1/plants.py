"""Public single-garden plant profile API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.plant_profile import PlantProfile
from app.modules.plants.schemas import PlantProfileInput, PlantProfileOut

router = APIRouter(prefix="/plants", tags=["plant profile"])


@router.get("/profile", response_model=PlantProfileOut)
def get_profile(db: Session = Depends(get_db)) -> PlantProfileOut:
    profile = db.scalar(select(PlantProfile).order_by(PlantProfile.updated_at.desc()).limit(1))
    if profile is None:
        raise HTTPException(status_code=404, detail="Plant profile has not been set up")
    return PlantProfileOut.model_validate(profile)


@router.put("/profile", response_model=PlantProfileOut)
def save_profile(
    payload: PlantProfileInput, db: Session = Depends(get_db)
) -> PlantProfileOut:
    profile = db.scalar(select(PlantProfile).order_by(PlantProfile.updated_at.desc()).limit(1))
    if profile is None:
        profile = PlantProfile(**payload.model_dump())
        db.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return PlantProfileOut.model_validate(profile)
