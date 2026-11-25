from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger
from app.seed import seed_database

logger = get_logger(__name__)


def init_database() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        get_settings().validate_voice_settings()
    except RuntimeError:
        logger.exception("Voice configuration is incomplete; refusing startup")
        raise
    init_database()
    logger.info("Database ready")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Doctor Appointment AI", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        body: dict = {"detail": exc.message}
        if exc.code is not None:
            body["code"] = exc.code.value
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Wire up route modules
    from app.api.routes import appointments_router, doctors_router, ws_router

    app.include_router(doctors_router)
    app.include_router(appointments_router)
    app.include_router(ws_router)

    # Voice/WebRTC signaling (imported lazily — pipecat may not be installed)
    try:
        from app.api.routes.offer import router as offer_router

        app.include_router(offer_router)
    except ImportError:
        logger.warning("pipecat not installed — /api/offer route disabled")

    return app


app = create_app()
