from datetime import datetime

from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CallSessionStatus


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CallSessionStatus] = mapped_column(
        Enum(CallSessionStatus, native_enum=False, length=20),
        nullable=False,
        default=CallSessionStatus.active,
    )
