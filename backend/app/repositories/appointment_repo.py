"""Appointment repository – queries only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus


class AppointmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, appointment_id: int) -> Appointment | None:
        return self._session.get(Appointment, appointment_id)

    def active_for_phone(self, phone: str) -> Appointment | None:
        """Return the single active (booked) appointment for a phone, or None."""
        return self._session.scalar(
            select(Appointment).where(
                Appointment.patient_phone == phone,
                Appointment.status == AppointmentStatus.booked,
            )
        )

    def list_all(self, *, booked_only: bool = False) -> list[Appointment]:
        stmt = select(Appointment).order_by(Appointment.created_at.desc())
        if booked_only:
            stmt = stmt.where(Appointment.status == AppointmentStatus.booked)
        return list(self._session.scalars(stmt))

    def insert(self, appointment: Appointment) -> Appointment:
        self._session.add(appointment)
        self._session.flush()
        return appointment

    def cancel(self, appointment: Appointment) -> None:
        appointment.status = AppointmentStatus.cancelled
        self._session.flush()
