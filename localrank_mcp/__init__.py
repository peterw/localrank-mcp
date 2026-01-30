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
        Tool(
            name="client_report",
            description="Generate a client report comparing recent scans. Shows ranking changes, wins (improved), drops (declined), and visual map URL. Perfect for sending to clients.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name to search for"}
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
            return [TextContent(type="text", text=json.dumps(report, indent=2))]

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
