"""Availability service – finding doctors and their free slots."""

from difflib import get_close_matches
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.models.doctor import Doctor
from app.models.enums import SlotStatus
from app.repositories.doctor_repo import DoctorRepository
from app.repositories.slot_repo import SlotRepository
from app.schemas import DoctorOut, SlotOut

CLINIC_TZ = ZoneInfo("Asia/Kolkata")


def _normalize_speciality(value: str) -> str:
    normalized = " ".join(value.casefold().split())
    if normalized.endswith("ologist"):
        return normalized[:-7] + "ology"
    if normalized.endswith("ician"):
        return normalized[:-5] + "ics"
    return normalized


class AvailabilityService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._doctors = DoctorRepository(session)
        self._slots = SlotRepository(session)

    def list_doctors(
        self,
        *,
        doctor_name: str | None = None,
        speciality: str | None = None,
        date: datetime | None = None,
        limit: int = 20,
    ) -> list[DoctorOut]:
        """Return doctors (optionally filtered) with their available future slots."""
        if doctor_name:
            doctors = self._doctors.search_by_name(doctor_name)
        elif speciality:
            specialities = self._doctors.list_specialities()
            normalized_speciality = _normalize_speciality(speciality)
            normalized_catalog = {
                _normalize_speciality(item): item for item in specialities
            }
            matches = get_close_matches(
                normalized_speciality,
                list(normalized_catalog),
                n=1,
                cutoff=0.6,
            )
            if not matches:
                raise DomainError(
                    ErrorCode.SPECIALITY_NOT_FOUND,
                    "No matching speciality was found.",
                    data={"valid_specialities": specialities},
                )
            search_term = normalized_catalog[matches[0]]
            doctors = self._doctors.search_by_speciality(search_term)
        else:
            doctors = self._doctors.list_all()

        if not doctors and (doctor_name or speciality):
            raise DomainError(
                ErrorCode.DOCTOR_NOT_FOUND,
                f"No doctors found matching the search criteria.",
            )

        now = datetime.now(CLINIC_TZ)
        result: list[DoctorOut] = []
        for doc in doctors:
            slots = self._slots.available_for_doctor(
                doc.id, after=now, date=date, limit=limit
            )
            result.append(self._to_doctor_out(doc, slots))
        return result

    # ── helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _to_doctor_out(doc: Doctor, available_slots: list) -> DoctorOut:
        return DoctorOut(
            id=doc.id,
            name=doc.name,
            speciality=doc.speciality,
            experience_years=doc.experience_years,
            available_slots=[
                SlotOut(
                    id=s.id,
                    doctor_id=s.doctor_id,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    status=s.status.value if isinstance(s.status, SlotStatus) else s.status,
                )
                for s in available_slots
            ],
        )
