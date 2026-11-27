"""Tests for the appointment backend core logic.

Uses an in-memory SQLite database for isolation.
"""

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.core.exceptions import DomainError, ErrorCode
from app.core import specialities as speciality_catalog
from app.voice.tools import (
    _check_doctor_availability,
    book_appointment,
    check_doctor_availability,
    configure_speciality_catalog,
)
from app.voice.pipeline import _system_prompt
from app.models import (
    Appointment,
    AppointmentStatus,
    AvailabilitySlot,
    Doctor,
    SlotStatus,
)
from app.services.appointment_service import AppointmentService
from app.services.phone import normalize_phone
from app.services.availability_service import AvailabilityService


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


# ── Availability ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("spoken_term", "speciality"),
    [
        ("cardiologist", "Cardiology"),
        ("pediatrician", "Pediatrics"),
    ],
)
def test_specialist_term_matches_catalog_speciality(session, spoken_term, speciality):
    doctor = Doctor(
        name="Dr. Cardiology Test",
        speciality=speciality,
        experience_years=5,
    )
    session.add(doctor)
    session.flush()
    _make_future_slot(session, doctor)
    session.commit()

    results = AvailabilityService(session).list_doctors(speciality=spoken_term)

    assert [result.name for result in results] == ["Dr. Cardiology Test"]


@pytest.mark.parametrize("spoken_term", ["heart doctor", "nonsenseword"])
def test_unmatched_speciality_returns_valid_catalog(
    session_factory, monkeypatch, spoken_term
):
    with session_factory() as session:
        session.add_all(
            [
                Doctor(name="Dr. Heart", speciality="Cardiology", experience_years=5),
                Doctor(name="Dr. General", speciality="General Medicine", experience_years=5),
            ]
        )
        session.commit()

    monkeypatch.setattr("app.voice.tools.SessionLocal", session_factory)

    result = _check_doctor_availability(None, spoken_term, None)

    assert result["ok"] is False
    assert result["code"] == "SPECIALITY_NOT_FOUND"
    assert result["data"] == {"valid_specialities": ["Cardiology", "General Medicine"]}


def test_voice_prompts_include_exact_speciality_catalog(monkeypatch):
    specialities = ("Cardiology", "Pediatrics")
    mapping_instruction = (
        "Map what the caller says (cardiologist, heart doctor, kids doctor) "
        "to one of these names before calling the tool."
    )
    monkeypatch.setattr(speciality_catalog, "_SPECIALITY_CATALOG", specialities)
    monkeypatch.setattr(
        check_doctor_availability,
        "__doc__",
        check_doctor_availability.__doc__,
    )
    configure_speciality_catalog(specialities)

    system_prompt = _system_prompt()
    tool_description = check_doctor_availability.__doc__

    assert "Exact DB specialities: Cardiology, Pediatrics." in system_prompt
    assert mapping_instruction in system_prompt
    assert "Available specialities (exact DB names): Cardiology, Pediatrics." in tool_description
    assert mapping_instruction in tool_description


class _ToolParams:
    def __init__(self):
        self.result = None

    async def result_callback(self, result):
        self.result = result


def test_book_tool_accepts_phone_confirmed_true(monkeypatch):
    monkeypatch.setattr(
        "app.voice.tools._book_appointment",
        lambda slot_id, phone_number: {"ok": True, "code": "SUCCESS", "data": {}},
    )
    params = _ToolParams()

    asyncio.run(
        book_appointment(
            params,
            slot_id=123,
            phone_number=VALID_PHONE,
            phone_confirmed=True,
        )
    )

    assert params.result["ok"] is True


def test_book_tool_rejects_phone_confirmed_false(monkeypatch):
    monkeypatch.setattr(
        "app.voice.tools._book_appointment",
        lambda *_args: pytest.fail("booking service must not be called"),
    )
    params = _ToolParams()

    asyncio.run(
        book_appointment(
            params,
            slot_id=123,
            phone_number=VALID_PHONE,
            phone_confirmed=False,
        )
    )

    assert params.result["ok"] is False
    assert params.result["code"] == "PHONE_NOT_CONFIRMED"


def test_availability_excludes_slots_before_current_ist_time(session, monkeypatch):
    clinic_tz = ZoneInfo("Asia/Kolkata")
    now = datetime(2026, 11, 27, 10, 7, tzinfo=clinic_tz)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz == clinic_tz
            return now

    monkeypatch.setattr("app.services.availability_service.datetime", FrozenDateTime)
    doctor = _make_doctor(session)
    for hour, minute in [(9, 0), (9, 30), (10, 30)]:
        start = datetime(2026, 11, 27, hour, minute, tzinfo=clinic_tz)
        session.add(
            AvailabilitySlot(
                doctor_id=doctor.id,
                start_time=start,
                end_time=start + timedelta(minutes=30),
                status=SlotStatus.available,
            )
        )
    session.commit()

    results = AvailabilityService(session).list_doctors()

    assert [slot.start_time.hour for slot in results[0].available_slots] == [10]
    assert [slot.start_time.minute for slot in results[0].available_slots] == [30]


# ── Voice configuration ───────────────────────────────────────────────

def test_voice_settings_require_all_provider_configuration():
    settings = Settings(_env_file=None)

    with pytest.raises(
        RuntimeError,
        match="ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, GOOGLE_API_KEY, GEMINI_MODEL",
    ):
        settings.validate_voice_settings()


def test_tts_model_defaults_to_flash_and_voice_id_is_required():
    settings = Settings(_env_file=None, elevenlabs_voice_id="voice-id")

    assert settings.elevenlabs_tts_model == "eleven_flash_v2_5"
    with pytest.raises(RuntimeError, match="ELEVENLABS_VOICE_ID"):
        Settings(_env_file=None).validate_voice_settings()


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
