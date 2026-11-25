"""REST routes for appointments: list, book, cancel."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import AppointmentOut, BookRequest, CancelRequest
from app.services.appointment_service import AppointmentService

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def _to_out(appt) -> AppointmentOut:
    return AppointmentOut(
        id=appt.id,
        doctor_id=appt.doctor_id,
        slot_id=appt.slot_id,
        patient_phone=appt.patient_phone,
        status=appt.status.value if hasattr(appt.status, "value") else appt.status,
        created_at=appt.created_at,
        doctor_name=appt.doctor.name if appt.doctor else "",
        slot_start=appt.slot.start_time if appt.slot else None,
        slot_end=appt.slot.end_time if appt.slot else None,
    )


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    session: Session = Depends(get_db),
) -> list[AppointmentOut]:
    svc = AppointmentService(session)
    appointments = svc.list_all()
    return [_to_out(a) for a in appointments]


@router.post("", response_model=AppointmentOut, status_code=201)
def book_appointment(
    body: BookRequest,
    session: Session = Depends(get_db),
) -> AppointmentOut:
    svc = AppointmentService(session)
    appt = svc.book(body.slot_id, body.phone)
    return _to_out(appt)


@router.delete("/{appointment_id}", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    body: CancelRequest,
    session: Session = Depends(get_db),
) -> AppointmentOut:
    svc = AppointmentService(session)
    appt = svc.cancel(body.phone, appointment_id=appointment_id)
    return _to_out(appt)
