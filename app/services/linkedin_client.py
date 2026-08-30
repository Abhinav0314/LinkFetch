import time
import asyncio
import random
import urllib.parse
from typing import Optional, Tuple, Dict, Any
from fastapi import HTTPException
from curl_cffi import requests

from app.core.config import settings
from app.core.logging import logger
from app.schemas.profile import ProfileData
from app.services.cache import cache_service
from app.services.rate_limiter import rate_limiter
from app.services.parser import PublicProfileParser, VoyagerGraphParser


class LinkedInScraperService:
    """Multi-Strategy LinkedIn profile extraction engine with dynamic session management."""

    VOYAGER_BASE = "https://www.linkedin.com/voyager/api"
    PUBLIC_BASE = "https://www.linkedin.com/in"

    def __init__(self):
        self._voyager_client: Optional[requests.AsyncSession] = None
        self._live_cookies: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _sync_live_cookies(self):
        """Initializes or refreshes the live cookie dictionary from settings."""
        async with self._lock:
            self._live_cookies = dict(settings.parsed_cookies)

    def _get_active_csrf_token(self) -> str:
        """Dynamically extracts the current active CSRF token from the cookie jar."""
        val = self._live_cookies.get("JSESSIONID", "")
        token = val.strip().strip('"')
        return token or (settings.sanitized_csrf_token or "")

    async def get_voyager_client(self) -> requests.AsyncSession:
        """Returns or initializes the shared curl_cffi AsyncSession for authenticated Voyager requests."""
        if self._voyager_client is None or getattr(self._voyager_client, "_closed", False):
            self._voyager_client = requests.AsyncSession(
                impersonate="chrome150",
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            await self._sync_live_cookies()
        return self._voyager_client

    async def close(self) -> None:
        """Closes HTTP client session on shutdown."""
        if self._voyager_client and not getattr(self._voyager_client, "_closed", False):
            await self._voyager_client.close()

    async def get_profile(self, public_id: str, force_refresh: bool = False) -> Tuple[ProfileData, str, bool]:
        """
        Fetches LinkedIn profile data using the best available strategy.
        Returns (ProfileData, strategy_used, is_cached).
        """
        raw_clean_id = public_id.strip().strip("/")
        clean_id = urllib.parse.quote(raw_clean_id)
        profile_url = f"https://www.linkedin.com/in/{clean_id}"

        # 1. Check Cache (bypassed if force_refresh is True)
        if not force_refresh:
            cached_data = cache_service.get(raw_clean_id)
            if cached_data:
                logger.info(f"Serving profile '{raw_clean_id}' from cache.")
                return cached_data, "cache", True
        else:
            logger.info(f"Force refresh requested for '{raw_clean_id}' — bypassing cache.")

        # 2. Try Authenticated Voyager Strategy if session credentials are configured
        if settings.has_session_credentials:
            try:
                logger.info(f"Attempting Voyager API fetch for '{raw_clean_id}'...")
                profile_data = await self._fetch_via_voyager(clean_id, profile_url)
                cache_service.set(raw_clean_id, profile_data)
                return profile_data, "voyager_api", False
            except HTTPException as he:
                if he.status_code in (404, 429):
                    raise
                logger.warning(
                    f"Voyager fetch returned HTTP {he.status_code} for '{raw_clean_id}': {he.detail}. "
                    "Falling back to Public JSON-LD strategy..."
                )
            except Exception as e:
                logger.warning(
                    f"Voyager fetch failed for '{raw_clean_id}': {e}. "
                    "Falling back to Public JSON-LD strategy..."
                )
        elif settings.LINKEDIN_LI_AT and not settings.LINKEDIN_JSESSIONID:
            logger.warning(
                "LINKEDIN_LI_AT is set, but LINKEDIN_JSESSIONID is missing in .env! "
                "Both cookies must be set to prevent LinkedIn CSRF session revocation. "
                "Falling back to Public Zero-Cookie strategy..."
            )

        # 3. Fallback to Zero-Cookie Public Strategy
        logger.info(f"Fetching profile '{raw_clean_id}' via Zero-Cookie Public Strategy...")
        profile_data = await self._fetch_via_public(clean_id, profile_url)
        cache_service.set(raw_clean_id, profile_data)
        return profile_data, "public_json_ld", False

    async def _fetch_via_voyager(self, public_id: str, profile_url: str) -> ProfileData:
        """Fetches and parses profile data via internal Voyager REST / Dash endpoints using dynamic session cookies."""
        client = await self.get_voyager_client()
        async with rate_limiter:
            if not self._live_cookies:
                await self._sync_live_cookies()

            csrf_token = self._get_active_csrf_token()
            page_instance_id = f"urn:li:page:d_flagship3_profile_view_base;{random.randint(10000000, 99999999)}"

            headers = {
                "Accept": "application/vnd.linkedin.normalized+json+2.1",
                "Accept-Language": "en-US,en-IN;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Referer": f"https://www.linkedin.com/in/{public_id}/",
                "Origin": "https://www.linkedin.com",
                "dnt": "1",
                "x-restli-protocol-version": "2.0.0",
                "csrf-token": csrf_token,
                "x-li-lang": "en_US",
                "x-li-track": '{"clientVersion":"1.13.21","mpVersion":"1.13.21","osName":"web","deviceFormFactor":"DESKTOP","mpName":"voyager-web"}',
                "x-li-page-instance": page_instance_id,
                "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": settings.USER_AGENT,
            }

            # Strategy: Use profileView (single request, returns ALL data) as primary.
            # Only fall back to dash endpoint if profileView fails.
            # This mimics a real browser which loads one page, not 8 API calls.

            primary_json = None

            # 1. Try legacy profileView first — returns skills, positions, educations all in one response
            profile_view_url = f"{self.VOYAGER_BASE}/identity/profiles/{public_id}/profileView"
            try:
                await asyncio.sleep(random.uniform(0.3, 0.8))  # Human-like delay
                response = await client.get(profile_view_url, headers=headers, cookies=self._live_cookies, allow_redirects=False)
                await self._update_cookie_jar(response, client)
                if response.status_code == 200:
                    primary_json = response.json()
            except Exception as e:
                logger.debug(f"profileView request failed: {e}")

            # 2. If profileView failed, try Dash decorator endpoint
            if not primary_json:
                dash_url = (
                    f"{self.VOYAGER_BASE}/identity/dash/profiles"
                    f"?q=memberIdentity&memberIdentity={public_id}"
                    f"&decorationId=com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-35"
                )
                response = await client.get(dash_url, headers=headers, cookies=self._live_cookies, allow_redirects=False)
                await self._update_cookie_jar(response, client)

                # 3. Fallback to authenticated web page if dash also failed
                if response.status_code in (404, 400):
                    web_url = f"{self.PUBLIC_BASE}/{public_id}"
                    web_headers = {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": "https://www.linkedin.com/",
                        "User-Agent": settings.USER_AGENT,
                    }
                    web_resp = await client.get(web_url, headers=web_headers, cookies=self._live_cookies, allow_redirects=True)
                    await self._update_cookie_jar(web_resp, client)
                    if web_resp.status_code == 200:
                        return PublicProfileParser.parse(web_resp.text, public_id, profile_url)
                    response = web_resp

                if response.status_code in (301, 302, 303, 307, 308, 401, 403):
                    raise RuntimeError(f"LinkedIn session expired or unauthorized (Status {response.status_code}).")
                elif response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"LinkedIn profile '{public_id}' not found.")
                elif response.status_code == 429:
                    raise HTTPException(status_code=429, detail="LinkedIn rate limit encountered. Please try again later.")
                elif response.status_code == 999:
                    raise RuntimeError(f"LinkedIn returned HTTP 999 (bot detection) on Voyager fallback.")

                response.raise_for_status()
                primary_json = response.json()

            return VoyagerGraphParser.parse(primary_json, public_id, profile_url)

    async def _update_cookie_jar(self, response: Any, client: requests.AsyncSession):
        """Updates internal live cookie jar from response cookies and client cookies safely."""
        try:
            async with self._lock:
                if hasattr(client, "cookies"):
                    for k, v in client.cookies.items():
                        self._live_cookies[k] = v
                if hasattr(response, "cookies"):
                    for k, v in response.cookies.items():
                        self._live_cookies[k] = v
        except Exception:
            pass

    async def _fetch_via_public(self, public_id: str, profile_url: str) -> ProfileData:
        """
        Fetches and parses public profile HTML using Schema.org JSON-LD & meta tags.
        Uses an isolated fresh AsyncSession per request to prevent guest-cookie persistence.
        """
        async with rate_limiter:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.google.com/",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }

            target_url = f"{self.PUBLIC_BASE}/{public_id}"

            # Always create a fresh AsyncSession for zero-cookie requests
            async with requests.AsyncSession(
                impersonate="chrome124",
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            ) as session:
                response = await session.get(target_url, headers=headers)

                # Retry once on HTTP 999 block using fresh session with distinct browser impersonation
                if response.status_code == 999:
                    retry_delay = random.uniform(2.0, 4.0)
                    logger.warning(f"Got HTTP 999 block for '{public_id}'. Retrying in {retry_delay:.1f}s with Safari TLS fingerprint...")
                    await asyncio.sleep(retry_delay)

                    retry_headers = {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Referer": "https://www.google.com/",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Upgrade-Insecure-Requests": "1",
                    }
                    async with requests.AsyncSession(
                        impersonate="safari17_2_ios",
                        timeout=settings.REQUEST_TIMEOUT_SECONDS,
                    ) as retry_session:
                        response = await retry_session.get(target_url, headers=retry_headers)

                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"LinkedIn profile '{public_id}' not found.")
                elif response.status_code == 429:
                    raise HTTPException(status_code=429, detail="LinkedIn public rate limit hit. Try again in a few moments.")
                elif response.status_code == 999:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"LinkedIn returned HTTP 999 (bot detection / auth-wall) for profile '{public_id}'. "
                            "This profile requires authenticated access. Configure LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in your .env file "
                            "to enable authenticated extraction via LinkedIn Voyager API."
                        ),
                    )

                if response.status_code >= 400:
                    raise HTTPException(
                        status_code=502,
                        detail=f"LinkedIn returned unexpected status {response.status_code} for '{public_id}'.",
                    )

                return PublicProfileParser.parse(response.text, public_id, profile_url)

    async def check_session_health(self) -> dict:
        """Reports whether session credentials are configured. Never contacts LinkedIn to avoid triggering detection."""
        if not settings.has_session_credentials:
            if settings.LINKEDIN_LI_AT and not settings.LINKEDIN_JSESSIONID:
                return {
                    "session_configured": False,
                    "status": "missing_jsessionid",
                    "message": "LINKEDIN_LI_AT is set, but LINKEDIN_JSESSIONID is missing. Both cookies are required.",
                }
            return {
                "session_configured": False,
                "status": "zero_cookie_mode",
                "message": "Running in Zero-Cookie Public Mode (Schema.org JSON-LD extraction active).",
            }

        return {
            "session_configured": True,
            "status": "configured",
            "message": "LinkedIn session credentials are configured. Voyager API will be used for deep extraction.",
        }


linkedin_service = LinkedInScraperService()
