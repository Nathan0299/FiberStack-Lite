import httpx

class GrafanaClient:
    def __init__(self, url, auth=("admin", "admin")):
        self.url = url
        self.auth = auth

    async def get_firing_alerts(self):
        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.get(f"{self.url}/api/alertmanager/grafana/config/api/v1/alerts")
            response.raise_for_status()
            return response.json()

    async def query_dashboard_data(self, query):
        # Implementation for direct datasource queries via Grafana proxy
        pass
