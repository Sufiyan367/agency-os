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
    from app.core.security import validate_production_configuration
    validate_production_configuration(raise_on_error=True, allow_initial_setup=True)
    logger.info("Starting Autonomous B2B Lead-Gen & Sales Agency Application...")
    await init_db()
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
    logger.info("Application initialized and ready.")

    if settings.WORKER_ENABLED:
        await agency_worker.start()

    from app.agents.revenue_agent import revenue_agent_orchestrator
    if getattr(settings, "AUTONOMOUS_AGENT_ENABLED", False):
        revenue_agent_orchestrator.start()

    yield

    revenue_agent_orchestrator.stop()
    if settings.WORKER_ENABLED:
        await agency_worker.stop()
    logger.info("Application shutdown.")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# Parse restricted CORS origins
raw_origins = getattr(settings, "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.core.security import verify_session_token, rate_limiter

# Security Headers & Rate Limiting Middleware
@app.middleware("http")
async def security_headers_and_rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    path = request.url.path

    # Rate limiting checks
    if getattr(settings, "RATE_LIMIT_ENABLED", True):
        # 1. Login & Password Reset endpoint rate limit: 5 req/min
        if path in ("/api/auth/login", "/api/auth/forgot-password", "/api/auth/reset-password") and request.method == "POST":
            limiter_key = "login" if path == "/api/auth/login" else "reset"
            allowed, retry_after = await rate_limiter.is_allowed(f"{limiter_key}:{client_ip}", max_requests=5, window_seconds=60)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many attempts. Please wait before retrying.", "status_code": 429},
                    headers={"Retry-After": str(retry_after)}
                )
        # 2. Agent control endpoints rate limit: 15 req/min
        elif path.startswith("/api/agent/") and request.method in ("POST", "PUT", "DELETE"):
            allowed, retry_after = await rate_limiter.is_allowed(f"agent_ctrl:{client_ip}", max_requests=15, window_seconds=60)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many agent control requests. Rate limit exceeded.", "status_code": 429},
                    headers={"Retry-After": str(retry_after)}
                )
        # 3. Webhook endpoints: 60 req/min
        elif path.startswith("/api/webhooks/"):
            allowed, retry_after = await rate_limiter.is_allowed(f"webhook:{client_ip}", max_requests=60, window_seconds=60)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many webhook requests.", "status_code": 429},
                    headers={"Retry-After": str(retry_after)}
                )
        # 4. Public contact inquiry endpoint: 5 req/min
        elif path == "/api/contact" and request.method == "POST":
            allowed, retry_after = await rate_limiter.is_allowed(f"contact:{client_ip}", max_requests=5, window_seconds=60)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many contact inquiries. Please wait a moment before trying again.", "status_code": 429},
                    headers={"Retry-After": str(retry_after)}
                )

    # Authentication & RBAC enforcement when AUTH_ENABLED is True
    if getattr(settings, "AUTH_ENABLED", False):
        # Normalize path to prevent double slash or traversal bypasses
        clean_parts = [p for p in path.split("/") if p and p != "."]
        normalized_path = "/" + "/".join(clean_parts) if clean_parts else "/"

        public_exact_paths = {
            "/",
            "/website",
            "/api/contact",
            "/health",
            "/api/health",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/setup",
            "/api/auth/status",
            "/api/auth/forgot-password",
            "/api/auth/reset-password",
            "/login",
            "/setup",
            "/reset-password",
        }
        privileged_prefixes = (
            "/api/agent/start",
            "/api/agent/pause",
            "/api/agent/resume",
            "/api/agent/stop",
            "/api/agent/kill",
            "/api/agent/emergency-stop",
            "/api/agent/step",
            "/api/agent/cycle-step",
            "/api/agent/build-website",
            "/api/agent/trigger-cycle",
            "/api/outreach/approve",
            "/api/outreach/reject",
            "/api/outreach/dispatch",
            "/api/deals/create",
            "/api/deals/send-proposal",
            "/api/deals/request-payment",
            "/api/system/backup",
            "/api/system/restore",
            "/api/production/reset",
            "/api/voice/call",
            "/api/config/",
        )

        is_public = (
            normalized_path in public_exact_paths
            or normalized_path.startswith("/static/")
            or normalized_path.startswith("/api/webhooks/")
        )

        if not is_public:
            # Extract authentication credential from Cookie or Authorization header
            token = request.cookies.get("agency_session")
            auth_header = request.headers.get("Authorization", "")
            if not token and auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

            user_info = None
            if token:
                from app.core.security import verify_api_key, verify_session_token_with_role
                from app.core.auth_service import auth_service
                if verify_api_key(token):
                    user_info = {"username": "api_client", "role": "admin"}
                else:
                    info = verify_session_token_with_role(token)
                    if info and not auth_service.is_session_revoked(info["username"], token):
                        user_info = info

            if normalized_path in ("/dashboard", "/app", "/index.html"):
                if user_info and user_info.get("role") == "client":
                    return RedirectResponse(url="/client")
                from app.core.auth_service import auth_service
                setup_required = False
                try:
                    async with AsyncSessionLocal() as session:
                        setup_required = await auth_service.is_setup_required(session)
                except Exception as e:
                    logger.error(f"[Middleware] Database error checking setup requirement: {e}")
                    setup_required = False

                if setup_required:
                    return RedirectResponse(url="/setup")
                if not user_info:
                    return RedirectResponse(url="/login")
            elif normalized_path == "/client":
                if not user_info:
                    return RedirectResponse(url="/login")
            elif normalized_path.startswith("/api/"):
                if not user_info:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Authentication required. Please log in.", "status_code": 401}
                    )

                # RBAC Isolation: Client accounts CANNOT access agency operational endpoints
                if user_info.get("role") == "client":
                    is_allowed_client_api = (
                        normalized_path.startswith("/api/client/")
                        or normalized_path.startswith("/api/auth/")
                        or normalized_path in ("/api/health", "/api/contact")
                    )
                    if not is_allowed_client_api:
                        return JSONResponse(
                            status_code=403,
                            content={
                                "detail": "Forbidden: Client accounts cannot access agency operational data.",
                                "status_code": 403
                            }
                        )

                is_deal_mutation = (
                    request.method in ("POST", "PUT", "DELETE", "PATCH")
                    and normalized_path.startswith("/api/deals")
                )
                if any(normalized_path.startswith(prefix) for prefix in privileged_prefixes) or is_deal_mutation:
                    if user_info.get("role") not in ("admin", "operator"):
                        return JSONResponse(
                            status_code=403,
                            content={
                                "detail": "Forbidden: Privileged access required for agent control operations.",
                                "status_code": 403
                            }
                        )
            else:
                # Any other non-static route (e.g. /docs, /openapi.json, unknown pages) requires auth
                if not user_info:
                    if "application/json" in request.headers.get("accept", ""):
                        return JSONResponse(
                            status_code=401,
                            content={"detail": "Authentication required.", "status_code": 401}
                        )
                    return RedirectResponse(url="/login")

    response = await call_next(request)

    # Inject Production Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    if "/preview" in request.url.path:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'self';"
        )
    else:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        )
    return response

# Global Exception Sanitization (prevents path, traceback, and raw DB error leakage)
@app.exception_handler(Exception)
async def sanitized_global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[UnhandledServerException] {request.method} {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "status_code": 500
        }
    )

# Mount static and templates
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR) if os.path.exists(TEMPLATES_DIR) else None

# Include API endpoints
app.include_router(router)
from app.api.local_lead_routes import router as local_lead_router
app.include_router(local_lead_router)
from app.api.acquisition_routes import router as acquisition_router
app.include_router(acquisition_router)
from app.api.market_intelligence_routes import router as market_intelligence_router
app.include_router(market_intelligence_router)
from app.api.prospect_routes import router as prospect_router
app.include_router(prospect_router)
from app.api.analytics_routes import router as analytics_router
app.include_router(analytics_router)
from app.api.autonomous_routes import router as autonomous_router
app.include_router(autonomous_router)


@app.get("/setup", response_class=HTMLResponse)
async def serve_setup(request: Request):
    from app.core.auth_service import auth_service
    setup_required = False
    try:
        async with AsyncSessionLocal() as session:
            setup_required = await auth_service.is_setup_required(session)
    except Exception as e:
        logger.error(f"[ServeSetup] Database error checking setup requirement: {e}")
        # Fail closed: never show setup if database cannot be verified
        return RedirectResponse(url="/login")

    if not setup_required:
        return RedirectResponse(url="/login")

    if templates:
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={"app_name": settings.APP_NAME}
        )
    return HTMLResponse("<h1>Initial Setup Required</h1>")

@app.get("/login", response_class=HTMLResponse)
async def serve_login(request: Request):
    if not settings.AUTH_ENABLED:
        return RedirectResponse(url="/dashboard")
    token = request.cookies.get("agency_session")
    if token:
        from app.core.security import verify_session_token_with_role
        from app.core.auth_service import auth_service
        info = verify_session_token_with_role(token)
        if info and not auth_service.is_session_revoked(info["username"], token):
            if info.get("role") == "client":
                return RedirectResponse(url="/client")
            return RedirectResponse(url="/dashboard")
    if templates:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"app_name": settings.APP_NAME}
        )
    return HTMLResponse("<h1>Login Required</h1>")

@app.get("/reset-password", response_class=HTMLResponse)
async def serve_reset_password(request: Request):
    token = request.query_params.get("token", "")
    if templates:
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={"app_name": settings.APP_NAME, "token": token}
        )
    return HTMLResponse("<h1>Reset Password</h1>")


@app.get("/", response_class=HTMLResponse)
@app.get("/website", response_class=HTMLResponse)
async def serve_website(request: Request):
    if templates:
        return templates.TemplateResponse(
            request=request,
            name="website.html",
            context={
                "app_name": settings.APP_NAME,
            }
        )
    return HTMLResponse("<h1>Agency OS — AI Automation &amp; Digital Solutions</h1><p>Website is active.</p>")


@app.get("/client", response_class=HTMLResponse)
async def serve_client_portal(request: Request):
    """Client Portal: Dedicated authenticated client-facing project & deliverables experience."""
    if not settings.AUTH_ENABLED:
        if templates:
            return templates.TemplateResponse(
                request=request,
                name="client_portal.html",
                context={
                    "app_name": settings.APP_NAME,
                    "auth_enabled": False,
                    "username": "client"
                }
            )
        return HTMLResponse("<h1>Client Portal Active</h1>")

    token = request.cookies.get("agency_session")
    if token:
        from app.core.security import verify_session_token_with_role
        from app.core.auth_service import auth_service
        info = verify_session_token_with_role(token)
        if info and not auth_service.is_session_revoked(info["username"], token):
            if templates:
                return templates.TemplateResponse(
                    request=request,
                    name="client_portal.html",
                    context={
                        "app_name": settings.APP_NAME,
                        "auth_enabled": True,
                        "username": info.get("username", "client")
                    }
                )

    return RedirectResponse(url="/login")


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    if not settings.AUTH_ENABLED:
        if templates:
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "app_name": settings.APP_NAME,
                    "auth_enabled": False
                }
            )
        return HTMLResponse("<h1>Autonomous B2B Agency API is active</h1><p>Navigate to /docs for API documentation.</p>")

    token = request.cookies.get("agency_session")
    if token:
        from app.core.security import verify_session_token_with_role
        from app.core.auth_service import auth_service
        info = verify_session_token_with_role(token)
        if info and not auth_service.is_session_revoked(info["username"], token):
            # Client role should never see the agency owner dashboard
            if info.get("role") == "client":
                return RedirectResponse(url="/client")
            if templates:
                return templates.TemplateResponse(
                    request=request,
                    name="index.html",
                    context={
                        "app_name": settings.APP_NAME,
                        "auth_enabled": True
                    }
                )

    clean_path = request.url.path.rstrip("/")
    if clean_path in ("/dashboard", "/app"):
        from app.core.auth_service import auth_service
        setup_required = False
        try:
            async with AsyncSessionLocal() as session:
                setup_required = await auth_service.is_setup_required(session)
        except Exception as e:
            logger.error(f"[ServeDashboard] Database error checking setup requirement: {e}")
            setup_required = False

        if setup_required:
            return RedirectResponse(url="/setup")

    return RedirectResponse(url="/login")

