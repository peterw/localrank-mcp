#!/usr/bin/env python3
"""
LocalRank MCP Server - mostly read-only API access for AI agents

Supports both stdio (Claude Desktop) and HTTP/SSE (Claude.ai web) transports.
- stdio: Uses LOCALRANK_API_KEY env var
- HTTP/SSE: Uses API key from query param (?api_key=lr_xxx) or OAuth Bearer token
"""
import os
import json
import base64
import asyncio
import logging
from contextvars import ContextVar
from urllib.parse import urlencode
import httpx
from mcp.server import Server
from mcp.types import (
    GetPromptResult,
    ImageContent,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    Tool,
)
from .citations_write import ensure_citation_business, ensure_citation_business_batch, to_json
from .scan_write import create_scan_run

API_BASE = os.getenv("LOCALRANK_API_URL", "https://api.localrank.so")
APP_BASE = os.getenv("LOCALRANK_APP_URL", "https://app.localrank.so")
API_KEY = os.getenv("LOCALRANK_API_KEY", "")  # For stdio mode
PORT = int(os.getenv("PORT", "8000"))
logging.basicConfig(
    level=os.getenv("LOCALRANK_MCP_LOG_LEVEL", "INFO").upper(),
    format="%(message)s",
)
logger = logging.getLogger("localrank_mcp")

# Context vars for HTTP mode auth
current_token: ContextVar[str] = ContextVar("current_token", default="")
current_api_key: ContextVar[str] = ContextVar("current_api_key", default="")
# Usage attribution: every API request carries the tool name and transport in
# its User-Agent, which the backend access log already records (Axiom field
# `user_agent`). Query: user_agent startswith "localrank-mcp/".
current_tool: ContextVar[str] = ContextVar("current_tool", default="")
CLIENT_VERSION = "0.2.0"
_transport = "stdio"


def set_transport(name: str) -> None:
    global _transport
    _transport = name


def client_user_agent() -> str:
    tool = current_tool.get() or "none"
    return f"localrank-mcp/{CLIENT_VERSION} (transport={_transport}; tool={tool})"

server = Server("localrank")

def get_auth_headers() -> dict:
    """Get authentication headers based on current context"""
    token = current_token.get()
    api_key = current_api_key.get()
    if token:
        return {"Authorization": f"Bearer {token}"}
    elif api_key:
        return {"Authorization": f"Api-Key {api_key}"}
    elif API_KEY:
        return {"Authorization": f"Api-Key {API_KEY}"}
    else:
        raise ValueError("No authentication provided. Use ?api_key=lr_xxx in URL.")


def request_headers() -> dict:
    return {**get_auth_headers(), "User-Agent": client_user_agent()}


def api_get(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GET request to LocalRank API"""
    headers = request_headers()
    resp = httpx.get(f"{API_BASE}{endpoint}", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(endpoint: str, data: dict = None) -> dict:
    """Make authenticated POST request to LocalRank API"""
    headers = request_headers()
    resp = httpx.post(f"{API_BASE}{endpoint}", headers=headers, json=data, timeout=60)
    resp.raise_for_status()
    return resp.json()


def api_get_binary(endpoint: str) -> bytes:
    """Make authenticated GET request expecting binary response (e.g., PDF)"""
    headers = request_headers()
    resp = httpx.get(f"{API_BASE}{endpoint}", headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.content


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="list_scans",
            description="List rank tracking scans. Filter by business_name to find a specific client. Returns view_url, embed_url, and PNG/JPG map-grid image URLs for visual reports.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max scans to return (default 10, max 50)"},
                    "business_name": {"type": "string", "description": "Filter by business name (partial match)"}
                }
            }
        ),
        Tool(
            name="get_scan",
            description="Get ranking details for a scan. Returns keyword rankings, view_url/embed_url, and PNG/JPG map-grid image URLs for reports.",
            inputSchema={
                "type": "object",
                "properties": {"scan_id": {"type": "string", "description": "The scan UUID"}},
                "required": ["scan_id"]
            }
        ),
        Tool(
            name="create_scan_run",
            description="Limited write tool. Starts a scan via /api/scans/ with request validation and a recent-duplicate guardrail.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_uuid": {"type": "string", "description": "Target business UUID"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keyword list for the scan (1-10 items)"
                    },
                    "scanType": {"type": "string", "description": "Optional: one-time (default) or repeating"},
                    "frequency": {"type": "string", "description": "Required when scanType is repeating"},
                    "pinCount": {"type": "integer", "description": "Optional pin count (default 35, must be >=1)"},
                    "radius": {"type": "number", "description": "Optional radius (default 5.0, must be >0)"},
                    "test_mode": {"type": "boolean", "description": "Optional test mode flag passed to scan create"},
                    "duplicate_window_minutes": {
                        "type": "integer",
                        "description": "Optional recent duplicate window in minutes (default 30)"
                    },
                    "allow_duplicate_recent": {
                        "type": "boolean",
                        "description": "Optional override to allow a duplicate run inside the recent window"
                    }
                },
                "required": ["business_uuid", "keywords"]
            }
        ),
        Tool(
            name="list_citations",
            description="List citations for businesses. Use business_name to filter.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Filter by business name (partial match)"}
                }
            }
        ),
        Tool(
            name="list_businesses",
            description="List all clients/businesses being tracked. Use search to find specific client by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search by business name"}
                }
            }
        ),
        Tool(
            name="ensure_citation_business",
            description="Limited write tool. Reuses an exact citation business match if one exists, creates a new citation business only when search finds nothing, and can optionally start a citation buildout.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Exact business name"},
                    "address": {"type": "string", "description": "Exact business address"},
                    "phone": {"type": "string", "description": "Exact business phone number"},
                    "website": {"type": "string", "description": "Business website"},
                    "description": {"type": "string", "description": "Optional business description"},
                    "location_name": {"type": "string", "description": "Optional first location name"},
                    "location_data": {"type": "object", "description": "Optional extra first-location fields like city/state/hours"},
                    "start_buildout": {"type": "boolean", "description": "Set true to start a limited citation buildout"},
                    "requested_citations": {"type": "integer", "description": "Optional requested citation count (must be >= 1)."}
                },
                "required": ["business_name", "address", "phone", "website"]
            }
        ),
        Tool(
            name="ensure_citation_business_batch",
            description="Batch citation write tool for multiple locations. Applies the same guardrails as ensure_citation_business to each item. Hard-capped to 10 items per call.",
            inputSchema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of businesses/locations to process in one request (max 10)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "business_name": {"type": "string", "description": "Exact business name"},
                                "address": {"type": "string", "description": "Exact business address"},
                                "phone": {"type": "string", "description": "Exact business phone number"},
                                "website": {"type": "string", "description": "Business website"},
                                "description": {"type": "string", "description": "Optional business description"},
                                "location_name": {"type": "string", "description": "Optional first location name"},
                                "location_data": {"type": "object", "description": "Optional extra first-location fields"},
                                "start_buildout": {"type": "boolean", "description": "Optional per-item override"},
                                "requested_citations": {"type": "integer", "description": "Optional per-item requested citations (must be >= 1)"}
                            },
                            "required": ["business_name", "address", "phone", "website"]
                        }
                    },
                    "start_buildout": {"type": "boolean", "description": "Default start_buildout for items missing it"},
                    "requested_citations": {"type": "integer", "description": "Default requested citations for items missing it"},
                    "max_total_requested_citations": {
                        "type": "integer",
                        "description": "Optional cross-item cap for requested citations in this batch"
                    }
                },
                "required": ["items"]
            }
        ),
        Tool(
            name="list_review_campaigns",
            description="List all review collection campaigns",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_review_campaign",
            description="Get details for a specific review campaign including analytics",
            inputSchema={
                "type": "object",
                "properties": {"campaign_id": {"type": "integer", "description": "The campaign ID"}},
                "required": ["campaign_id"]
            }
        ),
        Tool(
            name="list_gmb_locations",
            description="List all connected Google My Business locations",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="list_gmb_reviews",
            description="List reviews for a GMB location",
            inputSchema={
                "type": "object",
                "properties": {"location_id": {"type": "string", "description": "The GMB location ID"}},
                "required": ["location_id"]
            }
        ),
        Tool(
            name="client_report",
            description="Generate a client report comparing recent scans. Shows ranking changes, wins (improved), drops (declined), the visual map URL, and attaches the latest heat map image. Perfect for sending to clients.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name to search for"},
                    "include_map_image": {"type": "boolean", "description": "Attach the latest heat map image (default true)"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="get_ranking_changes",
            description="Get all clients with ranking drops or improvements. Use to quickly find which clients need attention.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Filter: 'drops' for declined, 'wins' for improved, 'all' for both (default)"}
                }
            }
        ),
        Tool(
            name="get_recommendations",
            description="Get recommendations for how to help a client rank better. Analyzes their data and suggests LocalRank features to use: more keywords, review campaigns, citation building, GBP optimization, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name to analyze"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="get_competitors",
            description="See who's outranking your client for each keyword. Shows top competitors and their positions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name to analyze"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="get_win_stories",
            description="Find your biggest client wins - clients with the most ranking improvements. Perfect for case studies and sales conversations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of top wins to return (default 5)"}
                }
            }
        ),
        Tool(
            name="get_at_risk_clients",
            description="Identify clients who might churn - ranking drops, no recent scans, declining engagement. Catch them before they cancel.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="portfolio_summary",
            description="Get a complete overview of all your clients - total wins, drops, opportunities, and health metrics. Perfect for monthly reviews.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="draft_client_email",
            description="Generate a monthly update email for a client. Includes wins, current rankings, next steps, and attaches the latest heat map image. Ready to copy-paste and send.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name"},
                    "include_map_image": {"type": "boolean", "description": "Attach the latest heat map image (default true)"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="find_quick_wins",
            description="Find keywords ranking 11-20 that could be pushed to page 1 with a little effort. Easy wins to show value fast.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name (optional - shows all clients if not provided)"}
                }
            }
        ),
        Tool(
            name="renewal_pitch",
            description="Generate a renewal pitch showing all value delivered since client started. Total ranking improvements, wins, and ROI justification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="suggest_content",
            description="Suggest blog post and content ideas based on keywords the client is tracking. Helps upsell content services.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="prioritize_today",
            description="Get a prioritized list of what to work on today. Shows clients needing urgent attention, quick wins available, and scheduled tasks.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="delegate_tasks",
            description="Get a list of tasks that can be delegated to a VA or team member. Routine work that doesn't need agency owner attention.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_boost_status",
            description="Check the status of LocalBoost, SuperBoost, and ContentBoost for a client. Shows citations built, backlinks created, and content published.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name"}
                },
                "required": ["business_name"]
            }
        ),
        Tool(
            name="list_boost_activity",
            description="Get recent boost activity across all clients - citations submitted, content published, optimizations made. Great for showing clients what you're doing for them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Filter by business name (optional)"},
                    "limit": {"type": "integer", "description": "Max activities to return (default 20)"}
                }
            }
        ),
        Tool(
            name="run_audit",
            description="Run a GMB audit on a Google Maps business URL. Analyzes reviews, ratings, response rates, and provides actionable insights. Costs 500 credits. Returns audit_id and share_url.",
            inputSchema={
                "type": "object",
                "properties": {
                    "gmb_url": {"type": "string", "description": "Google Maps business URL (e.g., https://www.google.com/maps/place/...)"}
                },
                "required": ["gmb_url"]
            }
        ),
        Tool(
            name="get_audit",
            description="Get the results of a GMB audit by audit ID. Returns detailed analysis including review stats, issues identified, and recommendations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "audit_id": {"type": "string", "description": "The audit UUID"}
                },
                "required": ["audit_id"]
            }
        ),
        Tool(
            name="get_audit_pdf",
            description="Download a PDF report for a completed audit. Returns the PDF as base64-encoded data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "audit_id": {"type": "string", "description": "The audit UUID"}
                },
                "required": ["audit_id"]
            }
        ),
    ]


PROMPTS = {
    "monthly-client-update": {
        "description": "Write this month's update email for one client, with the heat map.",
        "arguments": [("business_name", "Client business name", True)],
        "text": (
            "Write this month's client update for {business_name}. Do not change anything in LocalRank.\n"
            "1. Call client_report with business_name=\"{business_name}\". It returns ranking wins and drops "
            "and attaches the latest heat map image.\n"
            "2. Call draft_client_email for the same client.\n"
            "3. Rewrite it the way I would write to a client I know: short, warm, plain words, under 150 words. "
            "Open with the one change they will care about most, for example 'you went from #9 to #6 for \"plumber\"'. "
            "Use numbers only where they help. If something dropped, say so in one sentence and what we are doing next. "
            "No headings, no bold, no bullet points unless there are three or more keywords, and no stock phrases "
            "such as 'I hope this finds you well', 'Good news!' or 'Current performance'. Include the ranking map link.\n"
            "4. Show me the heat map image so I can attach it to the email."
        ),
    },
    "whats-changed-this-week": {
        "description": "See which clients moved up, which dropped, and what to do today.",
        "arguments": [],
        "text": (
            "Show me what changed across my LocalRank clients. Do not change anything in LocalRank.\n"
            "1. Call get_ranking_changes, then get_at_risk_clients.\n"
            "2. List up to 5 clients that improved (keyword, from #X to #Y) and every client that dropped (keyword, from #X to #Y).\n"
            "3. List clients with no recent scan.\n"
            "4. End with three actions for today, ordered by the risk of losing the client."
        ),
    },
    "renewal-pitch": {
        "description": "Write a renewal note that shows one client the results since they started.",
        "arguments": [("business_name", "Client business name", True)],
        "text": (
            "Write a renewal note for {business_name}. Do not change anything in LocalRank.\n"
            "1. Call renewal_pitch and client_report with business_name=\"{business_name}\".\n"
            "2. Call find_quick_wins for the same client.\n"
            "3. Write a short note to the client: results since they started, where they rank now, "
            "and a 90-day plan built from the quick wins. Show the heat map image so I can attach it."
        ),
    },
}


@server.list_prompts()
async def list_prompts():
    return [
        Prompt(
            name=name,
            description=spec["description"],
            arguments=[
                PromptArgument(name=arg, description=desc, required=required)
                for arg, desc, required in spec["arguments"]
            ],
        )
        for name, spec in PROMPTS.items()
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None):
    spec = PROMPTS.get(name)
    if spec is None:
        raise ValueError(f"Unknown prompt: {name}")
    arguments = arguments or {}
    missing = [arg for arg, _, required in spec["arguments"] if required and not arguments.get(arg)]
    if missing:
        raise ValueError(f"Missing argument: {', '.join(missing)}")
    logger.info(json.dumps({"flow": "mcp_prompt", "prompt_name": name, "transport": _transport}))
    return GetPromptResult(
        description=spec["description"],
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=spec["text"].replace("{business_name}", str(arguments.get("business_name", "")))),
            )
        ],
    )


def get_visual_urls(token: str) -> dict:
    """Generate visual report URLs from share token"""
    app_base = APP_BASE.rstrip("/")
    return {
        "view_url": f"{app_base}/share/{token}",
        "embed_url": f"{app_base}/share/{token}?embed=true",
    }

def get_map_grid_image_urls(scan_id: str, keyword: str = None) -> dict:
    """Generate authenticated map-grid image API URLs for reporting automation."""
    if not scan_id:
        return {}

    base_url = f"{APP_BASE.rstrip('/')}/api/scans/{scan_id}/map-grid-image"
    png_params = {"format": "png"}
    jpg_params = {"format": "jpg"}
    if keyword:
        png_params["keyword"] = keyword
        jpg_params["keyword"] = keyword

    return {
        "map_grid_image_png_url": f"{base_url}?{urlencode(png_params)}",
        "map_grid_image_jpg_url": f"{base_url}?{urlencode(jpg_params)}",
        "map_grid_image_auth": "Use the same Authorization header as MCP/API requests.",
    }

def fetch_map_image(scan_id: str, keyword: str = None):
    """Fetch the scan heat map as an MCP image so the user can see and attach it.

    The image URL needs our Authorization header, so a client email cannot
    embed it; returning the bytes lets Claude/ChatGPT show it directly.
    Returns None when the image is not available (scan still running, timeout).
    """
    if not scan_id:
        return None
    params = {"format": "jpg"}
    if keyword:
        params["keyword"] = keyword
    try:
        resp = httpx.get(
            f"{APP_BASE.rstrip('/')}/api/scans/{scan_id}/map-grid-image",
            headers=request_headers(),
            params=params,
            timeout=60,
        )
    except httpx.HTTPError as exc:
        logger.info(json.dumps({"flow": "mcp_map_image", "outcome": "request_error", "error": type(exc).__name__}))
        return None
    content_type = resp.headers.get("content-type", "").split(";")[0].strip()
    if resp.status_code != 200 or not content_type.startswith("image/"):
        logger.info(json.dumps({"flow": "mcp_map_image", "outcome": "unavailable", "status_code": resp.status_code}))
        return None
    return ImageContent(type="image", data=base64.b64encode(resp.content).decode("ascii"), mimeType=content_type)


def with_map_image(result: list, scan_id: str, arguments: dict) -> list:
    if arguments.get("include_map_image", True) is False:
        return result
    image = fetch_map_image(scan_id)
    return result + [image] if image else result


def summarize_scan(scan: dict) -> dict:
    """Return lightweight scan summary with share URLs"""
    token = scan.get("public_share_token")
    urls = get_visual_urls(token) if token else {}
    image_urls = get_map_grid_image_urls(scan.get("uuid"))
    return {
        "uuid": scan.get("uuid"),
        "business_name": scan.get("business", {}).get("name"),
        "keywords": scan.get("keywords", []),
        "status": scan.get("status"),
        "created_at": scan.get("created_at"),
        "avg_rank": scan.get("avg_rank"),
        "scanType": scan.get("scanType"),
        **urls,
        **image_urls,
    }

def summarize_scan_detail(scan: dict) -> dict:
    """Return scan detail with keyword rankings but without heavy grid data"""
    token = scan.get("public_share_token")
    urls = get_visual_urls(token) if token else {}
    image_urls = get_map_grid_image_urls(scan.get("uuid"))
    keyword_summary = []
    for kw in scan.get("keyword_results", []):
        keyword = kw.get("keyword") or kw.get("term")
        keyword_summary.append({
            "keyword": keyword,
            "avg_rank": kw.get("avg_rank"),
            "best_rank": kw.get("best_rank"),
            "found_count": kw.get("found_count"),
            **get_map_grid_image_urls(scan.get("uuid"), keyword),
        })
    return {
        "uuid": scan.get("uuid"),
        "business_name": scan.get("business", {}).get("name"),
        "keywords": scan.get("keywords", []),
        "status": scan.get("status"),
        "created_at": scan.get("created_at"),
        "completed_at": scan.get("completed_at"),
        "public_share_enabled": scan.get("public_share_enabled"),
        "keyword_rankings": keyword_summary,
        "scanType": scan.get("scanType"),
        "pinCount": scan.get("pinCount"),
        **urls,
        **image_urls,
    }


def log_tool_transaction(tool_name: str, outcome: str, payload: dict) -> None:
    logger.info(json.dumps({
        "flow": "mcp_tool",
        "tool_name": tool_name,
        "outcome": outcome,
        "action": payload.get("action"),
        "status": payload.get("status"),
        "search_results_count": payload.get("search_results_count"),
        "clear_match_count": payload.get("clear_match_count"),
        "candidate_count": len(payload.get("candidates", [])),
        "created_business": payload.get("created_business"),
        "business_uuid": payload.get("business", {}).get("uuid"),
        "buildout_started": payload.get("buildout", {}).get("started"),
        "buildout_requested": payload.get("buildout", {}).get("requested"),
        "max_citations_used": payload.get("buildout", {}).get("max_citations_used"),
    }, sort_keys=True))


def log_batch_tool_transaction(tool_name: str, outcome: str, payload: dict) -> None:
    summary = payload.get("summary", {})
    logger.info(json.dumps({
        "flow": "mcp_tool_batch",
        "tool_name": tool_name,
        "outcome": outcome,
        "action": payload.get("action"),
        "status": payload.get("status"),
        "total_items": summary.get("total_items"),
        "success_count": summary.get("success_count"),
        "blocked_count": summary.get("blocked_count"),
        "error_count": summary.get("error_count"),
        "buildout_started_count": summary.get("buildout_started_count"),
        "created_citations_total": summary.get("created_citations_total"),
        "total_requested_citations": summary.get("total_requested_citations"),
        "max_total_requested_citations": summary.get("max_total_requested_citations"),
        "action_counts": summary.get("action_counts"),
    }, sort_keys=True))


def log_scan_run_tool_transaction(tool_name: str, outcome: str, payload: dict) -> None:
    request_data = payload.get("request", {})
    duplicate_check = payload.get("duplicate_check", {})
    scan = payload.get("scan", {})

    logger.info(json.dumps({
        "flow": "mcp_tool_scan_run",
        "tool_name": tool_name,
        "outcome": outcome,
        "action": payload.get("action"),
        "status": payload.get("status"),
        "created_scan": payload.get("created_scan"),
        "message": payload.get("message"),
        "business_uuid": request_data.get("business_uuid"),
        "scan_type": request_data.get("scanType"),
        "keyword_count": request_data.get("keyword_count"),
        "keywords": request_data.get("keywords"),
        "pin_count": request_data.get("pinCount"),
        "radius": request_data.get("radius"),
        "frequency": request_data.get("frequency"),
        "test_mode": request_data.get("test_mode"),
        "duplicate_window_minutes": duplicate_check.get("window_minutes"),
        "duplicate_scanned_count": duplicate_check.get("scanned_count"),
        "duplicate_recent_active_count": duplicate_check.get("recent_active_count"),
        "duplicate_matching_recent_count": duplicate_check.get("matching_recent_count"),
        "duplicate_override_used": duplicate_check.get("override_used"),
        "duplicate_matches": duplicate_check.get("matching_recent"),
        "scan_uuid": scan.get("uuid"),
        "scan_status": scan.get("status"),
        "scan_created_at": scan.get("created_at"),
    }, sort_keys=True))


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    current_tool.set(name)
    try:
        if name == "list_scans":
            limit = min(arguments.get("limit", 10), 50)
            data = api_get("/api/scans/", params={"page_size": limit})
            results = data.get("results", [])
            # Filter by business name if provided
            business_filter = arguments.get("business_name", "").lower()
            if business_filter:
                results = [s for s in results if business_filter in s.get("business", {}).get("name", "").lower()]
            summaries = [summarize_scan(s) for s in results]
            return [TextContent(type="text", text=json.dumps({
                "count": len(summaries),
                "total": data.get("count"),
                "scans": summaries,
                "tip": "Use view_url for visual map, embed_url for iframe embed, and map_grid_image_png_url/map_grid_image_jpg_url for automated report images. Image URLs require the same Authorization header as MCP/API requests."
            }, indent=2))]

        elif name == "get_scan":
            data = api_get(f"/api/scans/{arguments['scan_id']}/")
            summary = summarize_scan_detail(data)
            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

        elif name == "create_scan_run":
            try:
                result = create_scan_run(arguments, api_get=api_get, api_post=api_post)
            except Exception as exc:
                args = arguments if isinstance(arguments, dict) else {}
                log_scan_run_tool_transaction(
                    name,
                    "error",
                    {
                        "status": "error",
                        "action": "exception",
                        "created_scan": False,
                        "message": str(exc),
                        "request": {
                            "business_uuid": args.get("business_uuid"),
                            "scanType": args.get("scanType") if "scanType" in args else (args.get("scan_type") or "one-time"),
                            "keyword_count": len(args.get("keywords", []))
                            if isinstance(args.get("keywords"), list)
                            else 0,
                            "keywords": args.get("keywords"),
                            "pinCount": args.get("pinCount") if "pinCount" in args else args.get("pin_count"),
                            "radius": args.get("radius"),
                            "frequency": args.get("frequency"),
                            "test_mode": bool(args.get("test_mode", False)),
                        },
                        "duplicate_check": {
                            "window_minutes": args.get("duplicate_window_minutes"),
                            "scanned_count": None,
                            "recent_active_count": None,
                            "matching_recent_count": None,
                            "override_used": bool(args.get("allow_duplicate_recent", False)),
                            "matching_recent": [],
                        },
                        "scan": {},
                    },
                )
                raise

            log_scan_run_tool_transaction(name, result.get("status", "success"), result)
            return [TextContent(type="text", text=to_json(result))]

        elif name == "list_citations":
            data = api_get("/citations/list/")
            results = data.get("results", []) if isinstance(data, dict) else data
            # Filter by business name if provided
            business_filter = arguments.get("business_name", "").lower()
            if business_filter and isinstance(results, list):
                results = [c for c in results if business_filter in str(c.get("business_name", "")).lower()]
            return [TextContent(type="text", text=json.dumps({"citations": results[:20]}, indent=2))]

        elif name == "list_businesses":
            data = api_get("/api/businesses/")
            results = data.get("results", []) if isinstance(data, dict) else data
            # Filter by search if provided
            search = arguments.get("search", "").lower()
            if search and isinstance(results, list):
                results = [b for b in results if search in b.get("name", "").lower()]
            # Return lightweight business list
            businesses = [{"uuid": b.get("uuid"), "name": b.get("name"), "place_id": b.get("place_id")} for b in results[:50]]
            return [TextContent(type="text", text=json.dumps({"businesses": businesses, "count": len(businesses)}, indent=2))]

        elif name == "ensure_citation_business":
            try:
                result = ensure_citation_business(arguments, api_get=api_get, api_post=api_post)
            except Exception as exc:
                log_tool_transaction(
                    name,
                    "error",
                    {
                        "action": "exception",
                        "status": "error",
                        "buildout": {
                            "started": False,
                            "requested": arguments.get("requested_citations"),
                            "max_citations_used": None,
                        },
                        "search_results_count": None,
                        "clear_match_count": None,
                        "business": {},
                        "candidates": [],
                        "created_business": False,
                        "message": str(exc),
                    },
                )
                raise

            log_tool_transaction(name, result.get("status", "success"), result)
            return [TextContent(type="text", text=to_json(result))]

        elif name == "ensure_citation_business_batch":
            try:
                result = ensure_citation_business_batch(arguments, api_get=api_get, api_post=api_post)
            except Exception as exc:
                log_batch_tool_transaction(
                    name,
                    "error",
                    {
                        "action": "exception",
                        "status": "error",
                        "summary": {
                            "total_items": len(arguments.get("items", []))
                            if isinstance(arguments.get("items"), list)
                            else None,
                            "success_count": 0,
                            "blocked_count": 0,
                            "error_count": 1,
                            "buildout_started_count": 0,
                            "created_citations_total": 0,
                            "total_requested_citations": 0,
                            "max_total_requested_citations": arguments.get("max_total_requested_citations"),
                            "action_counts": {"exception": 1},
                        },
                        "message": str(exc),
                    },
                )
                raise

            log_batch_tool_transaction(name, result.get("status", "success"), result)
            return [TextContent(type="text", text=to_json(result))]

        elif name == "list_review_campaigns":
            data = api_get("/review-booster/campaigns/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "get_review_campaign":
            data = api_get(f"/review-booster/campaigns/{arguments['campaign_id']}/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "list_gmb_locations":
            data = api_get("/api/gmb/locations/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "list_gmb_reviews":
            data = api_get(f"/api/gmb/locations/{arguments['location_id']}/reviews/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "client_report":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            # Get scans filtered by business name
            data = api_get("/api/scans/", params={"page_size": 50})
            results = data.get("results", [])
            client_scans = [s for s in results if business_name in s.get("business", {}).get("name", "").lower()]

            if len(client_scans) == 0:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No scans found for '{business_name}'",
                    "tip": "Use list_businesses to see all clients"
                }, indent=2))]

            # Get most recent scan details
            latest = client_scans[0]
            latest_detail = api_get(f"/api/scans/{latest['uuid']}/")

            report = {
                "business_name": latest.get("business", {}).get("name"),
                "latest_scan": {
                    "date": latest_detail.get("created_at"),
                    "avg_rank": latest_detail.get("avg_rank"),
                    "keywords": []
                },
                "wins": [],
                "drops": [],
                "unchanged": [],
            }

            # Extract keyword rankings from latest
            for kw in latest_detail.get("keyword_results", []):
                report["latest_scan"]["keywords"].append({
                    "keyword": kw.get("keyword"),
                    "avg_rank": kw.get("avg_rank"),
                    "best_rank": kw.get("best_rank"),
                })

            # Compare with previous scan if available
            if len(client_scans) >= 2:
                previous = client_scans[1]
                previous_detail = api_get(f"/api/scans/{previous['uuid']}/")
                report["previous_scan"] = {
                    "date": previous_detail.get("created_at"),
                    "avg_rank": previous_detail.get("avg_rank"),
                }

                # Build keyword lookup from previous scan
                prev_kw_ranks = {}
                for kw in previous_detail.get("keyword_results", []):
                    prev_kw_ranks[kw.get("keyword")] = kw.get("avg_rank")

                # Compare rankings
                for kw in latest_detail.get("keyword_results", []):
                    keyword = kw.get("keyword")
                    current_rank = kw.get("avg_rank")
                    prev_rank = prev_kw_ranks.get(keyword)

                    if prev_rank and current_rank:
                        change = prev_rank - current_rank  # Positive = improved (lower rank is better)
                        if change > 0:
                            report["wins"].append({"keyword": keyword, "from": prev_rank, "to": current_rank, "improved_by": round(change, 1)})
                        elif change < 0:
                            report["drops"].append({"keyword": keyword, "from": prev_rank, "to": current_rank, "dropped_by": round(abs(change), 1)})
                        else:
                            report["unchanged"].append({"keyword": keyword, "rank": current_rank})

            # Add visual report URLs
            token = latest_detail.get("public_share_token")
            if token:
                report["view_url"] = f"https://app.localrank.so/share/{token}"
                report["embed_url"] = f"https://app.localrank.so/share/{token}?embed=true"

            report["total_scans"] = len(client_scans)
            result = [TextContent(type="text", text=json.dumps(report, indent=2))]
            return with_map_image(result, latest.get("uuid"), arguments)

        elif name == "get_ranking_changes":
            filter_type = arguments.get("type", "all").lower()

            # Get recent scans
            data = api_get("/api/scans/", params={"page_size": 100})
            results = data.get("results", [])

            # Group scans by business
            by_business = {}
            for scan in results:
                biz = scan.get("business", {})
                biz_name = biz.get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = []
                by_business[biz_name].append(scan)

            changes = []
            for biz_name, scans in by_business.items():
                if len(scans) < 2:
                    continue

                # Compare two most recent scans
                latest = scans[0]
                previous = scans[1]

                latest_avg = latest.get("avg_rank")
                prev_avg = previous.get("avg_rank")

                if latest_avg and prev_avg:
                    change = prev_avg - latest_avg  # Positive = improved

                    entry = {
                        "business_name": biz_name,
                        "current_avg_rank": round(latest_avg, 1),
                        "previous_avg_rank": round(prev_avg, 1),
                        "change": round(change, 1),
                        "latest_scan_date": latest.get("created_at"),
                    }

                    # Add visual URL
                    token = latest.get("public_share_token")
                    if token:
                        entry["view_url"] = f"https://app.localrank.so/share/{token}"

                    if change > 0:
                        entry["status"] = "improved"
                        if filter_type in ["all", "wins"]:
                            changes.append(entry)
                    elif change < 0:
                        entry["status"] = "declined"
                        if filter_type in ["all", "drops"]:
                            changes.append(entry)

            # Sort by change magnitude (biggest drops first for attention)
            changes.sort(key=lambda x: x["change"])

            return [TextContent(type="text", text=json.dumps({
                "filter": filter_type,
                "clients_with_changes": len(changes),
                "changes": changes,
                "tip": "Use client_report for detailed breakdown of a specific client"
            }, indent=2))]

        elif name == "get_recommendations":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            recommendations = []

            # Get scans for this client
            scans_data = api_get("/api/scans/", params={"page_size": 50})
            scans = scans_data.get("results", [])
            client_scans = [s for s in scans if business_name in s.get("business", {}).get("name", "").lower()]

            if not client_scans:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No data found for '{business_name}'",
                    "recommendations": [{
                        "action": "Run first scan",
                        "feature": "Rank Tracker",
                        "reason": "No ranking data yet - run a scan to establish baseline",
                        "path": "/rank-tracker"
                    }]
                }, indent=2))]

            latest = client_scans[0]
            keywords = latest.get("keywords", [])
            avg_rank = latest.get("avg_rank")
            biz_name_full = latest.get("business", {}).get("name", business_name)

            # Recommendation: Poor rankings - need SuperBoost
            if avg_rank and avg_rank > 10:
                recommendations.append({
                    "action": "Use SuperBoost",
                    "product": "SuperBoost",
                    "reason": f"Average rank is {round(avg_rank, 1)}. SuperBoost uses AI-powered GBP optimization to dramatically improve visibility.",
                    "path": "/superboost"
                })

            # Recommendation: Moderate rankings - LocalBoost
            if avg_rank and 5 < avg_rank <= 10:
                recommendations.append({
                    "action": "Use LocalBoost",
                    "product": "LocalBoost",
                    "reason": f"Average rank is {round(avg_rank, 1)}. LocalBoost builds local authority through citations and backlinks.",
                    "path": "/localboost"
                })

            # Recommendation: Need content - ContentBoost
            if avg_rank and avg_rank > 7:
                recommendations.append({
                    "action": "Use ContentBoost",
                    "product": "ContentBoost",
                    "reason": "ContentBoost creates localized content that improves rankings for service area keywords.",
                    "path": "/contentboost"
                })

            # Recommendation: Ranking dropped - SuperBoost recovery
            if len(client_scans) >= 2:
                previous = client_scans[1]
                prev_avg = previous.get("avg_rank")
                if avg_rank and prev_avg and (avg_rank - prev_avg) > 2:
                    recommendations.append({
                        "action": "SuperBoost recovery",
                        "product": "SuperBoost",
                        "reason": f"Rankings dropped from {round(prev_avg, 1)} to {round(avg_rank, 1)}. SuperBoost can help recover lost positions.",
                        "path": "/superboost"
                    })

            # Check for review campaign
            try:
                campaigns_data = api_get("/review-booster/campaigns/")
                campaigns = campaigns_data if isinstance(campaigns_data, list) else campaigns_data.get("results", [])
                has_campaign = any(
                    business_name in (c.get("business_name") or c.get("business", {}).get("name", "")).lower()
                    for c in campaigns
                )
                if not has_campaign:
                    recommendations.append({
                        "action": "Start Review Booster campaign",
                        "product": "Review Booster",
                        "reason": "No active review campaign. Reviews boost rankings and conversions.",
                        "path": "/review-booster"
                    })
            except Exception:
                pass

            # Track more keywords
            if len(keywords) < 5:
                recommendations.append({
                    "action": "Track more keywords",
                    "product": "Rank Tracker",
                    "reason": f"Only tracking {len(keywords)} keywords. Add more to measure impact of boosts.",
                    "path": "/rank-tracker"
                })

            # If rankings are good, suggest maintaining with LocalBoost
            if avg_rank and avg_rank <= 5 and len(recommendations) == 0:
                recommendations.append({
                    "action": "Maintain with LocalBoost",
                    "product": "LocalBoost",
                    "reason": f"Great rankings (avg {round(avg_rank, 1)})! LocalBoost helps maintain authority and defend against competitors.",
                    "path": "/localboost"
                })

            return [TextContent(type="text", text=json.dumps({
                "business_name": biz_name_full,
                "current_avg_rank": round(avg_rank, 1) if avg_rank else None,
                "keywords_tracked": len(keywords),
                "recommendations": recommendations,
            }, indent=2))]

        elif name == "get_competitors":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            # Get scans for this client
            scans_data = api_get("/api/scans/", params={"page_size": 50})
            scans = scans_data.get("results", [])
            client_scans = [s for s in scans if business_name in s.get("business", {}).get("name", "").lower()]

            if not client_scans:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No scans found for '{business_name}'"
                }, indent=2))]

            # Get latest scan with full details
            latest = client_scans[0]
            latest_detail = api_get(f"/api/scans/{latest['uuid']}/")
            biz_name_full = latest.get("business", {}).get("name", business_name)

            competitors_by_keyword = []
            for kw in latest_detail.get("keyword_results", []):
                keyword = kw.get("keyword")
                your_rank = kw.get("avg_rank")

                # Extract competitors from grid data if available
                competitors = []
                grid_data = kw.get("grid_data", [])
                if grid_data:
                    # Collect all businesses found in grid
                    seen = set()
                    for point in grid_data:
                        for result in point.get("results", [])[:5]:
                            comp_name = result.get("name", "")
                            if comp_name and comp_name.lower() != biz_name_full.lower() and comp_name not in seen:
                                seen.add(comp_name)
                                competitors.append({
                                    "name": comp_name,
                                    "appears_in_top_5": True
                                })

                competitors_by_keyword.append({
                    "keyword": keyword,
                    "your_avg_rank": round(your_rank, 1) if your_rank else None,
                    "top_competitors": competitors[:5]
                })

            return [TextContent(type="text", text=json.dumps({
                "business_name": biz_name_full,
                "keywords_analyzed": len(competitors_by_keyword),
                "competitor_analysis": competitors_by_keyword,
                "tip": "These competitors consistently appear in top positions for your client's keywords"
            }, indent=2))]

        elif name == "get_win_stories":
            limit = arguments.get("limit", 5)

            # Get recent scans
            data = api_get("/api/scans/", params={"page_size": 100})
            results = data.get("results", [])

            # Group by business
            by_business = {}
            for scan in results:
                biz = scan.get("business", {})
                biz_name = biz.get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = []
                by_business[biz_name].append(scan)

            wins = []
            for biz_name, scans in by_business.items():
                if len(scans) < 2:
                    continue

                # Find biggest improvement across all scan pairs
                best_improvement = 0
                best_from = None
                best_to = None
                latest_scan = scans[0]

                for i in range(len(scans) - 1):
                    current = scans[i].get("avg_rank")
                    previous = scans[i + 1].get("avg_rank")
                    if current and previous:
                        improvement = previous - current
                        if improvement > best_improvement:
                            best_improvement = improvement
                            best_from = previous
                            best_to = current

                if best_improvement > 0:
                    token = latest_scan.get("public_share_token")
                    wins.append({
                        "business_name": biz_name,
                        "improvement": round(best_improvement, 1),
                        "from_rank": round(best_from, 1),
                        "to_rank": round(best_to, 1),
                        "scans_tracked": len(scans),
                        "view_url": f"https://app.localrank.so/share/{token}" if token else None,
                        "story": f"Improved from #{round(best_from, 1)} to #{round(best_to, 1)} average rank"
                    })

            # Sort by biggest improvement
            wins.sort(key=lambda x: x["improvement"], reverse=True)

            return [TextContent(type="text", text=json.dumps({
                "top_wins": wins[:limit],
                "total_improving_clients": len(wins),
                "tip": "Use these success stories in sales calls and case studies"
            }, indent=2))]

        elif name == "get_at_risk_clients":
            # Get recent scans
            data = api_get("/api/scans/", params={"page_size": 100})
            results = data.get("results", [])

            # Group by business
            by_business = {}
            for scan in results:
                biz = scan.get("business", {})
                biz_name = biz.get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = []
                by_business[biz_name].append(scan)

            at_risk = []
            for biz_name, scans in by_business.items():
                risk_factors = []
                risk_score = 0
                latest = scans[0]

                # Risk: Rankings dropped
                if len(scans) >= 2:
                    current = latest.get("avg_rank")
                    previous = scans[1].get("avg_rank")
                    if current and previous and (current - previous) > 2:
                        risk_factors.append(f"Rankings dropped from {round(previous, 1)} to {round(current, 1)}")
                        risk_score += 3

                # Risk: Poor rankings (never seeing results)
                avg_rank = latest.get("avg_rank")
                if avg_rank and avg_rank > 15:
                    risk_factors.append(f"Poor visibility (avg rank {round(avg_rank, 1)})")
                    risk_score += 2

                # Risk: Only one scan (not engaged)
                if len(scans) == 1:
                    risk_factors.append("Only 1 scan ever - low engagement")
                    risk_score += 1

                # Risk: Old scan (no recent activity)
                latest_date = latest.get("created_at", "")
                if latest_date:
                    # Simple check - if scan is old (we can't do date math easily, so skip this for now)
                    pass

                if risk_score > 0:
                    at_risk.append({
                        "business_name": biz_name,
                        "risk_score": risk_score,
                        "risk_factors": risk_factors,
                        "current_avg_rank": round(avg_rank, 1) if avg_rank else None,
                        "total_scans": len(scans),
                        "action": "Reach out proactively to show value and offer help"
                    })

            # Sort by risk score
            at_risk.sort(key=lambda x: x["risk_score"], reverse=True)

            return [TextContent(type="text", text=json.dumps({
                "at_risk_clients": at_risk,
                "total_at_risk": len(at_risk),
                "tip": "Contact these clients before they churn. Show them you're proactively monitoring their business."
            }, indent=2))]

        elif name == "portfolio_summary":
            # Get all scans
            data = api_get("/api/scans/", params={"page_size": 100})
            results = data.get("results", [])

            # Group by business
            by_business = {}
            for scan in results:
                biz = scan.get("business", {})
                biz_name = biz.get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = []
                by_business[biz_name].append(scan)

            summary = {
                "total_clients": len(by_business),
                "total_scans": len(results),
                "improving": 0,
                "declining": 0,
                "stable": 0,
                "new_clients": 0,
                "avg_rank_across_portfolio": 0,
                "clients": []
            }

            total_rank = 0
            rank_count = 0

            for biz_name, scans in by_business.items():
                latest = scans[0]
                avg_rank = latest.get("avg_rank")

                if avg_rank:
                    total_rank += avg_rank
                    rank_count += 1

                status = "new"
                change = None

                if len(scans) >= 2:
                    current = latest.get("avg_rank")
                    previous = scans[1].get("avg_rank")
                    if current and previous:
                        change = previous - current
                        if change > 0.5:
                            status = "improving"
                            summary["improving"] += 1
                        elif change < -0.5:
                            status = "declining"
                            summary["declining"] += 1
                        else:
                            status = "stable"
                            summary["stable"] += 1
                else:
                    summary["new_clients"] += 1

                token = latest.get("public_share_token")
                summary["clients"].append({
                    "name": biz_name,
                    "status": status,
                    "avg_rank": round(avg_rank, 1) if avg_rank else None,
                    "change": round(change, 1) if change else None,
                    "scans": len(scans),
                    "view_url": f"https://app.localrank.so/share/{token}" if token else None
                })

            if rank_count > 0:
                summary["avg_rank_across_portfolio"] = round(total_rank / rank_count, 1)

            # Sort clients by status priority: declining first, then improving, then stable
            status_order = {"declining": 0, "improving": 1, "stable": 2, "new": 3}
            summary["clients"].sort(key=lambda x: status_order.get(x["status"], 4))

            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

        elif name == "draft_client_email":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            # Get scans for this client
            scans_data = api_get("/api/scans/", params={"page_size": 50})
            scans = scans_data.get("results", [])
            client_scans = [s for s in scans if business_name in s.get("business", {}).get("name", "").lower()]

            if not client_scans:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No data found for '{business_name}'"
                }, indent=2))]

            latest = client_scans[0]
            biz_name_full = latest.get("business", {}).get("name", business_name)
            avg_rank = latest.get("avg_rank")
            keywords = latest.get("keywords", [])

            token = latest.get("public_share_token")
            map_url = f"https://app.localrank.so/share/{token}" if token else None
            first_keyword = keywords[0] if keywords else None
            if isinstance(first_keyword, dict):
                first_keyword = first_keyword.get("term") or first_keyword.get("keyword")
            main_keyword = f'"{first_keyword}"' if first_keyword else "your main keywords"
            current = round(avg_rank, 1) if avg_rank else None
            previous_avg = client_scans[1].get("avg_rank") if len(client_scans) >= 2 else None
            previous = round(previous_avg, 1) if previous_avg else None

            if current and previous and current < previous:
                headline = (
                    f"You're climbing on Google Maps. When people nearby search {main_keyword}, "
                    f"you now show up around #{current} on average, up from #{previous} last month."
                )
            elif current and previous and current > previous:
                headline = (
                    f"When people nearby search {main_keyword}, you now show up around #{current} on average. "
                    f"That's down a little from #{previous} last month, and we're already working on it."
                )
            elif current:
                headline = f"When people nearby search {main_keyword}, you show up around #{current} on average."
            else:
                headline = "Your latest ranking check is still running. I'll send the numbers as soon as it's done."

            email_parts = [
                f"Subject: How {biz_name_full} is showing up on Google Maps",
                "",
                "Hi,",
                "",
                f"Quick update on {biz_name_full} this month.",
                "",
                headline,
            ]
            if map_url:
                email_parts.extend([
                    "",
                    f"Here's the map. Green stars are the spots where you're in the top 3: {map_url}",
                ])
            email_parts.extend([
                "",
                "Any questions, just hit reply.",
                "",
                "Thanks,",
            ])

            result = [TextContent(type="text", text=json.dumps({
                "business_name": biz_name_full,
                "email_draft": "\n".join(email_parts),
                "tip": "This is a starting point. Rewrite it in the sender's own voice before sending. The latest heat map image is attached when available; show it so the user can add it to the email."
            }, indent=2))]
            return with_map_image(result, latest.get("uuid"), arguments)

        elif name == "find_quick_wins":
            business_filter = arguments.get("business_name", "").lower()

            # Get scans
            scans_data = api_get("/api/scans/", params={"page_size": 100})
            scans = scans_data.get("results", [])

            if business_filter:
                scans = [s for s in scans if business_filter in s.get("business", {}).get("name", "").lower()]

            # Group by business, get latest
            by_business = {}
            for scan in scans:
                biz_name = scan.get("business", {}).get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = scan

            quick_wins = []
            for biz_name, scan in by_business.items():
                scan_detail = api_get(f"/api/scans/{scan['uuid']}/")

                for kw in scan_detail.get("keyword_results", []):
                    avg_rank = kw.get("avg_rank")
                    # Quick wins are keywords ranking 11-20 (just off page 1)
                    if avg_rank and 11 <= avg_rank <= 20:
                        quick_wins.append({
                            "business_name": biz_name,
                            "keyword": kw.get("keyword"),
                            "current_rank": round(avg_rank, 1),
                            "positions_to_page_1": round(avg_rank - 10, 1),
                            "opportunity": "High" if avg_rank <= 15 else "Medium"
                        })

            # Sort by easiest wins first
            quick_wins.sort(key=lambda x: x["current_rank"])

            return [TextContent(type="text", text=json.dumps({
                "quick_wins": quick_wins[:20],
                "total_opportunities": len(quick_wins),
                "tip": "These keywords are close to page 1. A little push (reviews, citations, GBP optimization) could get them there."
            }, indent=2))]

        elif name == "renewal_pitch":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            # Get all scans for this client
            scans_data = api_get("/api/scans/", params={"page_size": 100})
            scans = scans_data.get("results", [])
            client_scans = [s for s in scans if business_name in s.get("business", {}).get("name", "").lower()]

            if not client_scans:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No data found for '{business_name}'"
                }, indent=2))]

            biz_name_full = client_scans[0].get("business", {}).get("name", business_name)
            latest = client_scans[0]
            oldest = client_scans[-1]

            # Calculate total improvement
            current_rank = latest.get("avg_rank")
            starting_rank = oldest.get("avg_rank")
            total_improvement = None
            if current_rank and starting_rank:
                total_improvement = starting_rank - current_rank

            # Count total scans
            total_scans = len(client_scans)

            # Get keywords tracked
            keywords = latest.get("keywords", [])

            token = latest.get("public_share_token")

            pitch = {
                "business_name": biz_name_full,
                "relationship_summary": {
                    "total_scans_run": total_scans,
                    "keywords_monitored": len(keywords),
                    "first_scan_date": oldest.get("created_at"),
                    "latest_scan_date": latest.get("created_at"),
                },
                "value_delivered": {
                    "starting_avg_rank": round(starting_rank, 1) if starting_rank else None,
                    "current_avg_rank": round(current_rank, 1) if current_rank else None,
                    "total_rank_improvement": round(total_improvement, 1) if total_improvement else None,
                    "improvement_direction": "better" if total_improvement and total_improvement > 0 else "needs attention"
                },
                "renewal_talking_points": []
            }

            # Build talking points
            if total_improvement and total_improvement > 0:
                pitch["renewal_talking_points"].append(f"Improved average ranking by {round(total_improvement, 1)} positions since starting")
            if total_scans > 5:
                pitch["renewal_talking_points"].append(f"Consistent monitoring with {total_scans} scans - caught issues early")
            if current_rank and current_rank < 10:
                pitch["renewal_talking_points"].append(f"Currently ranking on page 1 (avg #{round(current_rank, 1)})")
            pitch["renewal_talking_points"].append("Continued optimization needed to maintain and improve rankings")
            pitch["renewal_talking_points"].append("Competitors are always working to outrank - stopping now risks losing gains")

            if token:
                pitch["visual_proof"] = f"https://app.localrank.so/share/{token}"

            return [TextContent(type="text", text=json.dumps(pitch, indent=2))]

        elif name == "suggest_content":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            # Get scans for this client
            scans_data = api_get("/api/scans/", params={"page_size": 50})
            scans = scans_data.get("results", [])
            client_scans = [s for s in scans if business_name in s.get("business", {}).get("name", "").lower()]

            if not client_scans:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No data found for '{business_name}'"
                }, indent=2))]

            latest = client_scans[0]
            biz_name_full = latest.get("business", {}).get("name", business_name)
            keywords = latest.get("keywords", [])

            # Generate content ideas based on keywords
            content_ideas = []
            for kw in keywords:
                content_ideas.extend([
                    {
                        "keyword": kw,
                        "content_type": "Blog Post",
                        "title_idea": f"Top 10 Tips for {kw.title()}",
                        "angle": "Educational listicle"
                    },
                    {
                        "keyword": kw,
                        "content_type": "FAQ Page",
                        "title_idea": f"Frequently Asked Questions About {kw.title()}",
                        "angle": "Answer common questions to capture voice search"
                    },
                    {
                        "keyword": kw,
                        "content_type": "Local Landing Page",
                        "title_idea": f"{kw.title()} in [City Name]",
                        "angle": "Location-specific service page"
                    }
                ])

            return [TextContent(type="text", text=json.dumps({
                "business_name": biz_name_full,
                "keywords_analyzed": keywords,
                "content_ideas": content_ideas[:15],
                "tip": "Localized content targeting these keywords can improve rankings and attract qualified leads. Offer content creation as an add-on service."
            }, indent=2))]

        elif name == "prioritize_today":
            # Get all data we need
            scans_data = api_get("/api/scans/", params={"page_size": 100})
            scans = scans_data.get("results", [])

            # Group by business
            by_business = {}
            for scan in scans:
                biz_name = scan.get("business", {}).get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = []
                by_business[biz_name].append(scan)

            priorities = {
                "urgent": [],      # Needs immediate attention
                "important": [],   # Should do today
                "quick_wins": [],  # Easy wins available
                "routine": []      # Regular maintenance
            }

            for biz_name, client_scans in by_business.items():
                latest = client_scans[0]
                avg_rank = latest.get("avg_rank")

                # Urgent: Rankings dropped significantly
                if len(client_scans) >= 2:
                    prev_avg = client_scans[1].get("avg_rank")
                    if avg_rank and prev_avg and (avg_rank - prev_avg) > 3:
                        priorities["urgent"].append({
                            "client": biz_name,
                            "task": "Investigate ranking drop",
                            "reason": f"Dropped from {round(prev_avg, 1)} to {round(avg_rank, 1)}",
                            "action": "Check GBP for issues, review recent changes, analyze competitors"
                        })

                # Important: Poor rankings need work
                if avg_rank and avg_rank > 12:
                    priorities["important"].append({
                        "client": biz_name,
                        "task": "Improve rankings",
                        "reason": f"Average rank is {round(avg_rank, 1)} - not visible enough",
                        "action": "Run SuperBoost or review GBP optimization"
                    })

                # Quick wins: Close to page 1
                scan_detail = api_get(f"/api/scans/{latest['uuid']}/")
                for kw in scan_detail.get("keyword_results", []):
                    kw_rank = kw.get("avg_rank")
                    if kw_rank and 11 <= kw_rank <= 15:
                        priorities["quick_wins"].append({
                            "client": biz_name,
                            "task": f"Push '{kw.get('keyword')}' to page 1",
                            "reason": f"Currently #{round(kw_rank, 1)} - just {round(kw_rank - 10, 1)} positions away",
                            "action": "Add citations, get a review, or boost GBP posts"
                        })
                        break  # One quick win per client

                # Routine: Clients doing well
                if avg_rank and avg_rank <= 5:
                    priorities["routine"].append({
                        "client": biz_name,
                        "task": "Monitor and maintain",
                        "reason": f"Ranking well at #{round(avg_rank, 1)}",
                        "action": "Continue current strategy, watch for competitor moves"
                    })

            # Limit results
            for key in priorities:
                priorities[key] = priorities[key][:5]

            return [TextContent(type="text", text=json.dumps({
                "today_priorities": priorities,
                "summary": {
                    "urgent_items": len(priorities["urgent"]),
                    "important_items": len(priorities["important"]),
                    "quick_wins": len(priorities["quick_wins"]),
                    "routine_checks": len(priorities["routine"])
                },
                "tip": "Start with urgent items, then quick wins for momentum"
            }, indent=2))]

        elif name == "delegate_tasks":
            # Get all data
            scans_data = api_get("/api/scans/", params={"page_size": 100})
            scans = scans_data.get("results", [])

            # Group by business
            by_business = {}
            for scan in scans:
                biz_name = scan.get("business", {}).get("name", "Unknown")
                if biz_name not in by_business:
                    by_business[biz_name] = []
                by_business[biz_name].append(scan)

            va_tasks = []
            owner_tasks = []

            for biz_name, client_scans in by_business.items():
                latest = client_scans[0]
                avg_rank = latest.get("avg_rank")
                token = latest.get("public_share_token")
                map_url = f"https://app.localrank.so/share/{token}" if token else None

                # VA can do: Report generation, data entry, basic monitoring
                va_tasks.append({
                    "client": biz_name,
                    "task": "Generate monthly report",
                    "instructions": f"Download ranking map from {map_url}, add to client folder, update tracking spreadsheet",
                    "skill_needed": "Basic"
                })

                # VA can do: Citation building
                va_tasks.append({
                    "client": biz_name,
                    "task": "Submit to 5 citation sites",
                    "instructions": "Use business details to submit to Yelp, YP, Foursquare, Hotfrog, Manta",
                    "skill_needed": "Basic"
                })

                # Owner should do: Strategy decisions
                if avg_rank and avg_rank > 10:
                    owner_tasks.append({
                        "client": biz_name,
                        "task": "Review strategy - rankings below target",
                        "reason": f"Avg rank {round(avg_rank, 1)} needs strategic intervention",
                        "skill_needed": "Expert"
                    })

                # Owner should do: Client communication for issues
                if len(client_scans) >= 2:
                    prev_avg = client_scans[1].get("avg_rank")
                    if avg_rank and prev_avg and (avg_rank - prev_avg) > 2:
                        owner_tasks.append({
                            "client": biz_name,
                            "task": "Call client about ranking drop",
                            "reason": "Proactive communication before they notice",
                            "skill_needed": "Expert"
                        })

            # Get review campaigns for VA tasks
            try:
                campaigns_data = api_get("/review-booster/campaigns/")
                campaigns = campaigns_data if isinstance(campaigns_data, list) else campaigns_data.get("results", [])
                for campaign in campaigns[:5]:
                    va_tasks.append({
                        "client": campaign.get("business_name", "Unknown"),
                        "task": "Check review campaign responses",
                        "instructions": "Log into review booster, check for new reviews, flag negative ones",
                        "skill_needed": "Basic"
                    })
            except Exception:
                pass

            return [TextContent(type="text", text=json.dumps({
                "delegate_to_va": va_tasks[:15],
                "owner_attention_required": owner_tasks[:10],
                "summary": {
                    "va_tasks": len(va_tasks),
                    "owner_tasks": len(owner_tasks)
                },
                "tip": "VA tasks are routine and process-driven. Owner tasks require expertise or client relationships."
            }, indent=2))]

        elif name == "get_boost_status":
            business_name = arguments.get("business_name", "").lower()
            if not business_name:
                return [TextContent(type="text", text="Error: business_name is required")]

            # Get business to find UUID
            businesses_data = api_get("/api/businesses/")
            businesses = businesses_data.get("results", []) if isinstance(businesses_data, dict) else businesses_data
            matching = [b for b in businesses if business_name in b.get("name", "").lower()]

            if not matching:
                return [TextContent(type="text", text=json.dumps({
                    "error": f"No business found matching '{business_name}'"
                }, indent=2))]

            business = matching[0]
            biz_uuid = business.get("uuid")
            biz_name_full = business.get("name")

            boost_status = {
                "business_name": biz_name_full,
                "localboost": {
                    "what_it_does": "Builds citations on 50+ local directories to increase local authority and NAP consistency",
                    "status": "not_purchased",
                    "citations_built": 0,
                    "deliverables": []
                },
                "superboost": {
                    "what_it_does": "Premium citation building on 100+ high-authority sites plus Google Business Profile optimization",
                    "status": "not_purchased",
                    "citations_built": 0,
                    "deliverables": []
                },
                "contentboost": {
                    "what_it_does": "AI-generated localized blog content targeting your keywords to improve topical authority",
                    "status": "not_purchased",
                    "articles_created": 0
                }
            }

            # Get bonus citations (LocalBoost/SuperBoost deliverables)
            try:
                bonus_data = api_get("/citations/bonus-citations/", params={"business": biz_uuid})
                bonus_citations = bonus_data.get("results", []) if isinstance(bonus_data, dict) else bonus_data

                for citation in bonus_citations:
                    boost_type = citation.get("boost_type", "").upper()
                    url = citation.get("url", "")
                    if boost_type == "LOCALBOOST":
                        boost_status["localboost"]["citations_built"] += 1
                        boost_status["localboost"]["status"] = "active"
                        if len(boost_status["localboost"]["deliverables"]) < 10:
                            boost_status["localboost"]["deliverables"].append(url)
                    elif boost_type == "SUPERBOOST":
                        boost_status["superboost"]["citations_built"] += 1
                        boost_status["superboost"]["status"] = "active"
                        if len(boost_status["superboost"]["deliverables"]) < 10:
                            boost_status["superboost"]["deliverables"].append(url)

            except Exception:
                pass

            # Check ContentBoost status
            try:
                # ContentBoost is tracked via has_content_boost on business
                biz_detail = api_get(f"/citations/businesses/{biz_uuid}/")
                if biz_detail.get("has_content_boost"):
                    boost_status["contentboost"]["status"] = "active"
            except Exception:
                pass

            # Get activity logs to show work done
            try:
                activity_data = api_get(f"/citations/businesses/{biz_uuid}/activity-logs/")
                activities = activity_data.get("results", []) if isinstance(activity_data, dict) else activity_data

                # Filter for boost-related activities
                boost_activities = []
                for a in activities:
                    event = a.get("event_type", "").lower()
                    if any(x in event for x in ["boost", "citation", "content", "submitted", "built"]):
                        boost_activities.append({
                            "what_happened": a.get("message") or a.get("event_type"),
                            "when": a.get("created_at")
                        })

                if boost_activities:
                    boost_status["work_completed"] = boost_activities[:10]
            except Exception:
                pass

            # Add summary
            active_boosts = []
            if boost_status["localboost"]["status"] == "active":
                active_boosts.append(f"LocalBoost ({boost_status['localboost']['citations_built']} citations)")
            if boost_status["superboost"]["status"] == "active":
                active_boosts.append(f"SuperBoost ({boost_status['superboost']['citations_built']} citations)")
            if boost_status["contentboost"]["status"] == "active":
                active_boosts.append("ContentBoost")

            boost_status["summary"] = f"Active: {', '.join(active_boosts)}" if active_boosts else "No boosts active - consider LocalBoost to build citations"

            return [TextContent(type="text", text=json.dumps(boost_status, indent=2))]

        elif name == "list_boost_activity":
            business_filter = arguments.get("business_name", "").lower()
            limit = arguments.get("limit", 20)

            activities = []

            # Get all businesses first
            businesses_data = api_get("/api/businesses/")
            businesses = businesses_data.get("results", []) if isinstance(businesses_data, dict) else businesses_data

            if business_filter:
                businesses = [b for b in businesses if business_filter in b.get("name", "").lower()]

            # Get activity for each business (limited to avoid too many API calls)
            for biz in businesses[:10]:
                biz_uuid = biz.get("uuid")
                biz_name = biz.get("name")

                try:
                    activity_data = api_get(f"/citations/businesses/{biz_uuid}/activity-logs/")
                    biz_activities = activity_data.get("results", []) if isinstance(activity_data, dict) else activity_data

                    for activity in biz_activities[:5]:
                        activities.append({
                            "business_name": biz_name,
                            "event": activity.get("event_type"),
                            "message": activity.get("message"),
                            "date": activity.get("created_at")
                        })
                except Exception:
                    continue

            # Sort by date (most recent first) and limit
            activities.sort(key=lambda x: x.get("date", ""), reverse=True)

            return [TextContent(type="text", text=json.dumps({
                "activities": activities[:limit],
                "total": len(activities),
                "tip": "Share this activity log with clients to show ongoing work"
            }, indent=2))]

        elif name == "run_audit":
            gmb_url = arguments.get("gmb_url")
            if not gmb_url:
                return [TextContent(type="text", text="Error: gmb_url is required")]

            data = api_post("/api/gmb/audit/run/", {"gmb_url": gmb_url})
            return [TextContent(type="text", text=json.dumps({
                "audit_id": data.get("audit_id"),
                "status": data.get("status"),
                "share_url": data.get("share_url"),
                "credits_deducted": data.get("credits_deducted"),
                "tip": "Use get_audit to check status and get results once completed"
            }, indent=2))]

        elif name == "get_audit":
            audit_id = arguments.get("audit_id")
            if not audit_id:
                return [TextContent(type="text", text="Error: audit_id is required")]

            data = api_get(f"/api/gmb/audit/{audit_id}/")

            # Summarize the audit results
            result = {
                "audit_id": data.get("audit_id"),
                "status": data.get("status"),
                "business_name": data.get("business_name"),
            }

            if data.get("status") == "completed":
                result["audit_score"] = data.get("audit_score")
                result["review_stats"] = data.get("review_stats")
                result["revenue_impact"] = data.get("revenue_impact")
                result["issues_identified"] = data.get("issues_identified", [])[:10]
                result["created_at"] = data.get("created_at")
                result["expires_at"] = data.get("expires_at")

                # Add share URL if available
                business_info = data.get("business_info", {})
                if business_info:
                    result["business_info"] = {
                        "name": business_info.get("name"),
                        "address": business_info.get("address"),
                        "phone": business_info.get("phone"),
                    }

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_audit_pdf":
            import base64
            audit_id = arguments.get("audit_id")
            if not audit_id:
                return [TextContent(type="text", text="Error: audit_id is required")]

            try:
                pdf_bytes = api_get_binary(f"/api/gmb/audit/{audit_id}/pdf/")
                pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                return [TextContent(type="text", text=json.dumps({
                    "audit_id": audit_id,
                    "pdf_base64": pdf_base64,
                    "size_bytes": len(pdf_bytes),
                    "tip": "Decode base64 to get PDF file"
                }, indent=2))]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    return [TextContent(type="text", text=json.dumps({
                        "error": "Audit is not complete yet. Wait for status to be 'completed'."
                    }, indent=2))]
                raise

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def run_stdio():
    """Run server with stdio transport (for Claude Desktop)"""
    set_transport("stdio")
    from mcp.server.stdio import stdio_server
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="localrank",
                server_version=CLIENT_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def run_http():
    """Run server with HTTP/SSE transport (for Claude.ai web)"""
    set_transport("sse")
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        # Extract API key from query param or OAuth token from header
        api_key = request.query_params.get("api_key", "")
        if api_key:
            current_api_key.set(api_key)
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            current_token.set(auth_header[7:])

        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    async def handle_messages(request):
        # Extract API key from query param or OAuth token from header
        api_key = request.query_params.get("api_key", "")
        if api_key:
            current_api_key.set(api_key)
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            current_token.set(auth_header[7:])
        await sse.handle_post_message(request.scope, request.receive, request._send)

    async def health(request):
        return JSONResponse({"status": "ok"})

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
            Route("/health", endpoint=health),
        ]
    )

    uvicorn.run(app, host="0.0.0.0", port=PORT)


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        run_http()
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
