# AGENTS.md — qui-mcp

MCP server exposing qui's JSON REST API as tools for monitoring and managing qBittorrent instances, torrents, automations, cross-seeding, RSS, backups, and related services. Uses FastMCP, `uv` for deps.

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
- Tool names use the `qui_` prefix and snake_case. Tool calls take an `arguments` object: path variables at top level, query values under `params`, JSON request data under `body`.
- Preserve `X-API-Key` authentication; omit the header when `QUI_API_KEY` is unset. Keep SSE/binary endpoints out of structured MCP tools.
- Use read-only annotations for GET routes and destructive annotations for deletes/operations that can remove or restore torrent data.
- Keep `_req` as the single HTTP/error-handling path so error messages stay consistent and MockTransport tests remain straightforward.