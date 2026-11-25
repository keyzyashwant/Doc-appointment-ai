"""Slot repository – queries only."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.availability_slot import AvailabilitySlot
from app.models.enums import SlotStatus


class SlotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, slot_id: int) -> AvailabilitySlot | None:
        return self._session.get(AvailabilitySlot, slot_id)

    def available_for_doctor(
        self,
        doctor_id: int,
        *,
        after: datetime,
        date: datetime | None = None,
        limit: int = 20,
    ) -> list[AvailabilitySlot]:
        stmt = (
            select(AvailabilitySlot)
            .where(
                AvailabilitySlot.doctor_id == doctor_id,
                AvailabilitySlot.status == SlotStatus.available,
                AvailabilitySlot.start_time > after,
            )
            .order_by(AvailabilitySlot.start_time)
            .limit(limit)
        )
        if date is not None:
            # Filter to a specific date (compare date part only)
            from sqlalchemy import func

            stmt = stmt.where(
                func.date(AvailabilitySlot.start_time) == date.date()
            )
        return list(self._session.scalars(stmt))

    def conditional_book(self, slot_id: int) -> bool:
        """Atomically set status to 'booked' only if currently 'available'.

        Returns True if the row was updated.
        """
        result = self._session.execute(
            update(AvailabilitySlot)
            .where(
                AvailabilitySlot.id == slot_id,
                AvailabilitySlot.status == SlotStatus.available,
            )
            .values(status=SlotStatus.booked)
        )
        return result.rowcount == 1  # type: ignore[union-attr]

    def release(self, slot_id: int) -> None:
        """Mark a slot as available again."""
        self._session.execute(
            update(AvailabilitySlot)
            .where(AvailabilitySlot.id == slot_id)
            .values(status=SlotStatus.available)
        )
