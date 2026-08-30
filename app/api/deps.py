from app.services.linkedin_client import linkedin_service, LinkedInScraperService
from app.services.cache import cache_service, CacheService


def get_linkedin_service() -> LinkedInScraperService:
    """Dependency injector for LinkedInScraperService."""
    return linkedin_service


def get_cache_service() -> CacheService:
    """Dependency injector for CacheService."""
    return cache_service
