from fastapi import APIRouter
from app.api.v1.profile import router as profile_router
from app.api.v1.health import router as health_router
from app.core.config import settings

api_v1_router = APIRouter()


@api_v1_router.api_route("", methods=["GET", "HEAD"], include_in_schema=False)
@api_v1_router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def api_v1_index():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "docs": "/docs",
        "endpoints": {
            "profile": f"{settings.API_PREFIX}/profile",
            "health": f"{settings.API_PREFIX}/health",
        },
    }


api_v1_router.include_router(health_router)
api_v1_router.include_router(profile_router)
