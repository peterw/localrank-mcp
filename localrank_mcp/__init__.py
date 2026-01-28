#!/usr/bin/env python3
"""
LocalRank MCP Server - Read-only API access for AI agents

Supports both stdio (Claude Desktop) and HTTP/SSE (Claude.ai web) transports.
"""
import os
import json
import asyncio
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent

API_BASE = os.getenv("LOCALRANK_API_URL", "https://api.localrank.so")
API_KEY = os.getenv("LOCALRANK_API_KEY", "")
PORT = int(os.getenv("PORT", "8000"))

server = Server("localrank")

def api_get(endpoint: str, params: dict = None) -> dict:
    """Make authenticated GET request to LocalRank API"""
    headers = {"Authorization": f"Api-Key {API_KEY}"}
    resp = httpx.get(f"{API_BASE}{endpoint}", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="list_scans",
            description="List all rank tracking scans. Returns scan ID, URL, keywords, and current rankings.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_scan",
            description="Get detailed ranking data for a specific scan",
            inputSchema={
                "type": "object",
                "properties": {"scan_id": {"type": "string", "description": "The scan UUID"}},
                "required": ["scan_id"]
            }
        ),
        Tool(
            name="list_citations",
            description="List all citations for the user's businesses",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="list_businesses",
            description="List all businesses/locations being tracked",
            inputSchema={"type": "object", "properties": {}}
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


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "list_scans":
            data = api_get("/api/scans/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "get_scan":
            data = api_get(f"/api/scans/{arguments['scan_id']}/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "list_citations":
            data = api_get("/citations/list/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "list_businesses":
            data = api_get("/api/businesses/")
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

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
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    async def handle_messages(request):
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
