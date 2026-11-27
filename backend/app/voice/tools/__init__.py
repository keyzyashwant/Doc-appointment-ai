"""Voice tools exposed to the LLM. Services are the only business-logic boundary."""

import asyncio
from datetime import datetime

from app.core.database import SessionLocal
from app.core.exceptions import DomainError
from app.core.logging import get_logger
from app.services.appointment_service import AppointmentService
from app.services.availability_service import AvailabilityService

logger = get_logger(__name__)

def _ok(message: str, data: dict | None = None) -> dict:
    return {"ok": True, "code": "SUCCESS", "message": message, "data": data or {}}


def _fail(code: str, message: str, data: dict | None = None) -> dict:
    return {"ok": False, "code": code, "message": message, "data": data or {}}


def _domain_failure(exc: DomainError) -> dict:
    return _fail(
        exc.code.value if exc.code else "ERROR",
        exc.message,
        getattr(exc, "data", None),
    )


def _redact_log_values(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key.lower() in {"phone", "phone_number", "patient_phone"}
            else _redact_log_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_log_values(item) for item in value]
    return value


async def _send_result(params, result: dict, tool_name: str) -> None:
    logger.info("Voice tool result %s: %s", tool_name, _redact_log_values(result))
    if result.get("ok") is False:
        logger.info(
            "Voice service error in %s: code=%s message=%s",
            tool_name,
            result.get("code"),
            result.get("message"),
        )
    try:
        await params.result_callback(result)
    except Exception:
        logger.exception("Voice tool result callback failed")


def _check_doctor_availability(
    doctor_name: str | None, speciality: str | None, date: str | None
) -> dict:
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d") if date else None
        with SessionLocal() as session:
            doctors = AvailabilityService(session).list_doctors(
                doctor_name=doctor_name,
                speciality=speciality,
                date=parsed_date,
                limit=3,
            )

        doctors_data = [
            {
                "doctor_id": doctor.id,
                "name": doctor.name,
                "speciality": doctor.speciality,
                "experience_years": doctor.experience_years,
                "available_slots": [
                    {
                        "slot_id": slot.id,
                        "start_time": slot.start_time.isoformat(),
                        "end_time": slot.end_time.isoformat(),
                    }
                    for slot in doctor.available_slots
                ],
            }
            for doctor in doctors
        ]
        return _ok(
            f"Found {len(doctors_data)} doctor(s) with available slots.",
            {"doctors": doctors_data},
        )
    except ValueError:
        return _fail("INVALID_DATE", "Date must use YYYY-MM-DD format.")
    except DomainError as exc:
        return _domain_failure(exc)
    except Exception:
        logger.exception("check_doctor_availability failed")
        return _fail("ERROR", "Unable to check availability right now.")


async def check_doctor_availability(
    params,
    doctor_name: str | None = None,
    speciality: str | None = None,
    date: str | None = None,
):
    """Find available doctors and up to three upcoming slots per doctor.

    Args:
        doctor_name: Optional part or full doctor name.
        speciality: Optional medical speciality.
        date: Optional date in YYYY-MM-DD format.
    """
    logger.info(
        "Voice tool call check_doctor_availability args=%s",
        {"doctor_name": doctor_name, "speciality": speciality, "date": date},
    )
    try:
        result = await asyncio.to_thread(
            _check_doctor_availability, doctor_name, speciality, date
        )
    except Exception:
        logger.exception("check_doctor_availability failed")
        result = _fail("ERROR", "Unable to check availability right now.")
    await _send_result(params, result, "check_doctor_availability")


def configure_speciality_catalog(specialities: tuple[str, ...]) -> None:
    names = ", ".join(specialities) or "No specialities are currently available"
    check_doctor_availability.__doc__ = f"""Find available doctors and up to three upcoming slots per doctor.

Available specialities (exact DB names): {names}.
Map what the caller says (cardiologist, heart doctor, kids doctor) to one of these names before calling the tool.

Args:
    doctor_name: Optional part or full doctor name.
    speciality: Optional medical speciality; use one of the exact names listed above.
    date: Optional date in YYYY-MM-DD format.
"""


def _book_appointment(slot_id: int, phone_number: str) -> dict:
    try:
        with SessionLocal() as session:
            appointment = AppointmentService(session).book(slot_id, phone_number)
            return _ok(
                "Appointment booked successfully.",
                {
                    "appointment_id": appointment.id,
                    "doctor_name": appointment.doctor.name if appointment.doctor else "",
                    "slot_start": appointment.slot.start_time.isoformat()
                    if appointment.slot
                    else "",
                    "slot_end": appointment.slot.end_time.isoformat()
                    if appointment.slot
                    else "",
                    "phone": appointment.patient_phone,
                },
            )
    except DomainError as exc:
        return _domain_failure(exc)
    except Exception:
        logger.exception("book_appointment failed")
        return _fail("ERROR", "Unable to book the appointment right now.")


async def book_appointment(
    params, slot_id: int, phone_number: str, phone_confirmed: bool
):
    """Book a slot after the caller verbally confirms their phone number.

    Args:
        slot_id: The selected slot ID from availability results.
        phone_number: The caller's confirmed Indian mobile number.
        phone_confirmed: True only after reading each digit aloud and receiving a fresh yes.
    """
    logger.info(
        "Voice tool call book_appointment args=%s",
        _redact_log_values(
            {
                "slot_id": slot_id,
                "phone_number": phone_number,
                "phone_confirmed": phone_confirmed,
            }
        ),
    )
    if phone_confirmed is not True:
        result = _fail(
            "PHONE_NOT_CONFIRMED",
            "Read the phone number back digit by digit and get a new yes before booking.",
        )
    else:
        try:
            result = await asyncio.to_thread(_book_appointment, slot_id, phone_number)
        except Exception:
            logger.exception("book_appointment failed")
            result = _fail("ERROR", "Unable to book the appointment right now.")
    await _send_result(params, result, "book_appointment")


def _cancel_appointment(phone_number: str, appointment_id: int | None) -> dict:
    try:
        with SessionLocal() as session:
            appointment = AppointmentService(session).cancel(
                phone_number, appointment_id=appointment_id
            )
            return _ok(
                "Appointment cancelled successfully.",
                {
                    "appointment_id": appointment.id,
                    "doctor_name": appointment.doctor.name if appointment.doctor else "",
                    "phone": appointment.patient_phone,
                },
            )
    except DomainError as exc:
        return _domain_failure(exc)
    except Exception:
        logger.exception("cancel_appointment failed")
        return _fail("ERROR", "Unable to cancel the appointment right now.")


async def cancel_appointment(
    params,
    phone_number: str,
    phone_confirmed: bool,
    appointment_id: int | None = None,
):
    """Cancel the caller's active appointment after phone confirmation.

    Args:
        phone_number: The caller's confirmed Indian mobile number.
        phone_confirmed: True only after reading each digit aloud and receiving a fresh yes.
        appointment_id: Optional ID of the appointment to cancel.
    """
    logger.info(
        "Voice tool call cancel_appointment args=%s",
        _redact_log_values(
            {
                "phone_number": phone_number,
                "phone_confirmed": phone_confirmed,
                "appointment_id": appointment_id,
            }
        ),
    )
    if phone_confirmed is not True:
        result = _fail(
            "PHONE_NOT_CONFIRMED",
            "Read the phone number back digit by digit and get a new yes before cancelling.",
        )
    else:
        try:
            result = await asyncio.to_thread(
                _cancel_appointment, phone_number, appointment_id
            )
        except Exception:
            logger.exception("cancel_appointment failed")
            result = _fail("ERROR", "Unable to cancel the appointment right now.")
    await _send_result(params, result, "cancel_appointment")


ALL_TOOLS = [check_doctor_availability, book_appointment, cancel_appointment]
