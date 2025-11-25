import requests

class TestHttpClient:
    """Lightweight test HTTP client wrapper."""

    def get(self, url):
        return requests.get(url)

    def post(self, url, json=None):
        return requests.post(url, json=json)
