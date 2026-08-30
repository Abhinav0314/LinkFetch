import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def sample_public_html():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Satya Nadella - Chairman and CEO at Microsoft | LinkedIn</title>
        <meta property="og:title" content="Satya Nadella - Chairman and CEO at Microsoft | LinkedIn" />
        <meta property="og:description" content="Chairman and CEO at Microsoft. Experienced tech executive." />
        <meta property="og:image" content="https://media.licdn.com/dms/image/sample_profile.jpg" />
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "Satya Nadella",
            "givenName": "Satya",
            "familyName": "Nadella",
            "jobTitle": "Chairman and CEO",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Redmond",
                "addressRegion": "Washington",
                "addressCountry": "United States"
            },
            "image": "https://media.licdn.com/dms/image/sample_profile.jpg",
            "description": "Leading Microsoft into the AI era.",
            "sameAs": "https://news.microsoft.com/exec/satya-nadella/",
            "worksFor": [
                {
                    "@type": "Organization",
                    "name": "Microsoft",
                    "url": "https://www.linkedin.com/company/microsoft"
                }
            ],
            "alumniOf": [
                {
                    "@type": "EducationalOrganization",
                    "name": "University of Chicago Booth School of Business",
                    "url": "https://www.linkedin.com/school/uchicagobooth"
                }
            ]
        }
        </script>
    </head>
    <body>
        <h1>Satya Nadella</h1>
    </body>
    </html>
    """


@pytest.fixture
def sample_voyager_json():
    return {
        "data": {
            "$type": "com.linkedin.voyager.identity.profile.Profile",
            "entityUrn": "urn:li:fs_profile:ACoAA...",
            "firstName": "Satya",
            "lastName": "Nadella",
            "headline": "Chairman and CEO at Microsoft",
            "summary": "Building modern AI platforms and developer tooling.",
            "geoLocationName": "Redmond, Washington, United States",
            "picture": {
                "com.linkedin.common.VectorImage": {
                    "rootUrl": "https://media.licdn.com/dms/image/v2/D4E03AQG/",
                    "artifacts": [
                        {"width": 200, "height": 200, "fileIdentifyingUrlPathSegment": "profile-displayphoto-shrink_200_200.jpg"},
                        {"width": 800, "height": 800, "fileIdentifyingUrlPathSegment": "profile-displayphoto-shrink_800_800.jpg"}
                    ]
                }
            }
        },
        "included": [
            {
                "$type": "com.linkedin.voyager.identity.profile.Position",
                "entityUrn": "urn:li:fs_position:(ACoAA...,1)",
                "title": "Chairman and CEO",
                "companyName": "Microsoft",
                "companyUrn": "urn:li:fs_miniCompany:1035",
                "locationName": "Redmond, WA",
                "timePeriod": {
                    "startDate": {"year": 2014, "month": 2}
                },
                "isCurrent": True,
                "description": "Leading Microsoft worldwide operations and strategy."
            },
            {
                "$type": "com.linkedin.voyager.identity.profile.Education",
                "entityUrn": "urn:li:fs_education:(ACoAA...,1)",
                "schoolName": "University of Chicago Booth School of Business",
                "degreeName": "Master of Business Administration (MBA)",
                "fieldOfStudy": "Business Administration",
                "timePeriod": {
                    "startDate": {"year": 1994},
                    "endDate": {"year": 1997}
                }
            },
            {
                "$type": "com.linkedin.voyager.identity.profile.Skill",
                "name": "Cloud Computing",
                "endorsementCount": 99
            },
            {
                "$type": "com.linkedin.voyager.identity.profile.Skill",
                "name": "Artificial Intelligence",
                "endorsementCount": 99
            },
            {
                "$type": "com.linkedin.voyager.identity.profile.Certification",
                "name": "Azure Solutions Architect Expert",
                "authority": "Microsoft",
                "licenseNumber": "MS-AZ305"
            },
            {
                "$type": "com.linkedin.voyager.identity.profile.Language",
                "name": "English",
                "proficiency": "NATIVE_OR_BILINGUAL"
            }
        ]
    }


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
