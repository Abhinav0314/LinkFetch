import re
from typing import Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator, PrivateAttr


def parse_linkedin_url(url_or_identifier: str) -> str:
    """
    Extracts and sanitizes the LinkedIn public_id (vanity name / username) from any format:
    - https://www.linkedin.com/in/satyanadella/
    - http://linkedin.com/in/williamhgates?trk=public_profile
    - linkedin.com/in/satyanadella
    - www.linkedin.com/in/satyanadella
    - linkedin.com/satyanadella
    - /in/satyanadella
    - in/satyanadella
    - /satyanadella
    - @satyanadella
    - satyanadella
    """
    if not url_or_identifier or not url_or_identifier.strip():
        raise ValueError("LinkedIn URL or profile identifier cannot be empty.")

    cleaned = url_or_identifier.strip()

    # Remove leading '@' if someone types @username
    if cleaned.startswith("@"):
        cleaned = cleaned[1:].strip()

    # If it starts with protocol or domain
    if cleaned.startswith("http://") or cleaned.startswith("https://") or "linkedin.com" in cleaned:
        if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
            cleaned = "https://" + cleaned

        parsed = urlparse(cleaned)
        domain = parsed.netloc.lower()
        if domain and not (domain == "linkedin.com" or domain.endswith(".linkedin.com")):
            raise ValueError(f"Invalid domain '{domain}'. URL must be a valid LinkedIn URL.")

        path = parsed.path.strip("/")

        # Match /in/{public_id} or /pub/{public_id}
        match = re.search(r"(?:in|pub)/([^/?#&]+)", path)
        if match:
            public_id = match.group(1).strip()
            public_id = re.sub(r"[/#?&].*$", "", public_id)
            if public_id:
                return public_id

        # If path is just the vanity name (e.g. linkedin.com/satyanadella)
        parts = [p for p in path.split("/") if p and p not in ("in", "pub", "feed", "company", "school")]
        if parts:
            public_id = parts[0].strip()
            public_id = re.sub(r"[/#?&].*$", "", public_id)
            if public_id:
                return public_id

    # Strip any leading slashes (e.g. /satyanadella or /in/satyanadella)
    cleaned = cleaned.strip("/ \t\r\n")

    # Match in/username pattern (e.g. in/satyanadella)
    if cleaned.startswith("in/"):
        cleaned = cleaned[3:].strip("/?#& \t")

    # Match pub/username pattern
    if cleaned.startswith("pub/"):
        cleaned = cleaned[4:].strip("/?#& \t")

    # Remove trailing query params or slashes if any (e.g., satyanadella?trk=123 or satyanadella/)
    cleaned = re.split(r"[/?#&]", cleaned)[0].strip()

    # Match valid vanity username characters (letters, numbers, hyphens, underscores, percent-encoded)
    slug_match = re.match(r"^([a-zA-Z0-9\-_%]+)$", cleaned)
    if slug_match:
        return slug_match.group(1).strip()

    raise ValueError(f"Could not extract a valid LinkedIn profile identifier from: {url_or_identifier}")


class ProfileRequest(BaseModel):
    """Request payload for fetching a LinkedIn profile."""

    url: str = Field(
        ...,
        description="The LinkedIn profile URL or public ID (e.g., https://www.linkedin.com/in/satyanadella or satyanadella)",
        examples=["https://www.linkedin.com/in/satyanadella", "satyanadella", "/in/williamhgates"],
    )
    force_refresh: bool = Field(
        default=False,
        description="If True, bypasses cache and forces a fresh live scrape from LinkedIn.",
    )
    _parsed_id: Optional[str] = PrivateAttr(default=None)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parse_linkedin_url(v)
        return v.strip()

    def model_post_init(self, __context) -> None:
        self._parsed_id = parse_linkedin_url(self.url)

    @property
    def public_id(self) -> str:
        """Convenience property to extract the public ID from the validated URL."""
        if not self._parsed_id:
            self._parsed_id = parse_linkedin_url(self.url)
        return self._parsed_id
