# qui-mcp

MCP server exposing [qui](https://github.com/autobrr/qui)'s JSON REST API as
tools for monitoring and managing qBittorrent instances, torrents,
automations, cross-seeding, RSS, backups, and related services.

Built with [FastMCP](https://gofastmcp.com). The initial release mirrors the
full JSON API route surface as one MCP tool per endpoint.

## Install

```bash
uv tool install qui_mcp-*.whl
```

Register with Claude Code:

```bash
claude mcp add qui \
  --env QUI_URL=https://your-qui-host \
  --env QUI_API_KEY=<api-key> \
  -- qui-mcp
```

From source:

```bash
uv sync
claude mcp add qui \
  --env QUI_URL=https://your-qui-host \
  --env QUI_API_KEY=<api-key> \
  -- uv run --directory /path/to/qui-mcp qui-mcp
```

## Configuration

| Env var | Required | Description |
|---|---|---|
| `QUI_URL` | yes | qui host, optionally including a reverse-proxy base path; `/api` is appended automatically |
| `QUI_API_KEY` | no | API key sent as `X-API-Key`; omit only when qui authentication is intentionally disabled |

Create API keys in qui under **Settings -> API Keys**. The server never logs
the key and sends no authentication header when it is unset.

## Tools

The server registers one tool for every supported JSON endpoint. This includes
instances, torrents, categories, tags, preferences, automations, RSS,
backups, orphan scans, cross-seed, Torznab, ARR integrations, notifications,
API-key management, logs, and application metadata.

Streaming endpoints and binary downloads are intentionally omitted because MCP
tool results are structured JSON values. Session-creation endpoints
(`/auth/setup`, `/auth/login`, and `/auth/logout`) are also omitted; use qui's
web UI for those flows.

Every tool accepts one optional `arguments` object:

```json
{
  "instanceID": 1,
  "hash": "torrent-info-hash",
  "params": {"filter": "downloading"},
  "body": {"value": "request payload"}
}
```

Path variables use their documented names. Query values belong in `params` and
JSON request payloads belong in `body`.

## Development

```bash
make help
make sync
make test
make build
```

`make test` uses only `httpx.MockTransport`. Live smoke tests require
`QUI_URL` and can be run with `make test-integration`.

The release workflow builds a wheel and source distribution when a `v*` tag is
pushed. Start at version `0.0.0`; use `make bump-patch`, commit, tag, and push
for the first release.
