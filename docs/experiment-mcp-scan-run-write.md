# Experiment: Safe MCP Scan Run Write Tool

## What changed
- Added `create_scan_run` to MCP tools so API-only agents can start rank scans without using the UI.
- Added `localrank_mcp/scan_write.py` with strict input validation and duplicate-risk blocking.
- Wired the tool into `localrank_mcp/__init__.py` with structured transaction logging (`flow: mcp_tool_scan_run`).
- Added focused unit tests in `tests/test_scan_write.py`.
- Updated README tool docs and guardrail documentation.

## Why
- Usage analysis showed scan starts (`POST /api/scans/`) are the highest-value write action for API-only workflows.
- MCP had scan read tools but no safe scan start path, forcing UI dependence.

## Root cause
- The current MCP surface only exposed scan retrieval (`list_scans`, `get_scan`).
- Without a write entrypoint, agents could not execute the core scan lifecycle through API-only automation.
- If a write tool were added without safeguards, retry behavior could create accidental duplicate runs.

## What was tried and didn’t work
- Tried to call the `review_approach` MCP helper before coding, but it returned HTTP 400 in this environment.
- Continued with test-first implementation locally.

## Key files involved
- `localrank_mcp/scan_write.py`: New scan write logic and duplicate guard.
- `localrank_mcp/__init__.py`: Tool registration, execution branch, and structured scan-run log emission.
- `tests/test_scan_write.py`: Regression coverage for highest-risk behaviors.
- `README.md`: Public MCP tool and guardrail documentation.

## Verified live surface
- Exact route used by customers: `POST https://api.localrank.so/api/scans/`
- Files that render/invoke this in MCP: `localrank_mcp/__init__.py` -> `create_scan_run(...)` in `localrank_mcp/scan_write.py`.
- Code path reached:
  1. MCP `call_tool(name="create_scan_run")`
  2. `create_scan_run(...)` validation + duplicate preflight (`GET /api/scans/`)
  3. guarded create (`POST /api/scans/`)
- Stale routes intentionally not touched: `/api/scans/preview_pins/`, `/api/scans/smart_groups/`, timeline endpoints.

## Gotchas for future work
- Duplicate guard is intentionally conservative and checks only recent active scans.
- `allow_duplicate_recent=true` should be used only for intentional reruns.
- Keep this tool narrow; if new write scope is needed, add a separate tool rather than expanding this one aggressively.

## Verification
Run these checks in production logs and API responses to confirm success within 5 minutes:

1. Structured log presence
- Command:
  - `grep '"flow": "mcp_tool_scan_run"' <mcp-log-file>`
- Expect: one JSON event per call with fields including:
  - `status`, `action`, `created_scan`, `business_uuid`, `scan_uuid`, `duplicate_matching_recent_count`.

2. Duplicate guard behavior
- Make two calls with same `business_uuid`, `keywords`, and `scanType` within the duplicate window.
- Expect first call logs `action=created_scan_run` and second call logs `action=blocked_recent_duplicate_scan` unless override is set.

3. Override behavior
- Repeat duplicate call with `allow_duplicate_recent=true`.
- Expect log contains `duplicate_override_used=true` and `created_scan=true`.

4. API response fields to confirm run creation
- MCP response should include:
  - `status: success`
  - `scan.uuid`
  - `scan.status`
  - `scan.created_at`

5. Axiom query (if shipping MCP logs there)
- Filter: `flow == "mcp_tool_scan_run"`
- Check ratio of:
  - `action == "created_scan_run"`
  - `action == "blocked_recent_duplicate_scan"`
- Unexpected spike in blocked duplicates may indicate clients are retrying too aggressively.
