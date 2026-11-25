from app.api.routes.appointments import router as appointments_router
from app.api.routes.doctors import router as doctors_router
from app.api.routes.ws import router as ws_router

# Voice/offer route is imported lazily to avoid hard pipecat dependency
# when running tests or the REST-only server.
__all__ = ["appointments_router", "doctors_router", "ws_router"]
