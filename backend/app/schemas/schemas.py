"""Pydantic schemas for the REST API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ── Slots ──────────────────────────────────────────────────────────────
class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    status: str


# ── Doctors ────────────────────────────────────────────────────────────
class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    speciality: str
    experience_years: int
    available_slots: list[SlotOut] = []


# ── Appointments ───────────────────────────────────────────────────────
class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    slot_id: int
    patient_phone: str
    status: str
    created_at: datetime
    doctor_name: str = ""
    slot_start: datetime | None = None
    slot_end: datetime | None = None


# ── Requests ───────────────────────────────────────────────────────────
class BookRequest(BaseModel):
    slot_id: int
    phone: str


class CancelRequest(BaseModel):
    phone: str
    appointment_id: int | None = None
