import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, status

from app.api.deps import get_linkedin_service
from app.core.logging import logger
from app.schemas.profile import ProfileResponse, ResponseMetadata
from app.schemas.request import ProfileRequest, parse_linkedin_url
from app.services.linkedin_client import LinkedInScraperService

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.post(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Scrape and extract LinkedIn profile data (POST)",
    description="Accepts a LinkedIn profile URL in JSON body and returns structured profile information.",
)
async def extract_profile_post(
    request: ProfileRequest,
    service: LinkedInScraperService = Depends(get_linkedin_service),
) -> ProfileResponse:
    start_time = time.time()
    try:
        public_id = request.public_id
        profile_data, strategy, is_cached = await service.get_profile(
            public_id, force_refresh=request.force_refresh
        )

        duration_ms = int((time.time() - start_time) * 1000)
        return ProfileResponse(
            success=True,
            data=profile_data,
            metadata=ResponseMetadata(
                scraped_at=datetime.now(timezone.utc).isoformat(),
                execution_time_ms=duration_ms,
                cached=is_cached,
                strategy_used=strategy,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing profile request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract LinkedIn profile due to an internal server error.",
        )


@router.get(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Scrape and extract LinkedIn profile data (GET)",
    description="Accepts a LinkedIn profile URL or vanity username as query parameter and returns structured profile information.",
)
async def extract_profile_get(
    url: str = Query(
        ...,
        description="LinkedIn profile URL or public ID (e.g., https://www.linkedin.com/in/username or 'username')",
        examples=["https://www.linkedin.com/in/username"],
    ),
    force_refresh: bool = Query(
        False,
        description="If True, bypasses cache and forces a fresh live scrape from LinkedIn.",
    ),
    service: LinkedInScraperService = Depends(get_linkedin_service),
) -> ProfileResponse:
    start_time = time.time()
    try:
        public_id = parse_linkedin_url(url)
        profile_data, strategy, is_cached = await service.get_profile(
            public_id, force_refresh=force_refresh
        )

        duration_ms = int((time.time() - start_time) * 1000)
        return ProfileResponse(
            success=True,
            data=profile_data,
            metadata=ResponseMetadata(
                scraped_at=datetime.now(timezone.utc).isoformat(),
                execution_time_ms=duration_ms,
                cached=is_cached,
                strategy_used=strategy,
            ),
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error processing GET profile request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract LinkedIn profile due to an internal server error.",
        )
