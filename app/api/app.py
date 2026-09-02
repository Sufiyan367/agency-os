import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.logging import logger
from app.database.connection import init_db, AsyncSessionLocal
from app.database.seed_data import seed_initial_data
from app.api.routes import router

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "frontend", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "frontend", "templates")

from app.orchestrator.worker import agency_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Autonomous B2B Lead-Gen & Sales Agency Application...")
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    logger.info("Application initialized and ready.")

    if settings.WORKER_ENABLED:
        await agency_worker.start()

    yield

    if settings.WORKER_ENABLED:
        await agency_worker.stop()
    logger.info("Application shutdown.")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and templates
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR) if os.path.exists(TEMPLATES_DIR) else None

# Include API endpoints
app.include_router(router)

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    if templates:
        return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.APP_NAME})
    return HTMLResponse("<h1>Autonomous B2B Agency API is active</h1><p>Navigate to /docs for API documentation.</p>")
