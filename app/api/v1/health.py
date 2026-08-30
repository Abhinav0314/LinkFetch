from fastapi import APIRouter, Depends
from app.core.config import settings
from app.api.deps import get_linkedin_service, get_cache_service
from app.services.linkedin_client import LinkedInScraperService
from app.services.cache import CacheService

router = APIRouter(prefix="/health", tags=["Health & Diagnostics"])


@router.get(
    "",
    summary="API Health and Diagnostics",
    description="Returns the status of the API, cache performance metrics, and LinkedIn session health.",
)
async def health_check(
    service: LinkedInScraperService = Depends(get_linkedin_service),
    cache: CacheService = Depends(get_cache_service),
):
    session_status = await service.check_session_health()
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "session": session_status,
        "cache": cache.stats,
    }
