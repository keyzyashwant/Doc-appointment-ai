"""Doctor repository – queries only."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.doctor import Doctor


class DoctorRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[Doctor]:
        return list(self._session.scalars(select(Doctor).order_by(Doctor.name)))

    def get_by_id(self, doctor_id: int) -> Doctor | None:
        return self._session.get(Doctor, doctor_id)

    def search_by_name(self, name: str) -> list[Doctor]:
        """Case-insensitive LIKE search (fuzzy)."""
        pattern = f"%{name}%"
        return list(
            self._session.scalars(
                select(Doctor).where(Doctor.name.ilike(pattern))
            )
        )

    def search_by_speciality(self, speciality: str) -> list[Doctor]:
        pattern = f"%{speciality}%"
        return list(
            self._session.scalars(
                select(Doctor).where(Doctor.speciality.ilike(pattern))
            )
        )
