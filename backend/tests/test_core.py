"""Tests for the appointment backend core logic.

Uses an in-memory SQLite database for isolation.
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.core.exceptions import DomainError, ErrorCode
from app.models import (
    Appointment,
    AppointmentStatus,
    AvailabilitySlot,
    Doctor,
    SlotStatus,
)
from app.services.appointment_service import AppointmentService
from app.services.phone import normalize_phone


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture()
def db_engine():
    # Use a named in-memory DB shared across connections for concurrency tests
    engine = create_engine(
        "sqlite:///file:test_db?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def session_factory(db_engine):
    """Return a factory for creating new sessions (for concurrency tests)."""
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


def _make_doctor(session: Session) -> Doctor:
    doc = Doctor(name="Dr. Test", speciality="General Medicine", experience_years=5)
    session.add(doc)
    session.flush()
    return doc


def _make_future_slot(session: Session, doctor: Doctor, *, hours_ahead: int = 24) -> AvailabilitySlot:
    start = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    slot = AvailabilitySlot(
        doctor_id=doctor.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=SlotStatus.available,
    )
    session.add(slot)
    session.flush()
    return slot


def _make_past_slot(session: Session, doctor: Doctor) -> AvailabilitySlot:
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    slot = AvailabilitySlot(
        doctor_id=doctor.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=SlotStatus.available,
    )
    session.add(slot)
    session.flush()
    return slot


VALID_PHONE = "9876543210"
VALID_PHONE_2 = "8765432109"


# ── Voice configuration ───────────────────────────────────────────────

def test_voice_settings_require_all_provider_configuration():
    settings = Settings(_env_file=None)

    with pytest.raises(
        RuntimeError,
        match="ELEVENLABS_API_KEY, GOOGLE_API_KEY, GEMINI_MODEL",
    ):
        settings.validate_voice_settings()


# ── Phone normalization ───────────────────────────────────────────────

class TestPhoneNormalization:
    def test_ten_digit(self):
        assert normalize_phone("9876543210") == "+919876543210"

    def test_with_plus91(self):
        assert normalize_phone("+919876543210") == "+919876543210"

    def test_with_91(self):
        assert normalize_phone("919876543210") == "+919876543210"

    def test_with_zero(self):
        assert normalize_phone("09876543210") == "+919876543210"

    def test_with_spaces_dashes(self):
        assert normalize_phone("+91 987-654-3210") == "+919876543210"

    def test_with_parentheses(self):
        assert normalize_phone("(0) 987 654 3210") == "+919876543210"

    def test_invalid_starts_with_5(self):
        with pytest.raises(DomainError) as exc_info:
            normalize_phone("5876543210")
        assert exc_info.value.code == ErrorCode.INVALID_PHONE

    def test_invalid_too_short(self):
        with pytest.raises(DomainError) as exc_info:
            normalize_phone("98765")
        assert exc_info.value.code == ErrorCode.INVALID_PHONE

    def test_invalid_letters(self):
        with pytest.raises(DomainError) as exc_info:
            normalize_phone("abcdefghij")
        assert exc_info.value.code == ErrorCode.INVALID_PHONE


# ── Booking ────────────────────────────────────────────────────────────

class TestBooking:
    def test_successful_book(self, session):
        doc = _make_doctor(session)
        slot = _make_future_slot(session, doc)
        session.commit()

        svc = AppointmentService(session)
        appt = svc.book(slot.id, VALID_PHONE)

        assert appt.status == AppointmentStatus.booked
        assert appt.patient_phone == "+919876543210"
        # Slot must now be booked
        session.refresh(slot)
        assert slot.status == SlotStatus.booked

    def test_double_booking_rejected(self, session):
        """Booking the same slot twice must fail."""
        doc = _make_doctor(session)
        slot = _make_future_slot(session, doc)
        session.commit()

        svc = AppointmentService(session)
        svc.book(slot.id, VALID_PHONE)

        with pytest.raises(DomainError) as exc_info:
            svc.book(slot.id, VALID_PHONE_2)
        assert exc_info.value.code == ErrorCode.SLOT_NOT_AVAILABLE

    def test_second_active_appointment_rejected(self, session):
        """Same phone cannot hold two active appointments."""
        doc = _make_doctor(session)
        slot1 = _make_future_slot(session, doc, hours_ahead=24)
        slot2 = _make_future_slot(session, doc, hours_ahead=48)
        session.commit()

        svc = AppointmentService(session)
        svc.book(slot1.id, VALID_PHONE)

        with pytest.raises(DomainError) as exc_info:
            svc.book(slot2.id, VALID_PHONE)
        assert exc_info.value.code == ErrorCode.ALREADY_HAS_APPOINTMENT

    def test_past_slot_rejected(self, session):
        doc = _make_doctor(session)
        slot = _make_past_slot(session, doc)
        session.commit()

        svc = AppointmentService(session)
        with pytest.raises(DomainError) as exc_info:
            svc.book(slot.id, VALID_PHONE)
        assert exc_info.value.code == ErrorCode.SLOT_NOT_AVAILABLE

    def test_invalid_phone_rejected(self, session):
        doc = _make_doctor(session)
        slot = _make_future_slot(session, doc)
        session.commit()

        svc = AppointmentService(session)
        with pytest.raises(DomainError) as exc_info:
            svc.book(slot.id, "12345")
        assert exc_info.value.code == ErrorCode.INVALID_PHONE

    def test_nonexistent_slot(self, session):
        svc = AppointmentService(session)
        with pytest.raises(DomainError) as exc_info:
            svc.book(99999, VALID_PHONE)
        assert exc_info.value.code == ErrorCode.SLOT_NOT_AVAILABLE


# ── Concurrent booking ────────────────────────────────────────────────

class TestConcurrentBooking:
    def test_two_concurrent_bookings_one_wins(self, session, session_factory):
        """Two threads try to book the same slot; exactly one succeeds."""
        doc = _make_doctor(session)
        slot = _make_future_slot(session, doc)
        session.commit()

        results: list[str] = []  # "ok" or "fail"
        lock = threading.Lock()

        def try_book(phone: str) -> None:
            s = session_factory()
            try:
                svc = AppointmentService(s)
                svc.book(slot.id, phone)
                with lock:
                    results.append("ok")
            except Exception:
                s.rollback()
                with lock:
                    results.append("fail")
            finally:
                s.close()

        t1 = threading.Thread(target=try_book, args=(VALID_PHONE,))
        t2 = threading.Thread(target=try_book, args=(VALID_PHONE_2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results.count("ok") == 1
        assert results.count("fail") == 1


# ── Cancel ─────────────────────────────────────────────────────────────

class TestCancel:
    def test_cancel_releases_slot_and_allows_rebooking(self, session):
        doc = _make_doctor(session)
        slot = _make_future_slot(session, doc)
        session.commit()

        svc = AppointmentService(session)
        appt = svc.book(slot.id, VALID_PHONE)
        svc.cancel(VALID_PHONE, appointment_id=appt.id)

        # Appointment is cancelled
        session.refresh(appt)
        assert appt.status == AppointmentStatus.cancelled

        # Slot is available again
        session.refresh(slot)
        assert slot.status == SlotStatus.available

        # Can rebook the same slot
        appt2 = svc.book(slot.id, VALID_PHONE)
        assert appt2.status == AppointmentStatus.booked

    def test_cancel_without_appointment_id(self, session):
        doc = _make_doctor(session)
        slot = _make_future_slot(session, doc)
        session.commit()

        svc = AppointmentService(session)
        svc.book(slot.id, VALID_PHONE)
        cancelled = svc.cancel(VALID_PHONE)
        assert cancelled.status == AppointmentStatus.cancelled

    def test_cancel_no_appointment_found(self, session):
        svc = AppointmentService(session)
        with pytest.raises(DomainError) as exc_info:
            svc.cancel(VALID_PHONE)
        assert exc_info.value.code == ErrorCode.NO_APPOINTMENT_FOUND
