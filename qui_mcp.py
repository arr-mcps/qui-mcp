"""FastMCP server exposing qui's JSON REST API.

The route manifest below still mirrors qui's public API one endpoint at a
time (Streaming and binary endpoints are excluded because MCP tool results
are structured JSON values), but the manifest is now an internal routing
table rather than a 1:1 list of MCP tools. `_GROUPS` buckets the 214 routes
into 12 resource-scoped *portmanteau* tools; each takes an `operation` enum
(one of its group's route names) plus an ``arguments`` object. Path variables
are supplied by name in ``arguments``, query-string values go in
``arguments.params``, and request bodies go in ``arguments.body`` - exactly
as before, just addressed through the group tool instead of directly. See
AGENTS.md for the rationale (a 200+-tool server blows the MCP context budget
on session start).
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

JSONObj = dict[str, Any]
JSONVal = JSONObj | list[Any]
DESTRUCTIVE = ToolAnnotations(destructiveHint=True)
READ_ONLY = ToolAnnotations(readOnlyHint=True)

mcp = FastMCP("qui-mcp")
_client: httpx.AsyncClient | None = None


def build_client(
    base_url: str,
    api_key: str | None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.AsyncClient:
    headers = {"X-API-Key": api_key} if api_key else {}
    return httpx.AsyncClient(
        base_url=f"{base_url.rstrip('/')}/api",
        headers=headers,
        transport=transport,
    )


async def _req(
    method: str,
    path: str,
    *,
    params: JSONObj | None = None,
    json: Any = None,
) -> JSONVal:
    assert _client is not None, "client not configured"
    response = await _client.request(method, path, params=params, json=json)
    if response.status_code >= 400:
        try:
            payload = response.json()
            msg = payload.get("message", payload.get("error", response.text)) if isinstance(payload, dict) else response.text
        except ValueError:
            msg = response.text
        raise ToolError(f"qui API {response.status_code}: {msg}")
    if response.status_code == 204 or not response.content:
        return {"status": "ok"}
    try:
        payload = response.json()
    except ValueError as exc:
        raise ToolError("qui API returned a non-JSON success response") from exc
    return payload


def _path(template: str, arguments: JSONObj) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in arguments:
            raise ToolError(f"Missing path argument: {key}")
        return quote(str(arguments[key]), safe="")

    return re.sub(r"\{([^}]+)\}", replace, template)


async def _invoke(spec: tuple[str, str], arguments: JSONObj | None) -> JSONVal:
    arguments = arguments or {}
    method, template = spec
    path = _path(template, arguments)
    params = arguments.get("params")
    body = arguments.get("body")
    if params is None:
        params = {
            key: value
            for key, value in arguments.items()
            if key not in {"body", "params"} and not re.search(r"\{" + re.escape(key) + r"\}", template)
        }
        if not params:
            params = None
    return await _req(method, path, params=params, json=body)


# (tool name, HTTP method, API path).  Binary and SSE endpoints are omitted.
_ROUTES: tuple[tuple[str, str, str], ...] = (
    # Auth and account
    ("qui_check_setup", "GET", "/auth/check-setup"),
    ("qui_get_current_user", "GET", "/auth/me"),
    ("qui_validate_session", "GET", "/auth/validate"),
    ("qui_change_password", "PUT", "/auth/change-password"),
    ("qui_list_api_keys", "GET", "/api-keys/"),
    ("qui_create_api_key", "POST", "/api-keys/"),
    ("qui_delete_api_key", "DELETE", "/api-keys/{id}"),
    ("qui_list_client_api_keys", "GET", "/client-api-keys/"),
    ("qui_create_client_api_key", "POST", "/client-api-keys/"),
    ("qui_delete_client_api_key", "DELETE", "/client-api-keys/{id}"),
    # General management
    ("qui_list_external_programs", "GET", "/external-programs/"),
    ("qui_create_external_program", "POST", "/external-programs/"),
    ("qui_update_external_program", "PUT", "/external-programs/{id}"),
    ("qui_delete_external_program", "DELETE", "/external-programs/{id}"),
    ("qui_execute_external_program", "POST", "/external-programs/execute"),
    ("qui_list_notification_events", "GET", "/notifications/events"),
    ("qui_list_notification_targets", "GET", "/notifications/targets"),
    ("qui_create_notification_target", "POST", "/notifications/targets"),
    ("qui_update_notification_target", "PUT", "/notifications/targets/{id}"),
    ("qui_delete_notification_target", "DELETE", "/notifications/targets/{id}"),
    ("qui_test_notification_target", "POST", "/notifications/targets/{id}/test"),
    ("qui_list_arr_instances", "GET", "/arr/instances"),
    ("qui_create_arr_instance", "POST", "/arr/instances"),
    ("qui_get_arr_instance", "GET", "/arr/instances/{id}"),
    ("qui_update_arr_instance", "PUT", "/arr/instances/{id}"),
    ("qui_delete_arr_instance", "DELETE", "/arr/instances/{id}"),
    ("qui_test_arr_instance", "POST", "/arr/instances/{id}/test"),
    ("qui_test_arr_connection", "POST", "/arr/test"),
    ("qui_resolve_arr", "POST", "/arr/resolve"),
    ("qui_list_tracker_customizations", "GET", "/tracker-customizations/"),
    ("qui_create_tracker_customization", "POST", "/tracker-customizations/"),
    ("qui_update_tracker_customization", "PUT", "/tracker-customizations/{id}"),
    ("qui_delete_tracker_customization", "DELETE", "/tracker-customizations/{id}"),
    ("qui_get_dashboard_settings", "GET", "/dashboard-settings"),
    ("qui_update_dashboard_settings", "PUT", "/dashboard-settings"),
    ("qui_list_filter_views", "GET", "/filter-views/"),
    ("qui_create_filter_view", "POST", "/filter-views/"),
    ("qui_update_filter_view", "PUT", "/filter-views/{id}"),
    ("qui_delete_filter_view", "DELETE", "/filter-views/{id}"),
    ("qui_get_log_exclusions", "GET", "/log-exclusions"),
    ("qui_update_log_exclusions", "PUT", "/log-exclusions"),
    ("qui_get_log_settings", "GET", "/log-settings"),
    ("qui_update_log_settings", "PUT", "/log-settings"),
    ("qui_list_log_files", "GET", "/logs/files"),
    ("qui_get_version", "GET", "/version"),
    ("qui_get_latest_version", "GET", "/version/latest"),
    ("qui_get_application_info", "GET", "/application/info"),
    ("qui_get_tracker_icons", "GET", "/tracker-icons"),
    ("qui_list_custom_themes", "GET", "/themes/custom"),
    # Global services
    ("qui_list_cross_instance_torrents", "GET", "/torrents/cross-instance"),
    ("qui_get_dir_scan_settings", "GET", "/dir-scan/settings"),
    ("qui_update_dir_scan_settings", "PATCH", "/dir-scan/settings"),
    ("qui_list_scan_directories", "GET", "/dir-scan/directories/"),
    ("qui_create_scan_directory", "POST", "/dir-scan/directories/"),
    ("qui_get_scan_directory", "GET", "/dir-scan/directories/{directoryID}"),
    ("qui_update_scan_directory", "PATCH", "/dir-scan/directories/{directoryID}"),
    ("qui_delete_scan_directory", "DELETE", "/dir-scan/directories/{directoryID}"),
    ("qui_reset_scan_directory_files", "POST", "/dir-scan/directories/{directoryID}/reset-files"),
    ("qui_requeue_scan_directory_no_match", "POST", "/dir-scan/directories/{directoryID}/requeue-no-match"),
    ("qui_scan_directory", "POST", "/dir-scan/directories/{directoryID}/scan"),
    ("qui_cancel_directory_scan", "DELETE", "/dir-scan/directories/{directoryID}/scan"),
    ("qui_get_scan_directory_status", "GET", "/dir-scan/directories/{directoryID}/status"),
    ("qui_list_scan_directory_runs", "GET", "/dir-scan/directories/{directoryID}/runs"),
    ("qui_list_scan_run_injections", "GET", "/dir-scan/directories/{directoryID}/runs/{runID}/injections"),
    ("qui_list_scan_directory_files", "GET", "/dir-scan/directories/{directoryID}/files"),
    # Cross-seed
    ("qui_get_instance_cross_seed_status", "GET", "/instances/{instanceID}/cross-seed/status"),
    ("qui_cross_seed_apply", "POST", "/cross-seed/apply"),
    ("qui_cross_seed_webhook_check", "POST", "/cross-seed/webhook/check"),
    ("qui_analyze_cross_seed_torrent", "GET", "/cross-seed/torrents/{instanceID}/{hash}/analyze"),
    ("qui_get_cross_seed_async_status", "GET", "/cross-seed/torrents/{instanceID}/{hash}/async-status"),
    ("qui_get_cross_seed_local_matches", "GET", "/cross-seed/torrents/{instanceID}/{hash}/local-matches"),
    ("qui_search_cross_seed_torrent", "POST", "/cross-seed/torrents/{instanceID}/{hash}/search"),
    ("qui_apply_cross_seed_search", "POST", "/cross-seed/torrents/{instanceID}/{hash}/apply"),
    ("qui_get_cross_seed_settings", "GET", "/cross-seed/settings"),
    ("qui_patch_cross_seed_settings", "PATCH", "/cross-seed/settings"),
    ("qui_update_cross_seed_settings", "PUT", "/cross-seed/settings"),
    ("qui_get_cross_seed_status", "GET", "/cross-seed/status"),
    ("qui_list_cross_seed_runs", "GET", "/cross-seed/runs"),
    ("qui_run_cross_seed_automation", "POST", "/cross-seed/run"),
    ("qui_cancel_cross_seed_automation", "POST", "/cross-seed/run/cancel"),
    ("qui_list_cross_seed_blocklist", "GET", "/cross-seed/blocklist/"),
    ("qui_add_cross_seed_blocklist_entry", "POST", "/cross-seed/blocklist/"),
    ("qui_delete_cross_seed_blocklist_entry", "DELETE", "/cross-seed/blocklist/{instanceID}/{infohash}"),
    ("qui_get_cross_seed_search_settings", "GET", "/cross-seed/search/settings"),
    ("qui_patch_cross_seed_search_settings", "PATCH", "/cross-seed/search/settings"),
    ("qui_get_cross_seed_search_status", "GET", "/cross-seed/search/status"),
    ("qui_start_cross_seed_search", "POST", "/cross-seed/search/run"),
    ("qui_cancel_cross_seed_search", "POST", "/cross-seed/search/run/cancel"),
    ("qui_list_cross_seed_search_runs", "GET", "/cross-seed/search/runs"),
    ("qui_get_cross_seed_completion", "GET", "/cross-seed/completion/{instanceID}"),
    ("qui_update_cross_seed_completion", "PUT", "/cross-seed/completion/{instanceID}"),
    ("qui_check_cross_seed_season_pack", "POST", "/cross-seed/season-pack/check"),
    ("qui_apply_cross_seed_season_pack", "POST", "/cross-seed/season-pack/apply"),
    ("qui_list_cross_seed_season_pack_runs", "GET", "/cross-seed/season-pack/runs"),
    # Torznab
    ("qui_list_torznab_indexers", "GET", "/torznab/indexers/"),
    ("qui_create_torznab_indexer", "POST", "/torznab/indexers/"),
    ("qui_discover_torznab_indexers", "POST", "/torznab/indexers/discover"),
    ("qui_get_torznab_all_health", "GET", "/torznab/indexers/health"),
    ("qui_get_torznab_tracker_domains", "GET", "/torznab/indexers/tracker-domains"),
    ("qui_get_torznab_indexer", "GET", "/torznab/indexers/{indexerID}"),
    ("qui_update_torznab_indexer", "PUT", "/torznab/indexers/{indexerID}"),
    ("qui_delete_torznab_indexer", "DELETE", "/torznab/indexers/{indexerID}"),
    ("qui_test_torznab_indexer", "POST", "/torznab/indexers/{indexerID}/test"),
    ("qui_sync_torznab_indexer_caps", "POST", "/torznab/indexers/{indexerID}/caps/sync"),
    ("qui_get_torznab_indexer_health", "GET", "/torznab/indexers/{indexerID}/health"),
    ("qui_get_torznab_indexer_errors", "GET", "/torznab/indexers/{indexerID}/errors"),
    ("qui_get_torznab_indexer_stats", "GET", "/torznab/indexers/{indexerID}/stats"),
    ("qui_search_torznab_cross_seed", "POST", "/torznab/cross-seed/search"),
    ("qui_list_recent_torznab_searches", "GET", "/torznab/search/recent"),
    ("qui_search_torznab", "POST", "/torznab/search"),
    ("qui_get_torznab_search_cache", "GET", "/torznab/search/cache/"),
    ("qui_update_torznab_search_cache_settings", "PUT", "/torznab/search/cache/settings"),
    ("qui_get_torznab_search_history", "GET", "/torznab/search/history"),
    ("qui_get_torznab_activity", "GET", "/torznab/activity"),
    # Licenses
    ("qui_get_licensed_status", "GET", "/license/licensed"),
    ("qui_list_licenses", "GET", "/license/licenses"),
    ("qui_activate_license", "POST", "/license/activate"),
    ("qui_validate_license", "POST", "/license/validate"),
    ("qui_refresh_licenses", "POST", "/license/refresh"),
    ("qui_delete_license", "DELETE", "/license/{licenseKey}"),
    # Instances
    ("qui_list_instances", "GET", "/instances/"),
    ("qui_create_instance", "POST", "/instances/"),
    ("qui_update_instance_order", "PUT", "/instances/order"),
    ("qui_update_instance_status", "PUT", "/instances/{instanceID}/status"),
    ("qui_update_instance", "PUT", "/instances/{instanceID}/"),
    ("qui_delete_instance", "DELETE", "/instances/{instanceID}/"),
    ("qui_test_instance", "POST", "/instances/{instanceID}/test"),
    ("qui_get_instance_mediainfo", "GET", "/instances/{instanceID}/mediainfo"),
    ("qui_get_instance_capabilities", "GET", "/instances/{instanceID}/capabilities"),
    ("qui_get_instance_transfer_info", "GET", "/instances/{instanceID}/transfer-info"),
    ("qui_get_reannounce_activity", "GET", "/instances/{instanceID}/reannounce/activity"),
    ("qui_get_reannounce_candidates", "GET", "/instances/{instanceID}/reannounce/candidates"),
    ("qui_get_instance_app_info", "GET", "/instances/{instanceID}/app-info"),
    ("qui_get_directory_content", "GET", "/instances/{instanceID}/getDirectoryContent"),
    ("qui_get_alternative_speed_limits", "GET", "/instances/{instanceID}/alternative-speed-limits"),
    ("qui_toggle_alternative_speed_limits", "POST", "/instances/{instanceID}/alternative-speed-limits/toggle"),
    ("qui_get_preferences", "GET", "/instances/{instanceID}/preferences"),
    ("qui_update_preferences", "PATCH", "/instances/{instanceID}/preferences"),
    # Torrent operations
    ("qui_list_torrents", "GET", "/instances/{instanceID}/torrents/"),
    ("qui_add_torrent", "POST", "/instances/{instanceID}/torrents/"),
    ("qui_check_duplicate_torrents", "POST", "/instances/{instanceID}/torrents/check-duplicates"),
    ("qui_torrent_bulk_action", "POST", "/instances/{instanceID}/torrents/bulk-action"),
    ("qui_add_peers", "POST", "/instances/{instanceID}/torrents/add-peers"),
    ("qui_ban_peers", "POST", "/instances/{instanceID}/torrents/ban-peers"),
    ("qui_get_torrent_field", "POST", "/instances/{instanceID}/torrents/field"),
    ("qui_get_torrent_properties", "GET", "/instances/{instanceID}/torrents/{hash}/properties"),
    ("qui_get_torrent_trackers", "GET", "/instances/{instanceID}/torrents/{hash}/trackers"),
    ("qui_edit_torrent_tracker", "PUT", "/instances/{instanceID}/torrents/{hash}/trackers"),
    ("qui_add_torrent_trackers", "POST", "/instances/{instanceID}/torrents/{hash}/trackers"),
    ("qui_remove_torrent_trackers", "DELETE", "/instances/{instanceID}/torrents/{hash}/trackers"),
    ("qui_get_torrent_peers", "GET", "/instances/{instanceID}/torrents/{hash}/peers"),
    ("qui_get_torrent_webseeds", "GET", "/instances/{instanceID}/torrents/{hash}/webseeds"),
    ("qui_get_torrent_pieces", "GET", "/instances/{instanceID}/torrents/{hash}/pieces"),
    ("qui_get_torrent_files", "GET", "/instances/{instanceID}/torrents/{hash}/files"),
    ("qui_set_torrent_file_priority", "PUT", "/instances/{instanceID}/torrents/{hash}/files"),
    ("qui_rename_torrent", "PUT", "/instances/{instanceID}/torrents/{hash}/rename"),
    ("qui_rename_torrent_file", "PUT", "/instances/{instanceID}/torrents/{hash}/rename-file"),
    ("qui_rename_torrent_folder", "PUT", "/instances/{instanceID}/torrents/{hash}/rename-folder"),
    ("qui_get_torrent_file_mediainfo", "GET", "/instances/{instanceID}/torrents/{hash}/files/{fileIndex}/mediainfo"),
    # Torrent creator, categories, tags, trackers
    ("qui_create_torrent", "POST", "/instances/{instanceID}/torrent-creator/"),
    ("qui_get_torrent_creation_status", "GET", "/instances/{instanceID}/torrent-creator/status"),
    ("qui_get_active_torrent_creation_count", "GET", "/instances/{instanceID}/torrent-creator/count"),
    ("qui_delete_torrent_creation_task", "DELETE", "/instances/{instanceID}/torrent-creator/{taskID}"),
    ("qui_get_categories", "GET", "/instances/{instanceID}/categories"),
    ("qui_create_category", "POST", "/instances/{instanceID}/categories"),
    ("qui_edit_category", "PUT", "/instances/{instanceID}/categories"),
    ("qui_remove_categories", "DELETE", "/instances/{instanceID}/categories"),
    ("qui_get_tags", "GET", "/instances/{instanceID}/tags"),
    ("qui_create_tags", "POST", "/instances/{instanceID}/tags"),
    ("qui_delete_tags", "DELETE", "/instances/{instanceID}/tags"),
    ("qui_get_active_trackers", "GET", "/instances/{instanceID}/trackers"),
    # Automations
    ("qui_list_automations", "GET", "/instances/{instanceID}/automations/"),
    ("qui_create_automation", "POST", "/instances/{instanceID}/automations/"),
    ("qui_reorder_automations", "PUT", "/instances/{instanceID}/automations/order"),
    ("qui_apply_automations", "POST", "/instances/{instanceID}/automations/apply"),
    ("qui_dry_run_automations", "POST", "/instances/{instanceID}/automations/dry-run"),
    ("qui_preview_automation_delete", "POST", "/instances/{instanceID}/automations/preview"),
    ("qui_validate_automation_regex", "POST", "/instances/{instanceID}/automations/validate-regex"),
    ("qui_list_automation_activity", "GET", "/instances/{instanceID}/automations/activity"),
    ("qui_get_automation_activity_run", "GET", "/instances/{instanceID}/automations/activity/{activityId}"),
    ("qui_delete_automation_activity", "DELETE", "/instances/{instanceID}/automations/activity"),
    ("qui_update_automation", "PUT", "/instances/{instanceID}/automations/{ruleID}"),
    ("qui_delete_automation", "DELETE", "/instances/{instanceID}/automations/{ruleID}"),
    # RSS
    ("qui_get_rss_items", "GET", "/instances/{instanceID}/rss/items"),
    ("qui_add_rss_folder", "POST", "/instances/{instanceID}/rss/folders"),
    ("qui_add_rss_feed", "POST", "/instances/{instanceID}/rss/feeds"),
    ("qui_set_rss_feed_url", "PUT", "/instances/{instanceID}/rss/feeds/url"),
    ("qui_move_rss_item", "POST", "/instances/{instanceID}/rss/items/move"),
    ("qui_remove_rss_item", "DELETE", "/instances/{instanceID}/rss/items"),
    ("qui_refresh_rss_item", "POST", "/instances/{instanceID}/rss/items/refresh"),
    ("qui_mark_rss_article_read", "POST", "/instances/{instanceID}/rss/articles/read"),
    ("qui_get_rss_rules", "GET", "/instances/{instanceID}/rss/rules"),
    ("qui_set_rss_rule", "POST", "/instances/{instanceID}/rss/rules"),
    ("qui_rename_rss_rule", "PUT", "/instances/{instanceID}/rss/rules/{ruleName}/rename"),
    ("qui_remove_rss_rule", "DELETE", "/instances/{instanceID}/rss/rules/{ruleName}"),
    ("qui_preview_rss_rule_matches", "GET", "/instances/{instanceID}/rss/rules/{ruleName}/preview"),
    ("qui_reprocess_rss_rules", "POST", "/instances/{instanceID}/rss/rules/reprocess"),
    # Backups
    ("qui_get_backup_settings", "GET", "/instances/{instanceID}/backups/settings"),
    ("qui_update_backup_settings", "PUT", "/instances/{instanceID}/backups/settings"),
    ("qui_import_backup_manifest", "POST", "/instances/{instanceID}/backups/import"),
    ("qui_trigger_backup", "POST", "/instances/{instanceID}/backups/run"),
    ("qui_list_backup_runs", "GET", "/instances/{instanceID}/backups/runs"),
    ("qui_delete_all_backup_runs", "DELETE", "/instances/{instanceID}/backups/runs"),
    ("qui_get_backup_manifest", "GET", "/instances/{instanceID}/backups/runs/{runID}/manifest"),
    ("qui_preview_backup_restore", "POST", "/instances/{instanceID}/backups/runs/{runID}/restore/preview"),
    ("qui_execute_backup_restore", "POST", "/instances/{instanceID}/backups/runs/{runID}/restore"),
    ("qui_delete_backup_run", "DELETE", "/instances/{instanceID}/backups/runs/{runID}"),
    # Orphan scan
    ("qui_get_orphan_scan_settings", "GET", "/instances/{instanceID}/orphan-scan/settings"),
    ("qui_update_orphan_scan_settings", "PUT", "/instances/{instanceID}/orphan-scan/settings"),
    ("qui_trigger_orphan_scan", "POST", "/instances/{instanceID}/orphan-scan/scan"),
    ("qui_list_orphan_scan_runs", "GET", "/instances/{instanceID}/orphan-scan/runs"),
    ("qui_get_orphan_scan_run", "GET", "/instances/{instanceID}/orphan-scan/runs/{runID}"),
    ("qui_confirm_orphan_deletion", "POST", "/instances/{instanceID}/orphan-scan/runs/{runID}/confirm"),
    ("qui_cancel_orphan_scan", "DELETE", "/instances/{instanceID}/orphan-scan/runs/{runID}"),
)


# Resource groups for portmanteau registration. Every _ROUTES name must
# appear in exactly one group - see test_all_routes_grouped.
_GROUPS: dict[str, tuple[str, ...]] = {
    "qui_system": (
        'qui_activate_license',
        'qui_change_password',
        'qui_check_setup',
        'qui_create_api_key',
        'qui_create_arr_instance',
        'qui_create_client_api_key',
        'qui_create_external_program',
        'qui_create_filter_view',
        'qui_create_notification_target',
        'qui_create_tracker_customization',
        'qui_delete_api_key',
        'qui_delete_arr_instance',
        'qui_delete_client_api_key',
        'qui_delete_external_program',
        'qui_delete_filter_view',
        'qui_delete_license',
        'qui_delete_notification_target',
        'qui_delete_tracker_customization',
        'qui_execute_external_program',
        'qui_get_application_info',
        'qui_get_arr_instance',
        'qui_get_current_user',
        'qui_get_dashboard_settings',
        'qui_get_latest_version',
        'qui_get_licensed_status',
        'qui_get_log_exclusions',
        'qui_get_log_settings',
        'qui_get_tracker_icons',
        'qui_get_version',
        'qui_list_api_keys',
        'qui_list_arr_instances',
        'qui_list_client_api_keys',
        'qui_list_custom_themes',
        'qui_list_external_programs',
        'qui_list_filter_views',
        'qui_list_licenses',
        'qui_list_log_files',
        'qui_list_notification_events',
        'qui_list_notification_targets',
        'qui_list_tracker_customizations',
        'qui_refresh_licenses',
        'qui_resolve_arr',
        'qui_test_arr_connection',
        'qui_test_arr_instance',
        'qui_test_notification_target',
        'qui_update_arr_instance',
        'qui_update_dashboard_settings',
        'qui_update_external_program',
        'qui_update_filter_view',
        'qui_update_log_exclusions',
        'qui_update_log_settings',
        'qui_update_notification_target',
        'qui_update_tracker_customization',
        'qui_validate_license',
        'qui_validate_session',
    ),
    "qui_cross_seed": (
        'qui_add_cross_seed_blocklist_entry',
        'qui_analyze_cross_seed_torrent',
        'qui_apply_cross_seed_search',
        'qui_apply_cross_seed_season_pack',
        'qui_cancel_cross_seed_automation',
        'qui_cancel_cross_seed_search',
        'qui_check_cross_seed_season_pack',
        'qui_cross_seed_apply',
        'qui_cross_seed_webhook_check',
        'qui_delete_cross_seed_blocklist_entry',
        'qui_get_cross_seed_async_status',
        'qui_get_cross_seed_completion',
        'qui_get_cross_seed_local_matches',
        'qui_get_cross_seed_search_settings',
        'qui_get_cross_seed_search_status',
        'qui_get_cross_seed_settings',
        'qui_get_cross_seed_status',
        'qui_get_instance_cross_seed_status',
        'qui_list_cross_seed_blocklist',
        'qui_list_cross_seed_runs',
        'qui_list_cross_seed_search_runs',
        'qui_list_cross_seed_season_pack_runs',
        'qui_patch_cross_seed_search_settings',
        'qui_patch_cross_seed_settings',
        'qui_run_cross_seed_automation',
        'qui_search_cross_seed_torrent',
        'qui_start_cross_seed_search',
        'qui_update_cross_seed_completion',
        'qui_update_cross_seed_settings',
    ),
    "qui_torrents": (
        'qui_add_peers',
        'qui_add_torrent',
        'qui_add_torrent_trackers',
        'qui_ban_peers',
        'qui_check_duplicate_torrents',
        'qui_edit_torrent_tracker',
        'qui_get_reannounce_activity',
        'qui_get_reannounce_candidates',
        'qui_get_torrent_field',
        'qui_get_torrent_file_mediainfo',
        'qui_get_torrent_files',
        'qui_get_torrent_peers',
        'qui_get_torrent_pieces',
        'qui_get_torrent_properties',
        'qui_get_torrent_trackers',
        'qui_get_torrent_webseeds',
        'qui_list_cross_instance_torrents',
        'qui_list_torrents',
        'qui_remove_torrent_trackers',
        'qui_rename_torrent',
        'qui_rename_torrent_file',
        'qui_rename_torrent_folder',
        'qui_set_torrent_file_priority',
        'qui_torrent_bulk_action',
    ),
    "qui_torznab": (
        'qui_create_torznab_indexer',
        'qui_delete_torznab_indexer',
        'qui_discover_torznab_indexers',
        'qui_get_torznab_activity',
        'qui_get_torznab_all_health',
        'qui_get_torznab_indexer',
        'qui_get_torznab_indexer_errors',
        'qui_get_torznab_indexer_health',
        'qui_get_torznab_indexer_stats',
        'qui_get_torznab_search_cache',
        'qui_get_torznab_search_history',
        'qui_get_torznab_tracker_domains',
        'qui_list_recent_torznab_searches',
        'qui_list_torznab_indexers',
        'qui_search_torznab',
        'qui_search_torznab_cross_seed',
        'qui_sync_torznab_indexer_caps',
        'qui_test_torznab_indexer',
        'qui_update_torznab_indexer',
        'qui_update_torznab_search_cache_settings',
    ),
    "qui_instances": (
        'qui_create_instance',
        'qui_delete_instance',
        'qui_get_active_trackers',
        'qui_get_alternative_speed_limits',
        'qui_get_directory_content',
        'qui_get_instance_app_info',
        'qui_get_instance_capabilities',
        'qui_get_instance_mediainfo',
        'qui_get_instance_transfer_info',
        'qui_get_preferences',
        'qui_list_instances',
        'qui_test_instance',
        'qui_toggle_alternative_speed_limits',
        'qui_update_instance',
        'qui_update_instance_order',
        'qui_update_instance_status',
        'qui_update_preferences',
    ),
    "qui_dir_scan": (
        'qui_cancel_directory_scan',
        'qui_create_scan_directory',
        'qui_delete_scan_directory',
        'qui_get_dir_scan_settings',
        'qui_get_scan_directory',
        'qui_get_scan_directory_status',
        'qui_list_scan_directories',
        'qui_list_scan_directory_files',
        'qui_list_scan_directory_runs',
        'qui_list_scan_run_injections',
        'qui_requeue_scan_directory_no_match',
        'qui_reset_scan_directory_files',
        'qui_scan_directory',
        'qui_update_dir_scan_settings',
        'qui_update_scan_directory',
    ),
    "qui_rss": (
        'qui_add_rss_feed',
        'qui_add_rss_folder',
        'qui_get_rss_items',
        'qui_get_rss_rules',
        'qui_mark_rss_article_read',
        'qui_move_rss_item',
        'qui_preview_rss_rule_matches',
        'qui_refresh_rss_item',
        'qui_remove_rss_item',
        'qui_remove_rss_rule',
        'qui_rename_rss_rule',
        'qui_reprocess_rss_rules',
        'qui_set_rss_feed_url',
        'qui_set_rss_rule',
    ),
    "qui_automations": (
        'qui_apply_automations',
        'qui_create_automation',
        'qui_delete_automation',
        'qui_delete_automation_activity',
        'qui_dry_run_automations',
        'qui_get_automation_activity_run',
        'qui_list_automation_activity',
        'qui_list_automations',
        'qui_preview_automation_delete',
        'qui_reorder_automations',
        'qui_update_automation',
        'qui_validate_automation_regex',
    ),
    "qui_backups": (
        'qui_delete_all_backup_runs',
        'qui_delete_backup_run',
        'qui_execute_backup_restore',
        'qui_get_backup_manifest',
        'qui_get_backup_settings',
        'qui_import_backup_manifest',
        'qui_list_backup_runs',
        'qui_preview_backup_restore',
        'qui_trigger_backup',
        'qui_update_backup_settings',
    ),
    "qui_categories_tags": (
        'qui_create_category',
        'qui_create_tags',
        'qui_delete_tags',
        'qui_edit_category',
        'qui_get_categories',
        'qui_get_tags',
        'qui_remove_categories',
    ),
    "qui_orphan_scan": (
        'qui_cancel_orphan_scan',
        'qui_confirm_orphan_deletion',
        'qui_get_orphan_scan_run',
        'qui_get_orphan_scan_settings',
        'qui_list_orphan_scan_runs',
        'qui_trigger_orphan_scan',
        'qui_update_orphan_scan_settings',
    ),
    "qui_torrent_creator": (
        'qui_create_torrent',
        'qui_delete_torrent_creation_task',
        'qui_get_active_torrent_creation_count',
        'qui_get_torrent_creation_status',
    ),
}


def _register_group(group: str, names: tuple[str, ...], spec_of: dict[str, tuple[str, str]]) -> None:
    """Register one dispatching tool that fans out to every route named in
    `names`, calling the same `_invoke` each individual tool used to call."""
    specs = {n: spec_of[n] for n in names}

    async def dispatch(operation: str, arguments: JSONObj | None = None) -> JSONVal:
        spec = specs.get(operation)
        if spec is None:
            raise ToolError(f"Unknown operation {operation!r} for {group}. Valid: {', '.join(specs)}")
        return await _invoke(spec, arguments)

    dispatch.__annotations__["operation"] = Literal[names]
    ann = READ_ONLY if all(method == "GET" for method, _ in specs.values()) else None
    description = (
        f"{group.replace('_', ' ')} operations on qui. Pass `operation` and an `arguments` "
        "object; path variables go directly in arguments, query values in arguments.params, "
        "and a JSON request body in arguments.body.\n\n"
        + "\n".join(f"- {n}: {m} {p}" for n, (m, p) in sorted(specs.items()))
    )
    kwargs: dict[str, Any] = {"name": group, "description": description}
    if ann is not None:
        kwargs["annotations"] = ann
    mcp.tool(**kwargs)(dispatch)


def _register_tools() -> None:
    seen: set[str] = set()
    for name, _method, _path in _ROUTES:
        if name in seen:
            raise RuntimeError(f"duplicate MCP tool name: {name}")
        seen.add(name)
    spec_of = {name: (method, path) for name, method, path in _ROUTES}
    for group, names in _GROUPS.items():
        _register_group(group, names, spec_of)


_register_tools()


def main() -> None:
    global _client
    url = os.environ.get("QUI_URL")
    if not url:
        print("QUI_URL environment variable is required (e.g. https://qui.example.com)", file=sys.stderr)
        raise SystemExit(1)
    _client = build_client(url, os.environ.get("QUI_API_KEY"))
    mcp.run()


if __name__ == "__main__":
    main()
