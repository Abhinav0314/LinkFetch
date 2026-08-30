import pytest
from unittest.mock import AsyncMock, patch
from app.schemas.profile import ProfileData, Location, Position, Education, Skill


@pytest.fixture
def mock_profile_data():
    return ProfileData(
        public_id="satyanadella",
        profile_url="https://www.linkedin.com/in/satyanadella",
        first_name="Satya",
        last_name="Nadella",
        full_name="Satya Nadella",
        headline="Chairman and CEO at Microsoft",
        location=Location(city="Redmond", region="WA", country="United States", raw="Redmond, WA"),
        about="Chairman and CEO at Microsoft.",
        profile_picture_url="https://media.licdn.com/dms/image/sample.jpg",
        experience=[
            Position(
                title="Chairman and CEO",
                company_name="Microsoft",
                is_current=True,
            )
        ],
        education=[
            Education(
                school_name="University of Chicago",
                degree_name="MBA",
            )
        ],
        skills=[
            Skill(name="Cloud Computing", endorsement_count=99)
        ]
    )


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "cache" in data
    assert "session" in data


def test_post_profile_success(client, mock_profile_data):
    with patch("app.services.linkedin_client.linkedin_service.get_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (mock_profile_data, "voyager_api", False)

        response = client.post(
            "/api/v1/profile",
            json={"url": "https://www.linkedin.com/in/satyanadella"}
        )
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["data"]["public_id"] == "satyanadella"
        assert json_data["data"]["full_name"] == "Satya Nadella"
        assert json_data["metadata"]["strategy_used"] == "voyager_api"
        assert json_data["metadata"]["cached"] is False


def test_get_profile_success(client, mock_profile_data):
    with patch("app.services.linkedin_client.linkedin_service.get_profile", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = (mock_profile_data, "public_json_ld", True)

        response = client.get("/api/v1/profile?url=https://www.linkedin.com/in/satyanadella")
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["data"]["public_id"] == "satyanadella"
        assert json_data["metadata"]["cached"] is True


def test_invalid_url_returns_400(client):
    response = client.get("/api/v1/profile?url=")
    assert response.status_code in (400, 422)

    response2 = client.get("/api/v1/profile?url=https://other-site.com/user/test")
    assert response2.status_code == 400


def test_post_invalid_url_returns_422(client):
    response = client.post("/api/v1/profile", json={"url": ""})
    assert response.status_code == 422


def test_profile_not_found_returns_404(client):
    from fastapi import HTTPException
    with patch("app.services.linkedin_client.linkedin_service.get_profile", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HTTPException(status_code=404, detail="LinkedIn profile 'nonexistent' not found.")
        response = client.get("/api/v1/profile?url=nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


def test_profile_rate_limit_returns_429(client):
    from fastapi import HTTPException
    with patch("app.services.linkedin_client.linkedin_service.get_profile", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = HTTPException(status_code=429, detail="LinkedIn rate limit encountered.")
        response = client.get("/api/v1/profile?url=satyanadella")
        assert response.status_code == 429


def test_internal_server_error_returns_500(client):
    with patch("app.services.linkedin_client.linkedin_service.get_profile", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = RuntimeError("Network socket explosion")
        response = client.get("/api/v1/profile?url=satyanadella")
        assert response.status_code == 500
        # Verify internal error message does NOT leak internal exception details to client
        assert "internal server error" in response.json()["detail"].lower()
        assert "Network socket explosion" not in response.json()["detail"]


def test_serve_playground(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "LinkFetch API" in response.text


def test_serve_docs(client):
    response = client.get("/docs")
    assert response.status_code == 200
