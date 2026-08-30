from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DateModel(BaseModel):
    """Represents a partial or full date."""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None


class Location(BaseModel):
    """Location information."""
    raw: Optional[str] = Field(None, description="Full raw location string")
    city: Optional[str] = Field(None, description="City name")
    region: Optional[str] = Field(None, description="State / Province / Region")
    country: Optional[str] = Field(None, description="Country name")
    country_code: Optional[str] = Field(None, description="ISO country code")


class Position(BaseModel):
    """A single work experience entry."""
    title: str = Field(..., description="Job title / role")
    company_name: str = Field(..., description="Company name")
    company_url: Optional[str] = Field(None, description="Company LinkedIn or website URL")
    company_logo_url: Optional[str] = Field(None, description="Company logo image URL")
    company_urn: Optional[str] = Field(None, description="LinkedIn company URN")
    location: Optional[str] = Field(None, description="Job location")
    start_date: Optional[DateModel] = Field(None, description="Start date")
    end_date: Optional[DateModel] = Field(None, description="End date (null if current role)")
    is_current: bool = Field(False, description="Whether this is the current job")
    description: Optional[str] = Field(None, description="Role summary / responsibilities")
    employment_type: Optional[str] = Field(None, description="e.g., Full-time, Part-time, Contract")


class Education(BaseModel):
    """A single education entry."""
    school_name: str = Field(..., description="School or University name")
    school_url: Optional[str] = Field(None, description="School LinkedIn URL")
    school_logo_url: Optional[str] = Field(None, description="School logo image URL")
    degree_name: Optional[str] = Field(None, description="Degree name (e.g. Bachelor of Science, MBA)")
    field_of_study: Optional[str] = Field(None, description="Major / Field of study")
    start_year: Optional[int] = Field(None, description="Start year")
    end_year: Optional[int] = Field(None, description="End year")
    grade: Optional[str] = Field(None, description="Grade / GPA")
    activities: Optional[str] = Field(None, description="Societies, sports, or clubs")
    description: Optional[str] = Field(None, description="Notes or description")


class Skill(BaseModel):
    """A skill item."""
    name: str = Field(..., description="Skill name")
    endorsement_count: Optional[int] = Field(None, description="Number of endorsements")


class Certification(BaseModel):
    """A certification or license entry."""
    name: str = Field(..., description="Certification name")
    authority: Optional[str] = Field(None, description="Issuing organization")
    license_number: Optional[str] = Field(None, description="License or credential ID")
    url: Optional[str] = Field(None, description="Verification or credential URL")
    issue_date: Optional[DateModel] = Field(None, description="Date issued")
    expiration_date: Optional[DateModel] = Field(None, description="Date expiring")


class Language(BaseModel):
    """A spoken or written language."""
    name: str = Field(..., description="Language name")
    proficiency: Optional[str] = Field(None, description="e.g. Native, Professional working, Elementary")


class ContactInfo(BaseModel):
    """Public contact information."""
    websites: List[str] = Field(default_factory=list, description="Associated websites")
    twitter: Optional[str] = Field(None, description="Twitter handle")
    emails: List[str] = Field(default_factory=list, description="Public emails if visible")
    phone_numbers: List[str] = Field(default_factory=list, description="Phone numbers if visible")


class ProfileData(BaseModel):
    """Structured representation of a LinkedIn profile."""
    public_id: str = Field(..., description="Vanity identifier (e.g. satyanadella)")
    urn_id: Optional[str] = Field(None, description="LinkedIn member URN")
    profile_url: str = Field(..., description="Full LinkedIn profile URL")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    full_name: str = Field(..., description="Full display name")
    headline: Optional[str] = Field(None, description="Profile headline / tagline")
    location: Optional[Location] = Field(None, description="Location details")
    about: Optional[str] = Field(None, description="About summary section")
    profile_picture_url: Optional[str] = Field(None, description="Avatar / Profile picture URL")
    background_picture_url: Optional[str] = Field(None, description="Header banner image URL")

    # Deep structured sections
    experience: List[Position] = Field(default_factory=list, description="Work experience history")
    education: List[Education] = Field(default_factory=list, description="Educational background")
    skills: List[Skill] = Field(default_factory=list, description="Skills and competencies")
    certifications: List[Certification] = Field(default_factory=list, description="Licenses and certifications")
    languages: List[Language] = Field(default_factory=list, description="Languages spoken")
    contact_info: Optional[ContactInfo] = Field(default_factory=ContactInfo, description="Contact information")


class ResponseMetadata(BaseModel):
    """Response diagnostic metadata."""
    scraped_at: str = Field(..., description="ISO 8601 timestamp")
    execution_time_ms: int = Field(..., description="Execution time in milliseconds")
    cached: bool = Field(False, description="Whether the response was served from cache")
    strategy_used: str = Field(..., description="Extraction strategy ('voyager_api' or 'public_json_ld')")


class ProfileResponse(BaseModel):
    """Successful API response payload."""
    success: bool = True
    data: ProfileData
    metadata: ResponseMetadata


class ErrorResponse(BaseModel):
    """Error API response payload."""
    success: bool = False
    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Machine-readable error code")
    details: Optional[Dict[str, Any]] = None
