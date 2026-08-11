"""Opt-in smoke tests for a live qui instance."""

import os

import pytest
from fastmcp import Client

import qui_mcp

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("QUI_URL"), reason="requires QUI_URL"),
]


@pytest.fixture(autouse=True)
async def configure_client():
    client = qui_mcp.build_client(os.environ["QUI_URL"], os.environ.get("QUI_API_KEY"))
    qui_mcp._client = client
    yield
    await client.aclose()


async def test_live_version():
    async with Client(qui_mcp.mcp) as client:
        result = await client.call_tool("qui_get_version", {})
    assert result.data is not None
