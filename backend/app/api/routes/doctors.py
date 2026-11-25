"""GET /api/doctors – list doctors with available slots."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import DoctorOut
from app.services.availability_service import AvailabilityService

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
def list_doctors(
    doctor_name: str | None = Query(None),
    speciality: str | None = Query(None),
    date: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[DoctorOut]:
    svc = AvailabilityService(session)
    return svc.list_doctors(
        doctor_name=doctor_name,
        speciality=speciality,
        date=date,
        limit=limit,
    )
