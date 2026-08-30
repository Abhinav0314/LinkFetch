import os
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.api.v1.profile import router as profile_router
from app.api.v1.health import router as health_router
from app.api.deps import get_linkedin_service
from app.schemas.profile import ProfileResponse
from app.schemas.request import ProfileRequest
from app.services.linkedin_client import LinkedInScraperService, linkedin_service
from app.core.config import settings
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"Session configured: {settings.has_session_credentials}")
    yield
    logger.info("Shutting down LinkFetch API...")
    await linkedin_service.close()


TAGS_METADATA = [
    {
        "name": "Profile",
        "description": "Extract comprehensive LinkedIn profile data via Voyager REST/Dash API or public Schema.org JSON-LD fallback.",
    },
    {
        "name": "Health & Diagnostics",
        "description": "Real-time health status, active session credentials check, and in-memory LRU cache performance metrics.",
    },
]

OPENAPI_DESCRIPTION = """
### 🚀 LinkFetch API — High-Performance Profile Engine

A production-grade, reverse-engineered LinkedIn Profile Extraction API supporting **Authenticated Voyager REST/Dash APIs** and **Zero-Cookie Public JSON-LD fallback**.
"""

def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="LinkFetch API",
        version=settings.VERSION,
        description=OPENAPI_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        docs_url=None,  # We serve custom ultra-modern Scalar docs at /docs and Swagger at /swagger
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Disable client/proxy HTTP caching on all API responses
    @app.middleware("http")
    async def add_no_cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Static UI directory
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # API Routers (mounted at /api/v1 as well as root for maximum client compatibility)
    app.include_router(api_v1_router, prefix=settings.API_PREFIX)
    app.include_router(profile_router, include_in_schema=False)
    app.include_router(health_router, include_in_schema=False)

    # Interactive API Documentation Portal at /docs
    @app.api_route("/docs", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    async def serve_docs():
        docs_path = os.path.join(static_dir, "docs.html")
        if os.path.exists(docs_path):
            return FileResponse(docs_path, media_type="text/html")
        return HTMLResponse("<h1>API Documentation</h1><p>Visit <a href='/openapi.json'>/openapi.json</a></p>")

    # Root route: Direct Extraction or API Metadata JSON
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def root_endpoint(
        request: Request,
        url: Optional[str] = None,
        force_refresh: bool = False,
        service: LinkedInScraperService = Depends(get_linkedin_service),
    ):
        # If url query parameter is provided (e.g. ?url=satyanadella), extract immediately
        if url:
            from app.api.v1.profile import extract_profile_get
            return await extract_profile_get(url=url, force_refresh=force_refresh, service=service)

        # Return pure API JSON response directly
        return JSONResponse({
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "healthy",
            "docs_url": f"{str(request.base_url).rstrip('/')}/docs",
            "endpoints": {
                "profile": f"{str(request.base_url).rstrip('/')}/api/v1/profile",
                "health": f"{str(request.base_url).rstrip('/')}/api/v1/health",
            },
            "sample_request": {
                "method": "POST",
                "url": f"{str(request.base_url).rstrip('/')}/api/v1/profile",
                "headers": {"Content-Type": "application/json"},
                "body": {"url": "https://www.linkedin.com/in/satyanadella"}
            }
        })

    # Direct extraction on root POST for top-level domain submissions
    @app.post("/", response_model=ProfileResponse, include_in_schema=False)
    async def root_post_extract(
        request: ProfileRequest,
        service: LinkedInScraperService = Depends(get_linkedin_service),
    ) -> ProfileResponse:
        from app.api.v1.profile import extract_profile_post
        return await extract_profile_post(request=request, service=service)

    # Dedicated Web Playground UI route at /ui
    @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    async def serve_ui():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse("<h1>LinkFetch Playground</h1>")

    # Favicon route
    @app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
    async def favicon():
        favicon_path = os.path.join(static_dir, "favicon.svg")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path, media_type="image/svg+xml")
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    # Global Exception Handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "An internal server error occurred while processing the request.",
                "code": "INTERNAL_SERVER_ERROR",
                "details": {"path": str(request.url.path)},
            },
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
