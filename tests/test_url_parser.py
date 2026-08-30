import pytest
from app.schemas.request import parse_linkedin_url, ProfileRequest


def test_parse_standard_linkedin_url():
    url = "https://www.linkedin.com/in/satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_trailing_slash():
    url = "https://www.linkedin.com/in/williamhgates/"
    assert parse_linkedin_url(url) == "williamhgates"


def test_parse_query_params():
    url = "https://linkedin.com/in/satyanadella?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3A12345&trk=public_profile"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_subdomain_country():
    url = "http://in.linkedin.com/in/johndoe-dev"
    assert parse_linkedin_url(url) == "johndoe-dev"


def test_parse_in_shorthand():
    url = "in/satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_slash_in_shorthand():
    url = "/in/satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_slash_username():
    url = "/satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_at_username():
    url = "@satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_bare_username():
    url = "satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_vanity_url_without_in():
    url = "https://www.linkedin.com/satyanadella"
    assert parse_linkedin_url(url) == "satyanadella"


def test_parse_empty_raises_error():
    with pytest.raises(ValueError):
        parse_linkedin_url("")


def test_profile_request_model_validation():
    req = ProfileRequest(url="/in/satyanadella/")
    assert req.public_id == "satyanadella"
