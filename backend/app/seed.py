from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Appointment, AppointmentStatus, AvailabilitySlot, Doctor, SlotStatus

logger = get_logger(__name__)

CLINIC_ZONE = ZoneInfo("Asia/Kolkata")
SLOT_MINUTES = 30
DAY_START = time(9, 0)
DAY_END = time(17, 0)
HORIZON_DAYS = 7

DOCTORS: list[dict[str, str | int]] = [
    {"name": "Dr. Ananya Sharma", "speciality": "Cardiology", "experience_years": 12},
    {"name": "Dr. Rohan Mehta", "speciality": "Dermatology", "experience_years": 8},
    {"name": "Dr. Priya Nair", "speciality": "Pediatrics", "experience_years": 10},
    {"name": "Dr. Vikram Iyer", "speciality": "Orthopedics", "experience_years": 15},
    {"name": "Dr. Meera Kapoor", "speciality": "General Medicine", "experience_years": 9},
    {"name": "Dr. Arjun Desai", "speciality": "Cardiology", "experience_years": 7},
]

# doctor index, day offset, hour, minute, phone
PREBOOKED: list[tuple[int, int, int, int, str]] = [
    (0, 1, 10, 0, "+919810000001"),
    (1, 1, 11, 30, "+919810000002"),
    (2, 2, 9, 30, "+919810000003"),
    (4, 3, 16, 0, "+919810000004"),
]


def _clinic_days(now: datetime | None = None) -> list[datetime]:
    current = now or datetime.now(CLINIC_ZONE)
    start_date = current.astimezone(CLINIC_ZONE).date()
    return [
        datetime.combine(start_date + timedelta(days=offset), DAY_START, tzinfo=CLINIC_ZONE)
        for offset in range(HORIZON_DAYS)
    ]


def _slot_bounds(day_start: datetime) -> list[tuple[datetime, datetime]]:
    slots: list[tuple[datetime, datetime]] = []
    cursor = day_start
    day_end = datetime.combine(day_start.date(), DAY_END, tzinfo=CLINIC_ZONE)
    while cursor < day_end:
        slot_end = cursor + timedelta(minutes=SLOT_MINUTES)
        slots.append((cursor, slot_end))
        cursor = slot_end
    return slots


def seed_database(session: Session, now: datetime | None = None) -> None:
    existing = session.scalar(select(func.count()).select_from(Doctor))
    if existing:
        logger.info("Seed skipped; %s doctors already present", existing)
        return

    doctors = [
        Doctor(
            name=str(spec["name"]),
            speciality=str(spec["speciality"]),
            experience_years=int(spec["experience_years"]),
        )
        for spec in DOCTORS
    ]
    session.add_all(doctors)
    session.flush()

    prebooked = {
        (doctor_index, day_offset, hour, minute): phone
        for doctor_index, day_offset, hour, minute, phone in PREBOOKED
    }
    days = _clinic_days(now)
    created_at = datetime.now(timezone.utc)
    booked_slots: list[tuple[AvailabilitySlot, int, str]] = []

    for doctor_index, doctor in enumerate(doctors):
        for day_offset, day_start in enumerate(days):
            for start, end in _slot_bounds(day_start):
                local_start = start.astimezone(CLINIC_ZONE)
                phone = prebooked.get(
                    (doctor_index, day_offset, local_start.hour, local_start.minute)
                )
                slot = AvailabilitySlot(
                    doctor_id=doctor.id,
                    start_time=start,
                    end_time=end,
                    status=SlotStatus.booked if phone else SlotStatus.available,
                )
                session.add(slot)
                if phone:
                    booked_slots.append((slot, doctor.id, phone))

    session.flush()
    session.add_all(
        Appointment(
            doctor_id=doctor_id,
            slot_id=slot.id,
            patient_phone=phone,
            status=AppointmentStatus.booked,
            created_at=created_at,
        )
        for slot, doctor_id, phone in booked_slots
    )

    logger.info(
        "Seeded %s doctors, %s days of 30-minute slots, %s pre-booked appointments",
        len(doctors),
        len(days),
        len(prebooked),
    )
