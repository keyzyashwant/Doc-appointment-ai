import enum


class SlotStatus(str, enum.Enum):
    available = "available"
    booked = "booked"


class AppointmentStatus(str, enum.Enum):
    booked = "booked"
    cancelled = "cancelled"


class CallSessionStatus(str, enum.Enum):
    active = "active"
    ended = "ended"
