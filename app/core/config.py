from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from app import __version__


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server Info
    PROJECT_NAME: str = "LinkFetch API"
    VERSION: str = __version__
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Optional LinkedIn session credentials for deep internal Voyager API extraction
    LINKEDIN_LI_AT: Optional[str] = None
    LINKEDIN_JSESSIONID: Optional[str] = None
    LINKEDIN_BCOOKIE: Optional[str] = None
    LINKEDIN_BSCOOKIE: Optional[str] = None
    LINKEDIN_LIDC: Optional[str] = None
    LINKEDIN_COOKIES: Optional[str] = None  # Full raw cookie string from browser DevTools

    # Request & Networking settings
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    MAX_CONCURRENT_REQUESTS: int = 3
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )

    # Caching
    CACHE_TTL_SECONDS: int = 3600  # 1 hour
    CACHE_MAX_SIZE: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def parsed_cookies(self) -> dict:
        """Parses individual env cookies or full raw LINKEDIN_COOKIES string into a unified cookie dict."""
        cookies: dict = {}

        # 1. Parse raw full cookie string if provided
        if self.LINKEDIN_COOKIES and self.LINKEDIN_COOKIES.strip():
            raw_pairs = self.LINKEDIN_COOKIES.strip().split(";")
            for pair in raw_pairs:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k_clean = k.strip()
                    v_clean = v.strip()
                    if k_clean and v_clean:
                        cookies[k_clean] = v_clean

        # 2. Overlay individual environment variables
        if self.LINKEDIN_LI_AT and self.LINKEDIN_LI_AT.strip():
            cookies["li_at"] = self.LINKEDIN_LI_AT.strip().strip('"')
        if self.LINKEDIN_JSESSIONID and self.LINKEDIN_JSESSIONID.strip():
            token = self.LINKEDIN_JSESSIONID.strip().strip('"')
            cookies["JSESSIONID"] = f'"{token}"'
        if self.LINKEDIN_BCOOKIE and self.LINKEDIN_BCOOKIE.strip():
            cookies["bcookie"] = self.LINKEDIN_BCOOKIE.strip()
        if self.LINKEDIN_BSCOOKIE and self.LINKEDIN_BSCOOKIE.strip():
            cookies["bscookie"] = self.LINKEDIN_BSCOOKIE.strip()
        if self.LINKEDIN_LIDC and self.LINKEDIN_LIDC.strip():
            cookies["lidc"] = self.LINKEDIN_LIDC.strip()

        return cookies

    @property
    def has_session_credentials(self) -> bool:
        """Returns True if BOTH li_at and JSESSIONID cookies are configured."""
        cookies = self.parsed_cookies
        return bool(
            cookies.get("li_at")
            and cookies.get("JSESSIONID")
        )

    @property
    def sanitized_csrf_token(self) -> Optional[str]:
        """Derives clean unquoted csrf-token header value from JSESSIONID."""
        cookies = self.parsed_cookies
        raw = cookies.get("JSESSIONID")
        if not raw:
            return None
        return raw.strip().strip('"')

    @property
    def cookie_jsessionid(self) -> Optional[str]:
        """Ensures JSESSIONID cookie format (quoted string as stored in browser cookie jar)."""
        token = self.sanitized_csrf_token
        if not token:
            return None
        return f'"{token}"'


settings = Settings()
