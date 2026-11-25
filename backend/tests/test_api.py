from contextlib import asynccontextmanager

import app.models  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import create_app
from app.seed import seed_database


@asynccontextmanager
async def _empty_lifespan(_app):
    yield


def test_list_routes_and_appointment_event_websocket():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as session:
        seed_database(session)
        session.commit()

    def override_get_db():
        with session_factory() as session:
            yield session

    app = create_app()
    app.router.lifespan_context = _empty_lifespan
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            doctors_response = client.get("/api/doctors")
            appointments_response = client.get("/api/appointments")
            assert doctors_response.status_code == 200
            assert appointments_response.status_code == 200

            doctors = doctors_response.json()
            assert doctors
            slot = next(
                slot
                for doctor in doctors
                for slot in doctor["available_slots"]
            )
            assert appointments_response.json()

            with client.websocket_connect("/ws/events") as websocket:
                booking_response = client.post(
                    "/api/appointments",
                    json={"slot_id": slot["id"], "phone": "9876543210"},
                )
                assert booking_response.status_code == 201
                booked_event = websocket.receive_json()
                assert booked_event["topic"] == "appointment.booked"

                appointment_id = booking_response.json()["id"]
                cancellation_response = client.request(
                    "DELETE",
                    f"/api/appointments/{appointment_id}",
                    json={"phone": "9876543210"},
                )
                assert cancellation_response.status_code == 200
                cancelled_event = websocket.receive_json()
                assert cancelled_event["topic"] == "appointment.cancelled"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()