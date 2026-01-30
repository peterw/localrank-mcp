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
            description="Generate a monthly update email for a client. Includes wins, current rankings, and next steps. Ready to copy-paste and send.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_name": {"type": "string", "description": "Client business name"}
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

            # Calculate changes if we have previous scan
            wins = []
            drops = []
            if len(client_scans) >= 2:
                current_avg = latest.get("avg_rank")
                previous_avg = client_scans[1].get("avg_rank")
                if current_avg and previous_avg:
                    change = previous_avg - current_avg
                    if change > 0:
                        wins.append(f"Overall ranking improved by {round(change, 1)} positions")
                    elif change < 0:
                        drops.append(f"Rankings dropped by {round(abs(change), 1)} positions - we're working on recovery")

            # Build email
            token = latest.get("public_share_token")
            map_url = f"https://app.localrank.so/share/{token}" if token else None

            email_parts = [
                f"Subject: {biz_name_full} - Monthly SEO Update",
                "",
                f"Hi,",
                "",
                f"Here's your monthly local SEO update for {biz_name_full}.",
                "",
                f"**Current Performance:**",
                f"- Average Local Rank: #{round(avg_rank, 1) if avg_rank else 'N/A'}",
                f"- Keywords Tracked: {len(keywords)}",
            ]

            if wins:
                email_parts.append("")
                email_parts.append("**Wins This Period:**")
                for win in wins:
                    email_parts.append(f"- {win}")

            if drops:
                email_parts.append("")
                email_parts.append("**Areas of Focus:**")
                for drop in drops:
                    email_parts.append(f"- {drop}")

            if map_url:
                email_parts.append("")
                email_parts.append(f"**View Your Ranking Map:** {map_url}")

            email_parts.extend([
                "",
                "Let me know if you have any questions!",
                "",
                "Best regards"
            ])

            return [TextContent(type="text", text=json.dumps({
                "business_name": biz_name_full,
                "email_draft": "\n".join(email_parts),
                "tip": "Customize this email with specific insights before sending"
            }, indent=2))]

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
