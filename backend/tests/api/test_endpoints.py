"""TraceLit — API Health & Settings Endpoint Tests."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_health_endpoint(app):
    """Test the /health endpoint returns valid status."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_settings_config_endpoint(app):
    """Test the /api/v1/settings/config endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/settings/config")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "thresholds" in data
        assert "limits" in data


@pytest.mark.asyncio
async def test_settings_memory_endpoint(app):
    """Test the /api/v1/settings/memory endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/settings/memory")
        assert response.status_code == 200
        data = response.json()
        assert "level" in data
        assert "system_percent" in data
