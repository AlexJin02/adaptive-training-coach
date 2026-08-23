from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import router
from app.config import PROJECT_DIR, get_settings
from app.db import SessionLocal
from app.services.core import initialize_defaults
from app.services.demo import seed_demo


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ``make dev`` and ``make remote-server`` run Alembic before startup. Keeping schema creation
    # out of the hot-reload process prevents ORM create_all from racing a pending migration.
    with SessionLocal() as db:
        initialize_defaults(db)
        if settings.load_demo_data:
            seed_demo(db)
    yield


settings = get_settings()
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
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


def _frontend_asset(path: str) -> Path | None:
    dist = FRONTEND_DIST.resolve()
    candidate = (dist / path).resolve()
    try:
        candidate.relative_to(dist)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.get("/", include_in_schema=False)
def root() -> Response:
    index = _frontend_asset("index.html")
    if index:
        return FileResponse(index)
    return JSONResponse(
        {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_prefix}/health"}
    )


@app.get("/{path:path}", include_in_schema=False)
def frontend_spa(path: str) -> Response:
    api_path = settings.api_prefix.strip("/")
    if path == api_path or path.startswith(f"{api_path}/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if ".." in Path(path).parts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    asset = _frontend_asset(path)
    if asset:
        return FileResponse(asset)
    index = _frontend_asset("index.html")
    if index:
        return FileResponse(index)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
