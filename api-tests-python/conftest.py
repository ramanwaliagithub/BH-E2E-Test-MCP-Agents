"""
Pytest configuration and fixtures for ReqRes API tests
"""

import os
import pytest
from dotenv import load_dotenv
from api.client import HTTPClient

# Load environment variables from .env.local if it exists
load_dotenv(".env.local")


@pytest.fixture(scope="session")
def env_config():
    """
    Session-scoped fixture providing test configuration
    Returns a dictionary with API base URL and API key
    """
    return {
        "base_url": os.getenv("REQRES_BASE_URL", "https://reqres.in/api"),
        "api_key": os.getenv("REQRES_API_KEY", "free_user_3HlAYBLKIFyDKC1h491e34cTl2A"),
        "timeout": int(os.getenv("REQUEST_TIMEOUT", "10000")) / 1000,  # Convert ms to seconds
    }


@pytest.fixture(scope="function")
def api_client(env_config):
    """
    Function-scoped fixture providing an HTTP client instance
    A new client is created for each test to ensure isolation
    """
    client = HTTPClient(
        base_url=env_config["base_url"],
        timeout=env_config["timeout"],
        custom_headers={"x-api-key": env_config["api_key"]},
    )
    yield client
    client.close()