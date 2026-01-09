import pytest
import pytest_asyncio
import asyncio
import sys
import os
from aiohttp import web
from aiohttp.test_utils import TestServer

# Add fiber-probe/src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../fiber-probe/src')))

from client import FederationClient

# Mock API Handlers
fail_counter = {} # node_id -> current failures

async def mock_api_handler(request):
    auth = request.headers.get("Authorization")
    if auth != "Bearer secret":
        return web.Response(status=401)
    
    batch_id = request.headers.get("X-Batch-ID")
    if not batch_id:
        return web.Response(status=400)
    
    # Flaky Simulation via Header
    node_id = (await request.json()).get("node_id")
    if node_id == "flaky-node":
        global fail_counter
        count = fail_counter.get(batch_id, 0)
        if count < 2: # Fail twice
            fail_counter[batch_id] = count + 1
            return web.Response(status=500)
        
    return web.json_response({"status": "accepted"}, status=202)

@pytest_asyncio.fixture
async def api_server():
    """Explicitly manage TestServer lifecycle with async fixture."""
    app = web.Application()
    app.router.add_post('/ingest', mock_api_handler)
    server = TestServer(app)
    
    # Start server
    await server.start_server()
    yield server
    # Stop server
    await server.close()

@pytest.mark.asyncio
async def test_federation_client_success(api_server):
    config = {
        "url": str(api_server.make_url('/ingest')),
        "auth": {"type": "bearer", "token_env": "TEST_TOKEN"},
        "retry": {"max_attempts": 1}
    }
    
    os.environ["TEST_TOKEN"] = "secret"
    client = FederationClient("test-target", config)
    
    # Use client session
    import aiohttp
    async with aiohttp.ClientSession() as session:
        success = await client.push_batch(
            session, 
            [{"latency": 10}], 
            "node-1"
        )
        assert success is True

@pytest.mark.asyncio
async def test_federation_client_auth_fail(api_server):
    config = {
        "url": str(api_server.make_url('/ingest')),
        "auth": {"type": "bearer", "token_env": "WRONG_TOKEN"},
    }
    
    os.environ["WRONG_TOKEN"] = "wrong"
    client = FederationClient("test-target", config)
    
    import aiohttp
    async with aiohttp.ClientSession() as session:
        success = await client.push_batch(
            session, 
            [{"latency": 10}], 
            "node-1"
        )
        assert success is False

@pytest.mark.asyncio
async def test_federation_client_retry_success(api_server):
    config = {
        "url": str(api_server.make_url('/ingest')),
        "auth": {"type": "bearer", "token_env": "TEST_TOKEN"},
        # Fast retry for test
        "retry": {"max_attempts": 3, "base_delay_ms": 10} 
    }
    
    import os
    os.environ["TEST_TOKEN"] = "secret"
    client = FederationClient("test-target", config)
    
    import aiohttp
    async with aiohttp.ClientSession() as session:
        # Should succeed after 2 failures (3rd attempt)
        success = await client.push_batch(
            session, 
            [{"latency": 10}], 
            "flaky-node"
        )
        assert success is True
