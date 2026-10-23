"""
Main FastAPI Application for VTP Fleet Tracking.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import logger
from app.api.routes import router as fleet_router
from app.services.fleet_service import fleet_service

BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = BASE_DIR / "templates" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing VTP Fleet Tracking backend...")
    # Initial telemetry sync on startup
    await fleet_service.sync_telemetry()
    yield
    logger.info("Shutting down VTP Fleet Tracking backend...")


app = FastAPI(
    title="VTP Fleet Tracking Service",
    description="Unified Fleet Telemetry and Operational Management Dashboard for Viettel Post",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS enabled for web & mobile dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API Router
app.include_router(fleet_router)


@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    """Serves the unified fleet tracking dashboard."""
    if not INDEX_HTML_PATH.exists():
        return HTMLResponse("<h3>Dashboard file not found</h3>", status_code=404)
    return FileResponse(str(INDEX_HTML_PATH))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "vtp_fleet_tracking",
        "environment": "production" if not settings.DEBUG else "development",
        "safe_config": settings.get_safe_summary(),
    }
