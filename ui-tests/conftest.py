"""
Pytest configuration and fixtures for UI tests.

Browser/context/page lifecycle is provided by the pytest-playwright plugin:
one browser per test session, a fresh isolated context/page per test.
"""

import os
from pathlib import Path
import pytest
from dotenv import load_dotenv


# Load environment variables from .env.local
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Use default values for demo purposes
    os.environ.setdefault("SAUCE_DEMO_USERNAME", "standard_user")
    os.environ.setdefault("SAUCE_DEMO_PASSWORD", "secret_sauce")
    os.environ.setdefault("SAUCE_DEMO_URL", "https://www.saucedemo.com")
    os.environ.setdefault("HEADLESS", "true")


@pytest.fixture(scope="session")
def env_config():
    """Provide environment configuration as a fixture."""
    return {
        "username": os.getenv("SAUCE_DEMO_USERNAME", "standard_user"),
        "password": os.getenv("SAUCE_DEMO_PASSWORD", "secret_sauce"),
        "url": os.getenv("SAUCE_DEMO_URL", "https://www.saucedemo.com"),
        "headless": os.getenv("HEADLESS", "true").lower() == "true",
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(env_config):
    """Honor this project's HEADLESS env var instead of pytest-playwright's --headed flag."""
    return {"headless": env_config["headless"]}
