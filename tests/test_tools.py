"""Offline coverage for the generated qui API tools."""

import json
import re

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.exceptions import ToolError

import qui_mcp


class Recorder:
    def __init__(self) -> None:
        self.request: httpx.Request | None = None
        self.response = httpx.Response(200, json={"ok": True})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.request = request
        return self.response


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest_asyncio.fixture
async def server(recorder: Recorder, monkeypatch: pytest.MonkeyPatch):
    client = qui_mcp.build_client(
        "https://qui.example.com",
        "test-key",
        transport=httpx.MockTransport(recorder.handler),
    )
    monkeypatch.setattr(qui_mcp, "_client", client)
    yield qui_mcp.mcp
    await client.aclose()


async def call(server, name: str, **arguments):
    async with Client(server) as client:
        return await client.call_tool(name, arguments)


@pytest.mark.parametrize("name,method,path", qui_mcp._ROUTES)
async def test_every_manifest_route(server, recorder, name, method, path):
    values = {
        "id": 2,
        "instanceID": 7,
        "hash": "abc def",
        "infohash": "abc def",
        "directoryID": 3,
        "runID": 4,
        "taskID": 5,
        "indexerID": 6,
        "fileIndex": 0,
        "activityId": 8,
        "ruleID": 9,
        "ruleName": "rule name",
        "licenseKey": "license key",
    }
    arguments = {key: values[key] for key in re.findall(r"\{([^}]+)\}", path)}
    arguments["body"] = {"value": 1}
    await call(server, name, arguments=arguments)
    assert recorder.request is not None
    assert recorder.request.method == method
    expected = re.sub(r"\{([^}]+)\}", lambda match: str(arguments[match.group(1)]).replace(" ", "%20"), path)
    assert recorder.request.url.raw_path == ("/api" + expected).encode()


async def test_query_params_and_body_are_forwarded(server, recorder):
    await call(
        server,
        "qui_list_torrents",
        arguments={"instanceID": 3, "params": {"filter": "downloading", "limit": 5}, "body": {"ignored": True}},
    )
    assert recorder.request is not None
    assert str(recorder.request.url.params) == "filter=downloading&limit=5"
    assert json.loads(recorder.request.content) == {"ignored": True}


async def test_api_key_header_is_sent(server, recorder):
    await call(server, "qui_get_version")
    assert recorder.request is not None
    assert recorder.request.headers["x-api-key"] == "test-key"


async def test_no_api_key_means_no_header(recorder, monkeypatch):
    client = qui_mcp.build_client(
        "https://qui.example.com", None, transport=httpx.MockTransport(recorder.handler)
    )
    monkeypatch.setattr(qui_mcp, "_client", client)
    await call(qui_mcp.mcp, "qui_get_version")
    assert recorder.request is not None
    assert "x-api-key" not in recorder.request.headers
    await client.aclose()


async def test_error_message_reaches_caller(server, recorder):
    recorder.response = httpx.Response(404, json={"message": "instance not found"})
    with pytest.raises(ToolError, match="instance not found"):
        await call(server, "qui_get_arr_instance", arguments={"id": 99})


async def test_non_json_error_does_not_crash(server, recorder):
    recorder.response = httpx.Response(502, text="Bad Gateway")
    with pytest.raises(ToolError, match="502"):
        await call(server, "qui_get_version")


async def test_no_content_is_structured(server, recorder):
    recorder.response = httpx.Response(204)
    result = await call(server, "qui_delete_api_key", arguments={"id": 2})
    assert result.data == {"status": "ok"}


def test_main_requires_qui_url(monkeypatch):
    monkeypatch.delenv("QUI_URL", raising=False)
    with pytest.raises(SystemExit):
        qui_mcp.main()
