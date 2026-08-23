from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import get_settings
from app.db import SessionLocal, create_all
from app.services.core import initialize_defaults
from app.services.demo import seed_demo


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Alembic is the production path; create_all also makes a fresh local checkout immediately usable.
    create_all()
    with SessionLocal() as db:
        initialize_defaults(db)
        if settings.load_demo_data:
            seed_demo(db)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_trusted_origin(request: Request, call_next):  # noqa: ANN001
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Origin is not allowed to modify local training data"},
            )
    return await call_next(request)


app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_prefix}/health"}
