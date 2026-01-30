#!/usr/bin/env python3
"""
LocalRank MCP Server - Read-only API access for AI agents

Supports both stdio (Claude Desktop) and HTTP/SSE (Claude.ai web) transports.
- stdio: Uses LOCALRANK_API_KEY env var
- HTTP/SSE: Uses API key from query param (?api_key=lr_xxx) or OAuth Bearer token
"""
import os
import json
import asyncio
from contextvars import ContextVar
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent

API_BASE = os.getenv("LOCALRANK_API_URL", "https://api.localrank.so")
API_KEY = os.getenv("LOCALRANK_API_KEY", "")  # For stdio mode
PORT = int(os.getenv("PORT", "8000"))

# Context vars for HTTP mode auth
current_token: ContextVar[str] = ContextVar("current_token", default="")
current_api_key: ContextVar[str] = ContextVar("current_api_key", default="")

server = Server("localrank")

def api_get(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GET request to LocalRank API"""
    token = current_token.get()
    api_key = current_api_key.get()
    if token:
        # OAuth token from HTTP mode
        headers = {"Authorization": f"Bearer {token}"}
    elif api_key:
        # API key from query param (HTTP mode)
        headers = {"Authorization": f"Api-Key {api_key}"}
    elif API_KEY:
        # API key from env (stdio mode)
        headers = {"Authorization": f"Api-Key {API_KEY}"}
    else:
        raise ValueError("No authentication provided. Use ?api_key=lr_xxx in URL.")
    resp = httpx.get(f"{API_BASE}{endpoint}", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="list_scans",
            description="List rank tracking scans. Filter by business_name to find a specific client. Returns view_url and embed_url for visual map reports.",
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
            description="Get ranking details for a scan. Returns keyword rankings and view_url/embed_url for visual map reports to share with clients.",
            inputSchema={
                "type": "object",
                "properties": {"scan_id": {"type": "string", "description": "The scan UUID"}},
                "required": ["scan_id"]
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
    ]


def get_visual_urls(token: str) -> dict:
    """Generate visual report URLs from share token"""
    return {
        "view_url": f"https://app.localrank.so/share/{token}",
        "embed_url": f"https://app.localrank.so/share/{token}?embed=true",
    }

def summarize_scan(scan: dict) -> dict:
    """Return lightweight scan summary with share URLs"""
    token = scan.get("public_share_token")
    urls = get_visual_urls(token) if token else {}
    return {
        "uuid": scan.get("uuid"),
        "business_name": scan.get("business", {}).get("name"),
        "keywords": scan.get("keywords", []),
        "status": scan.get("status"),
        "created_at": scan.get("created_at"),
        "avg_rank": scan.get("avg_rank"),
        "scanType": scan.get("scanType"),
        **urls,
    }

def summarize_scan_detail(scan: dict) -> dict:
    """Return scan detail with keyword rankings but without heavy grid data"""
    token = scan.get("public_share_token")
    urls = get_visual_urls(token) if token else {}
    keyword_summary = []
    for kw in scan.get("keyword_results", []):
        keyword_summary.append({
            "keyword": kw.get("keyword"),
            "avg_rank": kw.get("avg_rank"),
            "best_rank": kw.get("best_rank"),
            "found_count": kw.get("found_count"),
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
    }

@server.call_tool()
async def call_tool(name: str, arguments: dict):
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
                "tip": "Use view_url for visual map, embed_url for iframe embed"
            }, indent=2))]

        elif name == "get_scan":
            data = api_get(f"/api/scans/{arguments['scan_id']}/")
            summary = summarize_scan_detail(data)
            return [TextContent(type="text", text=json.dumps(summary, indent=2))]

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

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API Error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def run_stdio():
    """Run server with stdio transport (for Claude Desktop)"""
    from mcp.server.stdio import stdio_server
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="localrank",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def run_http():
    """Run server with HTTP/SSE transport (for Claude.ai web)"""
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
