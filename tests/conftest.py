import pytest
import os
import asyncio
from tests.utils.http_client import TestHttpClient
from tests.utils.sandbox_loader import SandboxLoader
from tests.utils.db_helpers import DbAssertionHelper

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Mark slow tests
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests (require sandbox)")
    config.addinivalue_line("markers", "slow: slow running tests")


@pytest.fixture(scope="session")
def client():
    return TestHttpClient()

@pytest.fixture(scope="session")
def sandbox():
    return SandboxLoader().load("dev")

@pytest.fixture(scope="session")
def api_url():
    host = os.getenv("API_HOST", "localhost")
    return f"http://{host}:8000/api"


@pytest.fixture(scope="session")
def federation_secret():
    return os.getenv("FEDERATION_SECRET", "sandbox_secret")


@pytest.fixture(scope="session")
def db_helper():
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "postgres")
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "fiberstack")
    dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:5432/{db_name}"
    return DbAssertionHelper(dsn)

import httpx

@pytest.fixture
async def probe_token(api_url):
    """Get a valid JWT token for probe operations."""
    async with httpx.AsyncClient() as client:
        # Based on docker-compose USER_CREDENTIALS=...probe_user:probe_password
        response = await client.post(f"{api_url}/auth/login", json={
            "username": "probe_user",
            "password": "probe_password"
        })
        if response.status_code != 200:
            # Fallback to admin if probe_user doesn't exist
            response = await client.post(f"{api_url}/auth/login", json={
                "username": "admin",
                "password": "admin"
            })
        if response.status_code == 200:
             return response.json()["access_token"]
        return "mock_token" # Fallback to avoid complete crash if auth fails
