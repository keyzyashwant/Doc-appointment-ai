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
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
