import pytest
import requests

import os
API_URL = f"http://{os.getenv('API_HOST', 'localhost')}:8000/api"

def test_api_status_endpoint():
    """Verify API status endpoint returns 200 and valid JSON."""
    try:
        response = requests.get(f"{API_URL}/status")
    except requests.exceptions.ConnectionError:
        pytest.fail("API is not reachable at localhost:8000")
    
    assert response.status_code == 200
    try:
        data = response.json()
    except ValueError:
        pytest.fail("API response is not valid JSON")
        
    assert data.get("status") == "ok"
    assert "data" in data

def test_api_root():
    """Verify Root endpoint."""
    try:
        # Note: app.get("/") is mounted at root, not /api/
        response = requests.get(f"http://{os.getenv('API_HOST', 'localhost')}:8000/") 
    except requests.exceptions.ConnectionError:
        pytest.fail("API root is not reachable")

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
