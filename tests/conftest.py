import pytest
from tests.utils.http_client import TestHttpClient
from tests.utils.sandbox_loader import SandboxLoader

@pytest.fixture(scope="session")
def client():
    return TestHttpClient()

@pytest.fixture(scope="session")
def sandbox():
    return SandboxLoader().load("dev")
