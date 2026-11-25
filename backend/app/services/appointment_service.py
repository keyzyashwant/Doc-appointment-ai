"""Appointment service – book and cancel with full business rules."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.events import DomainEvent, event_bus
from app.core.exceptions import DomainError, ErrorCode
from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus
from app.repositories.appointment_repo import AppointmentRepository
from app.repositories.slot_repo import SlotRepository
from app.services.phone import normalize_phone


class AppointmentService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._appointments = AppointmentRepository(session)
        self._slots = SlotRepository(session)

    # ── book ───────────────────────────────────────────────────────────
    def book(self, slot_id: int, raw_phone: str) -> Appointment:
        phone = normalize_phone(raw_phone)

        # 1. Slot must exist
        slot = self._slots.get_by_id(slot_id)
        if slot is None:
            raise DomainError(ErrorCode.SLOT_NOT_AVAILABLE, "Slot does not exist.")

        # 2. Slot must be in the future
        slot_time = slot.start_time
        if slot_time.tzinfo is None:
            slot_time = slot_time.replace(tzinfo=timezone.utc)
        if slot_time <= datetime.now(timezone.utc):
            raise DomainError(ErrorCode.SLOT_NOT_AVAILABLE, "Cannot book a slot in the past.")

        # 3. Phone must have no active appointment
        if self._appointments.active_for_phone(phone):
            raise DomainError(
                ErrorCode.ALREADY_HAS_APPOINTMENT,
                "You already have an active appointment. Cancel it first.",
            )

        # 4. Atomic conditional UPDATE (status='available' → 'booked')
        if not self._slots.conditional_book(slot_id):
            raise DomainError(ErrorCode.SLOT_NOT_AVAILABLE, "Slot is no longer available.")

        # 5. Insert appointment
        appointment = self._appointments.insert(
            Appointment(
                doctor_id=slot.doctor_id,
                slot_id=slot.id,
                patient_phone=phone,
                status=AppointmentStatus.booked,
            )
        )

        self._session.commit()

        # Publish event after commit
        _publish_event(
            "appointment.booked",
            {
                "appointment_id": appointment.id,
                "doctor_id": appointment.doctor_id,
                "slot_id": appointment.slot_id,
                "patient_phone": appointment.patient_phone,
            },
        )

        return appointment

    # ── cancel ─────────────────────────────────────────────────────────
    def cancel(self, raw_phone: str, appointment_id: int | None = None) -> Appointment:
        phone = normalize_phone(raw_phone)

        if appointment_id is not None:
            appointment = self._appointments.get_by_id(appointment_id)
            if (
                appointment is None
                or appointment.patient_phone != phone
                or appointment.status != AppointmentStatus.booked
            ):
                raise DomainError(
                    ErrorCode.NO_APPOINTMENT_FOUND,
                    "No matching active appointment found.",
                )
        else:
            appointment = self._appointments.active_for_phone(phone)
            if appointment is None:
                raise DomainError(
                    ErrorCode.NO_APPOINTMENT_FOUND,
                    "No active appointment found for this phone.",
                )

        # Mark cancelled + release the slot
        self._appointments.cancel(appointment)
        self._slots.release(appointment.slot_id)

        self._session.commit()

        _publish_event(
            "appointment.cancelled",
            {
                "appointment_id": appointment.id,
                "doctor_id": appointment.doctor_id,
                "slot_id": appointment.slot_id,
                "patient_phone": appointment.patient_phone,
            },
        )

        return appointment

    # ── list ───────────────────────────────────────────────────────────
    def list_all(self, *, booked_only: bool = False) -> list[Appointment]:
        return self._appointments.list_all(booked_only=booked_only)


def _publish_event(topic: str, data: dict) -> None:
    """Publish committed service events to subscribers on their event loops."""
    event = DomainEvent(topic=topic, data=data)
    event_bus.publish_threadsafe(event)
