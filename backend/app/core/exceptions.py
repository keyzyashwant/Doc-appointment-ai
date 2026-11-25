"""Domain exceptions with machine-readable codes."""

from enum import Enum


class ErrorCode(str, Enum):
    SLOT_NOT_AVAILABLE = "SLOT_NOT_AVAILABLE"
    INVALID_PHONE = "INVALID_PHONE"
    ALREADY_HAS_APPOINTMENT = "ALREADY_HAS_APPOINTMENT"
    NO_APPOINTMENT_FOUND = "NO_APPOINTMENT_FOUND"
    DOCTOR_NOT_FOUND = "DOCTOR_NOT_FOUND"


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str, code: ErrorCode | None = None) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class DomainError(AppError):
    """Raised by services for business-rule violations."""

    status_code = 422

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message, code=code)
