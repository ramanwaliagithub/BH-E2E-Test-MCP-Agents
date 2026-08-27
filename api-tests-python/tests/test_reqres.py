"""
ReqRes API Tests using Python Requests

Tests cover:
- Happy Path 1: GET /users/1 returns 200 with valid user data structure
- Happy Path 2: POST /users returns 201 with name, job, id, createdAt
- Negative Case 1: GET /users/9999 returns 404 for non-existent user
- Negative Case 2: POST /users with missing name field returns 201
"""

import pytest


@pytest.mark.smoke
def test_get_user_returns_200(api_client):
    """
    Test successful GET user request - HAPPY PATH
    Verify response contains valid user data structure
    """
    response = api_client.get("/users/1")

    # Verify status code
    assert response.status_code == 200, "Expected 200 status code"

    # Verify response structure
    user = response.data.get("data")
    assert user is not None, "Response should contain 'data' field"

    # Verify user properties
    assert user.get("id") == 1, "User ID should be 1"
    assert "email" in user, "User should have email"
    assert "first_name" in user, "User should have first_name"
    assert "last_name" in user, "User should have last_name"
    assert "avatar" in user, "User should have avatar"


@pytest.mark.smoke
def test_create_user_returns_201(api_client):
    """
    Test successful POST create user request - HAPPY PATH
    Verify response includes created user data with generated id and timestamp
    """
    payload = {"name": "John Doe", "job": "QA Engineer"}

    response = api_client.post("/users", json=payload)

    # Verify status code
    assert response.status_code == 201, "Expected 201 status code for resource creation"

    # Verify response structure
    assert response.data.get("name") == payload["name"], "Response should echo provided name"
    assert response.data.get("job") == payload["job"], "Response should echo provided job"
    assert "id" in response.data, "Response should contain generated id"
    assert "createdAt" in response.data, "Response should contain createdAt timestamp"


@pytest.mark.regression
def test_get_nonexistent_user_returns_404(api_client):
    """
    Test GET request for non-existent user - NEGATIVE CASE
    Verify API returns 404 for invalid user ID
    """
    response = api_client.get("/users/9999")

    # Verify 404 status code
    assert response.status_code == 404, "Expected 404 status code for non-existent resource"

    # Verify response is empty (ReqRes returns empty object for 404)
    assert response.data == {} or response.data is None, "Response should be empty for 404"


@pytest.mark.regression
def test_create_user_with_missing_required_field(api_client):
    """
    Test POST create user with incomplete data - NEGATIVE CASE
    Note: ReqRes is lenient and accepts this; stricter APIs would reject it
    """
    payload = {"job": "QA Engineer"}  # Missing 'name' field

    response = api_client.post("/users", json=payload)

    # ReqRes accepts this and returns 201
    assert response.status_code == 201, "ReqRes accepts POST without name field"

    # Verify response structure
    assert "id" in response.data, "Response should contain generated id"
    assert "createdAt" in response.data, "Response should contain createdAt timestamp"
