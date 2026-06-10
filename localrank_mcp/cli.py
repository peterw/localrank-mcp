"""LocalRank CLI — drive LocalRank from the terminal or from coding agents.

Thin command layer over the same API client and write guardrails the MCP
server uses. All commands print JSON to stdout so output is directly
machine-readable; errors print JSON to stderr and exit non-zero.

Auth: set LOCALRANK_API_KEY (create one at https://app.localrank.so/mcp).
"""

import argparse
import json
import logging
import os
import sys

import httpx


def _fail(message: str, **extra) -> None:
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    sys.exit(1)


def _client():
    """Import the shared API helpers, failing with a clear message if the
    API key is missing (the helpers read LOCALRANK_API_KEY at import)."""
    if not os.getenv("LOCALRANK_API_KEY"):
        _fail(
            "LOCALRANK_API_KEY is not set.",
            fix="Create an API key at https://app.localrank.so/mcp and run: export LOCALRANK_API_KEY=lr_...",
        )
    from localrank_mcp import api_get, api_post

    return api_get, api_post


def _print(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_auth(_args) -> None:
    api_get, _ = _client()
    data = api_get("/api/scans/", params={"page_size": 1})
    _print({"authenticated": True, "total_scans": data.get("count")})


def cmd_businesses_list(args) -> None:
    api_get, _ = _client()
    data = api_get("/api/businesses/")
    results = data.get("results", []) if isinstance(data, dict) else data
    if args.search:
        needle = args.search.lower()
        results = [b for b in results if needle in (b.get("name") or "").lower()]
    _print(
        {
            "count": len(results),
            "businesses": [
                {
                    "uuid": b.get("uuid"),
                    "name": b.get("name"),
                    "place_id": b.get("place_id"),
                }
                for b in results
            ],
        }
    )


def cmd_scans_list(args) -> None:
    from localrank_mcp import summarize_scan

    api_get, _ = _client()
    data = api_get("/api/scans/", params={"page_size": min(args.limit, 50)})
    results = data.get("results", [])
    if args.business:
        needle = args.business.lower()
        results = [
            s
            for s in results
            if needle in (s.get("business", {}) or {}).get("name", "").lower()
        ]
    _print(
        {
            "count": len(results),
            "total": data.get("count"),
            "scans": [summarize_scan(s) for s in results],
        }
    )


def cmd_scans_get(args) -> None:
    from localrank_mcp import summarize_scan_detail

    api_get, _ = _client()
    data = api_get(f"/api/scans/{args.scan_id}/")
    _print(summarize_scan_detail(data))


def cmd_scans_run(args) -> None:
    from localrank_mcp.scan_write import create_scan_run

    api_get, api_post = _client()
    arguments = {
        "business_uuid": args.business_uuid,
        "keywords": [k.strip() for k in args.keywords.split(",") if k.strip()],
        "scanType": args.scan_type,
        "pinCount": args.pins,
        "radius": args.radius,
        "test_mode": args.test_mode,
        "allow_duplicate_recent": args.allow_duplicate,
    }
    if args.frequency:
        arguments["frequency"] = args.frequency
    result = create_scan_run(arguments, api_get=api_get, api_post=api_post)
    _print(result)


def cmd_citations_list(args) -> None:
    api_get, _ = _client()
    data = api_get("/citations/list/")
    results = data.get("results", []) if isinstance(data, dict) else data
    if args.business and isinstance(results, list):
        needle = args.business.lower()
        results = [
            c for c in results if needle in str(c.get("business_name", "")).lower()
        ]
    _print({"count": len(results), "citations": results[: args.limit]})


def cmd_citations_build(args) -> None:
    from localrank_mcp.citations_write import ensure_citation_business

    api_get, api_post = _client()
    arguments = {
        "business_name": args.name,
        "address": args.address,
        "phone": args.phone,
        "website": args.website,
        "start_buildout": args.start,
    }
    if args.description:
        arguments["description"] = args.description
    if args.citations:
        arguments["requested_citations"] = args.citations
    result = ensure_citation_business(arguments, api_get, api_post)
    _print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localrank",
        description=(
            "LocalRank CLI — Google Maps rank tracking and citation building. "
            "JSON output on every command. Auth via LOCALRANK_API_KEY "
            "(create one at https://app.localrank.so/mcp)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth", help="Verify the API key works")
    p.set_defaults(func=cmd_auth)

    businesses = sub.add_parser("businesses", help="Businesses on the account")
    bsub = businesses.add_subparsers(dest="subcommand", required=True)
    p = bsub.add_parser("list", help="List businesses")
    p.add_argument("--search", help="Filter by business name")
    p.set_defaults(func=cmd_businesses_list)

    scans = sub.add_parser("scans", help="Google Maps rank scans (geogrid)")
    ssub = scans.add_subparsers(dest="subcommand", required=True)

    p = ssub.add_parser("list", help="List recent scans")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--business", help="Filter by business name")
    p.set_defaults(func=cmd_scans_list)

    p = ssub.add_parser("get", help="Get one scan with results")
    p.add_argument("scan_id")
    p.set_defaults(func=cmd_scans_get)

    p = ssub.add_parser("run", help="Start a scan (duplicate-guarded)")
    p.add_argument("--business-uuid", required=True)
    p.add_argument("--keywords", required=True, help="Comma-separated keywords")
    p.add_argument("--pins", type=int, default=None, help="Grid pin count")
    p.add_argument("--radius", type=float, default=None, help="Radius in miles")
    p.add_argument(
        "--scan-type", choices=["one-time", "repeating"], default="one-time"
    )
    p.add_argument("--frequency", help="For repeating scans, e.g. weekly")
    p.add_argument("--test-mode", action="store_true", help="Free test scan")
    p.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Override the recent-duplicate guardrail",
    )
    p.set_defaults(func=cmd_scans_run)

    citations = sub.add_parser("citations", help="Citation building (LocalBoost)")
    csub = citations.add_subparsers(dest="subcommand", required=True)

    p = csub.add_parser("list", help="List citations and their status")
    p.add_argument("--business", help="Filter by business name")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_citations_list)

    p = csub.add_parser(
        "build",
        help="Ensure a citation business exists; optionally start a buildout",
    )
    p.add_argument("--name", required=True, help="Business name")
    p.add_argument("--address", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--website", required=True)
    p.add_argument("--description")
    p.add_argument(
        "--start", action="store_true", help="Start the citation buildout"
    )
    p.add_argument(
        "--citations", type=int, help="Citation count for the buildout"
    )
    p.set_defaults(func=cmd_citations_build)

    return parser


def main() -> None:
    # Keep stdout/stderr clean JSON for agents; silence httpx request logging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = build_parser().parse_args()
    try:
        args.func(args)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        _fail(
            f"API request failed with HTTP {exc.response.status_code}",
            url=str(exc.request.url),
            body=body,
        )
    except ValueError as exc:
        _fail(str(exc))


if __name__ == "__main__":
    main()
