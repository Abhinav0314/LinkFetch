import pytest
from app.services.parser import PublicProfileParser, VoyagerGraphParser


def test_public_profile_parser(sample_public_html):
    profile = PublicProfileParser.parse(
        html_content=sample_public_html,
        public_id="satyanadella",
        profile_url="https://www.linkedin.com/in/satyanadella",
    )

    assert profile.public_id == "satyanadella"
    assert profile.full_name == "Satya Nadella"
    assert profile.first_name == "Satya"
    assert profile.last_name == "Nadella"
    assert profile.headline == "Chairman and CEO"
    assert profile.location is not None
    assert profile.location.city == "Redmond"
    assert profile.location.country == "United States"
    assert "sample_profile.jpg" in (profile.profile_picture_url or "")
    
    # Check experience & education
    assert len(profile.experience) >= 1
    assert profile.experience[0].company_name == "Microsoft"

    assert len(profile.education) >= 1
    assert "University of Chicago" in profile.education[0].school_name


def test_voyager_graph_parser(sample_voyager_json):
    profile = VoyagerGraphParser.parse(
        raw_json=sample_voyager_json,
        public_id="satyanadella",
        profile_url="https://www.linkedin.com/in/satyanadella",
    )

    assert profile.public_id == "satyanadella"
    assert profile.full_name == "Satya Nadella"
    assert profile.headline == "Chairman and CEO at Microsoft"
    assert profile.location is not None
    assert "Redmond" in (profile.location.raw or "")
    
    # Check resolution of largest image artifact (800x800)
    assert profile.profile_picture_url is not None
    assert "profile-displayphoto-shrink_800_800.jpg" in profile.profile_picture_url

    # Check experience
    assert len(profile.experience) == 1
    pos = profile.experience[0]
    assert pos.title == "Chairman and CEO"
    assert pos.company_name == "Microsoft"
    assert pos.is_current is True
    assert pos.start_date.year == 2014

    # Check education
    assert len(profile.education) == 1
    edu = profile.education[0]
    assert "University of Chicago" in edu.school_name
    assert edu.degree_name == "Master of Business Administration (MBA)"
    assert edu.start_year == 1994
    assert edu.end_year == 1997

    # Check skills
    assert len(profile.skills) == 2
    assert profile.skills[0].name == "Cloud Computing"
    assert profile.skills[0].endorsement_count == 99

    # Check certs & languages
    assert len(profile.certifications) == 1
    assert profile.certifications[0].name == "Azure Solutions Architect Expert"

    assert len(profile.languages) == 1
    assert profile.languages[0].name == "English"


def test_public_profile_parser_empty_and_masked():
    html = """
    <html>
    <head><title>*** | LinkedIn</title></head>
    <body>
        <script type="application/ld+json">
        {
            "@type": "Person",
            "name": "***",
            "worksFor": [{"@type": "Organization", "name": "***"}],
            "alumniOf": [{"@type": "EducationalOrganization", "name": "***"}]
        }
        </script>
    </body>
    </html>
    """
    profile = PublicProfileParser.parse(html, "johndoe", "https://www.linkedin.com/in/johndoe")
    assert profile.public_id == "johndoe"
    assert profile.full_name == "johndoe"  # Fallback to public_id when name is masked
    assert len(profile.experience) == 0     # Masked entries filtered out
    assert len(profile.education) == 0


def test_voyager_parser_empty_included():
    raw_json = {
        "data": {
            "$type": "com.linkedin.voyager.dash.identity.profile.Profile",
            "firstName": "Jane",
            "lastName": "Doe",
        },
        "included": []
    }
    profile = VoyagerGraphParser.parse(raw_json, "janedoe", "https://www.linkedin.com/in/janedoe")
    assert profile.full_name == "Jane Doe"
    assert len(profile.experience) == 0
    assert len(profile.education) == 0
    assert len(profile.skills) == 0


def test_voyager_parser_dash_skill_variations():
    raw_json = {
        "data": {
            "$type": "com.linkedin.voyager.dash.identity.profile.FullProfileWithEntities",
            "firstName": "Harshit",
            "lastName": "Trehan",
        },
        "included": [
            {
                "$type": "com.linkedin.voyager.dash.identity.profile.Skill",
                "name": "Python",
                "endorsementCount": 40,
            },
            {
                "$type": "com.linkedin.voyager.dash.identity.profile.SkillWithEndorsement",
                "name": "FastAPI",
                "endorsementCount": 25,
            },
            {
                "$type": "com.linkedin.voyager.dash.identity.profile.StandardizedSkill",
                "skill": {"name": "Kubernetes"},
            },
            {
                "$type": "com.linkedin.voyager.dash.identity.profile.Education",
                "schoolName": "Delhi University",
                "degreeName": "B.Tech",
                "timePeriod": {"startDate": {"year": 2018}, "endDate": {"year": 2022}},
            }
        ]
    }
    profile = VoyagerGraphParser.parse(raw_json, "harshit-trehan", "https://www.linkedin.com/in/harshit-trehan")
    assert len(profile.skills) == 3
    skill_names = {s.name for s in profile.skills}
    assert skill_names == {"Python", "FastAPI", "Kubernetes"}
    assert len(profile.education) == 1
    assert profile.education[0].school_name == "Delhi University"


def test_public_profile_parser_extracts_skills_from_summary():
    html = """
    <html>
    <head>
        <title>Alex Developer - Senior Engineer | LinkedIn</title>
        <script type="application/ld+json">
        {
            "@type": "Person",
            "name": "Alex Developer",
            "jobTitle": "Senior Software Engineer",
            "description": "Passionate backend engineer with expertise in Python, FastAPI, Docker, Kubernetes, and PostgreSQL."
        }
        </script>
    </head>
    <body>
    </body>
    </html>
    """
    profile = PublicProfileParser.parse(html, "alexdev", "https://www.linkedin.com/in/alexdev")
    assert profile.full_name == "Alex Developer"
    assert len(profile.skills) >= 4
    skill_names = {s.name for s in profile.skills}
    assert "Python" in skill_names
    assert "FastAPI" in skill_names
    assert "Docker" in skill_names
    assert "Kubernetes" in skill_names
    assert "PostgreSQL" in skill_names

