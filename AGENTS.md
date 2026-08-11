# qui-mcp Agent Guide

## Project

This repository is a Python FastMCP wrapper for qui's JSON REST API. Keep the
server in `qui_mcp.py` unless a change clearly requires a package layout.

## Development

- Use Python 3.11 or newer and `uv` for dependency management.
- Run `uv sync` before tests when dependencies are missing.
- Run `uv run pytest` for the offline suite.
- Run `uv run pytest -m integration` only with an explicitly configured live qui instance.
- Run `uv build` before release.
- Keep the project version at `0.0.0` until the first release bump.

## API wrapper conventions

- Add or remove API coverage in `_ROUTES`; do not hand-register duplicate tools.
- Tool names use the `qui_` prefix and snake_case.
- Tool calls accept an `arguments` object. Put path variables at its top level,
  query values under `params`, and JSON request data under `body`.
- Preserve `X-API-Key` authentication and omit the header when `QUI_API_KEY` is unset.
- Keep SSE and binary endpoints out of structured MCP tools.
- Use read-only annotations for GET routes and destructive annotations for
  deletes or operations that can remove/restore torrent data.
- Keep `_req` as the single HTTP/error-handling path so error messages remain
  consistent and MockTransport tests stay straightforward.

## Testing

Tests must not make network requests by default. Add route coverage through the
manifest parameterized test and add focused assertions for special query,
encoding, authentication, error, or no-content behavior when needed.

## Release

The release workflow is tag driven. Do not tag or push from routine changes.
The intended first release flow is `make bump-patch`, commit, tag `v0.0.1`, and
push.
