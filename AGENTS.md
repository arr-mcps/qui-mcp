# AGENTS.md — qui-mcp

MCP server exposing qui's JSON REST API as tools for monitoring and managing qBittorrent instances, torrents, automations, cross-seeding, RSS, backups, and related services. Uses FastMCP, `uv` for deps.

Exposed as **12 resource-scoped portmanteau tools**, not one tool per route — see "API wrapper conventions" below. A prior version registered all 214 routes individually (this was qui-mcp's biggest source of tool-count bloat in the fleet, even though `grep -c '@mcp.tool'` reported 0 since routes were registered via `mcp.tool()(tool)` calls, not decorators); that blew the MCP context budget (~214 tools × ~250 tokens ≈ 54k tokens just for this one server) and has been retired.

## Testing
- Offline suite: `make test` (or `uv run pytest`)
- Live integration (needs `QUI_URL`/`QUI_API_KEY`): `make test-integration`

## Release workflow
Always use the `make bump-*` targets to bump the version (`uv version --bump patch|minor|major`), which updates `pyproject.toml` and `uv.lock` together. Do NOT edit the version by hand.

- Bump: `make bump-patch` (or `bump-minor` / `bump-major`)
- Commit message is **just the version**, e.g. `0.1.2` — nothing else.
- Tag it `v<version>` (e.g. `v0.1.2`).
- Push main and the tag:
  ```
  git push origin main
  git push origin v<version>
  ```
- Deploy to the Proxmox host (root SSH key): pull the repo then reinstall the uv tool:
  ```
  ssh root@192.168.50.3 -- 'cd /root/qui-mcp && git fetch origin && git reset --hard origin/main'
  ssh root@192.168.50.3 -- 'cd /root/qui-mcp && uv tool install --force .'
  ```
  The host runs it via `uv tool install` → `/root/.local/bin/qui-mcp` (not from the repo). There is no `/home/savagecore/Documents/christopfarr/mcp/qui-mcp` copy.

## API wrapper conventions
- Add or remove API coverage in `_ROUTES`; do not hand-register duplicate tools.
- Route naming (internal, no longer an MCP tool name): `qui_` prefix and snake_case. `arguments.operation`'s dispatch resolves to a route via `spec_of`: path variables at top level of `arguments`, query values under `arguments.params`, JSON request data under `arguments.body`.
- Preserve `X-API-Key` authentication; omit the header when `QUI_API_KEY` is unset. Keep SSE/binary endpoints out of structured MCP tools.
- Keep `_req` as the single HTTP/error-handling path so error messages stay consistent and MockTransport tests remain straightforward.

## Portmanteau registration — **do not go back to one tool per route**
- `_GROUPS` buckets every `_ROUTES` name into one of 12 resource groups (`qui_torrents`, `qui_cross_seed`, `qui_system`, ...). `_register_tools()` registers exactly one MCP tool per group via `_register_group`, which wraps the group's routes in a single `dispatch(operation, arguments)` closure that calls `_invoke` with the resolved `(method, path)` spec. No route's HTTP behavior changes — grouping is purely a registration-time concern.
- `operation` is typed `Literal[<the group's route names>]`, so FastMCP/pydantic validates it against the real route list before `dispatch` ever runs — an invalid operation never reaches the group tool's body.
- Adding a new route: add its entry to `_ROUTES` as before, then add its name to exactly one group in `_GROUPS`. `tests/test_tools.py::test_all_routes_grouped` fails if you forget.
- New resource area big enough to need its own group (rare): add a new `_GROUPS` key. Keep the total group count at or under ~15 — that ceiling is the entire point of this pattern.
- If you're tempted to add a per-route `mcp.tool()` call outside `_register_group`, don't — every route must be reachable only via its group's `operation` enum. A 214-route server (one tool per route) previously cost ~54k tokens of system-prompt budget on every session start; the 12-tool grouped version costs roughly a tenth of that.
- Annotations: a group tool is `readOnlyHint=True` (`READ_ONLY`) only when *every* route in it is a GET. Mixed groups carry no hints — the per-route `DESTRUCTIVE` distinction (deletes/restores/bulk-actions) that the old per-tool registration made is no longer applied at the group level; it's still visible in each operation line's `METHOD path` in the group tool's description. `_is_destructive()` was removed as dead code along with it — if you want per-operation destructive hints back, they'd need to live in the operation-line text, not a `ToolAnnotations` hint, since one group mixes methods.