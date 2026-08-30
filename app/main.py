import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.logging import logger
from app.services.linkedin_client import linkedin_service


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

    # API Routers
    app.include_router(api_v1_router, prefix=settings.API_PREFIX)

    # Interactive API Documentation Portal at /docs
    @app.api_route("/docs", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    async def serve_docs():
        docs_path = os.path.join(static_dir, "docs.html")
        if os.path.exists(docs_path):
            return FileResponse(docs_path, media_type="text/html")
        return HTMLResponse("<h1>API Documentation</h1><p>Visit <a href='/openapi.json'>/openapi.json</a></p>")

    # Root route serving Web Playground UI & Render health ping
    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    async def serve_playground():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse("<h1>LinkFetch API is Running</h1><p>Visit <a href='/docs'>/docs</a></p>")

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
