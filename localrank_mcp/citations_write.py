import json
from typing import Any, Callable
from urllib.parse import urlparse

MAX_BUILDOUT_CITATIONS = 3
DEFAULT_BUILDOUT_CITATIONS = 1
SEARCH_LIMIT = 5
MAX_BATCH_ITEMS = 10


def _require_non_empty_string(arguments: dict, key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _coerce_optional_string(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("location_name must be a string")
    return value.strip()


def _coerce_optional_object(value: Any) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("location_data must be an object")
    return value


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def _coerce_requested_citations(value: Any) -> int:
    if value is None:
        return DEFAULT_BUILDOUT_CITATIONS
    if isinstance(value, bool):
        raise ValueError("requested_citations must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("requested_citations must be an integer") from exc
    if parsed < 1:
        raise ValueError("requested_citations must be at least 1")
    return parsed


def _coerce_optional_positive_int(value: Any, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{key} must be a positive integer")
    return parsed


def _normalize_text(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in (value or ""))
    return " ".join(cleaned.split())


def _normalize_phone(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _normalize_website(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _build_business_details(
    business_name: str,
    address: str,
    phone: str,
    website: str,
    description: str,
) -> dict:
    details = {
        "name": business_name,
        "address": address,
        "phone": phone,
        "phone_number": phone,
        "website": website,
    }
    if description:
        details["description"] = description
    return details


def _summarize_business(business: dict) -> dict:
    details = business.get("business_details") or {}
    citations = business.get("citations") or {}
    return {
        "uuid": business.get("uuid"),
        "name": business.get("name") or details.get("name") or "",
        "address": business.get("address") or details.get("address") or "",
        "phone": business.get("phone") or details.get("phone") or details.get("phone_number") or "",
        "website": business.get("website") or details.get("website") or "",
        "description": business.get("description") or details.get("description") or "",
        "citation_total": citations.get("total", 0),
    }


def _match_reasons(candidate: dict, requested: dict) -> list[str]:
    candidate_name = _normalize_text(candidate.get("name", ""))
    requested_name = _normalize_text(requested["business_name"])
    if not candidate_name or candidate_name != requested_name:
        return []

    reasons = ["name"]

    if _normalize_text(candidate.get("address", "")) == _normalize_text(requested["address"]):
        reasons.append("address")

    candidate_phone = _normalize_phone(candidate.get("phone", ""))
    requested_phone = _normalize_phone(requested["phone"])
    if candidate_phone and requested_phone and candidate_phone == requested_phone:
        reasons.append("phone")

    candidate_website = _normalize_website(candidate.get("website", ""))
    requested_website = _normalize_website(requested["website"])
    if candidate_website and requested_website and candidate_website == requested_website:
        reasons.append("website")

    return reasons if len(reasons) > 1 else []


def _build_guardrails() -> list[str]:
    return [
        "Only creates a business when citation search returns zero candidates.",
        "Blocks when search returns near matches or multiple exact matches instead of guessing.",
        "Only starts buildout when explicitly requested.",
        f"Hard-caps any buildout to {MAX_BUILDOUT_CITATIONS} citations per call.",
        "Blocks buildout for existing businesses that already have citations.",
    ]


def _build_batch_guardrails() -> list[str]:
    return [
        f"Batch accepts at most {MAX_BATCH_ITEMS} items per call.",
        f"Per-item buildout is still hard-capped to {MAX_BUILDOUT_CITATIONS} citations.",
        "Each item runs through the same duplicate-protection checks as ensure_citation_business.",
        "Invalid items fail closed and do not stop other valid items in the batch.",
    ]


def _summarize_requested_item(arguments: dict) -> dict:
    return {
        "business_name": arguments.get("business_name"),
        "address": arguments.get("address"),
        "phone": arguments.get("phone"),
        "website": arguments.get("website"),
        "start_buildout": _coerce_bool(arguments.get("start_buildout", False)),
        "requested_citations": arguments.get("requested_citations"),
    }


def ensure_citation_business(
    arguments: dict,
    api_get: Callable[..., dict],
    api_post: Callable[..., dict],
) -> dict:
    business_name = _require_non_empty_string(arguments, "business_name")
    address = _require_non_empty_string(arguments, "address")
    phone = _require_non_empty_string(arguments, "phone")
    website = _require_non_empty_string(arguments, "website")
    description = _coerce_optional_string(arguments.get("description"))
    location_name = _coerce_optional_string(arguments.get("location_name"))
    location_data = _coerce_optional_object(arguments.get("location_data"))
    start_buildout = _coerce_bool(arguments.get("start_buildout", False))
    requested_citations = _coerce_requested_citations(arguments.get("requested_citations")) if start_buildout else None
    max_citations_used = (
        min(requested_citations, MAX_BUILDOUT_CITATIONS) if requested_citations is not None else 0
    )

    requested_business = {
        "business_name": business_name,
        "address": address,
        "phone": phone,
        "website": website,
    }
    search_response = api_get(
        "/citations/search/",
        params={
            "name": business_name,
            "address": address,
            "phone": phone,
            "limit": SEARCH_LIMIT,
        },
    )
    search_results = search_response.get("businesses", [])
    clear_matches = []

    for raw_business in search_results:
        summary = _summarize_business(raw_business)
        reasons = _match_reasons(summary, requested_business)
        if reasons:
            clear_matches.append({**summary, "match_reasons": reasons})

    if len(clear_matches) > 1:
        return {
            "status": "blocked",
            "action": "blocked_ambiguous_match",
            "message": "Multiple exact citation businesses matched. No write was performed.",
            "search_results_count": len(search_results),
            "clear_match_count": len(clear_matches),
            "candidates": clear_matches,
            "guardrails": _build_guardrails(),
        }

    if search_results and not clear_matches:
        return {
            "status": "blocked",
            "action": "blocked_near_match_requires_review",
            "message": "Citation search found possible matches, but none were exact enough to trust automatically.",
            "search_results_count": len(search_results),
            "clear_match_count": 0,
            "candidates": [_summarize_business(candidate) for candidate in search_results],
            "guardrails": _build_guardrails(),
        }

    created_business = False
    match_reasons = []
    if clear_matches:
        business = clear_matches[0]
        business_uuid = business["uuid"]
        match_reasons = business.get("match_reasons", [])
    else:
        business_response = api_post(
            "/citations/businesses/",
            {
                "business_details": _build_business_details(
                    business_name=business_name,
                    address=address,
                    phone=phone,
                    website=website,
                    description=description,
                )
            },
        )
        business = _summarize_business(business_response)
        business_uuid = business["uuid"]
        created_business = True

    if start_buildout and not created_business and business.get("citation_total", 0) > 0:
        return {
            "status": "blocked",
            "action": "blocked_existing_business_has_citations",
            "message": "Buildout only runs for brand-new citation businesses or businesses with zero citations.",
            "search_results_count": len(search_results),
            "clear_match_count": len(clear_matches),
            "business": business,
            "guardrails": _build_guardrails(),
        }

    buildout_summary = {
        "requested": requested_citations,
        "max_citations_used": max_citations_used,
        "started": False,
        "created_citations": 0,
    }

    if start_buildout:
        buildout_location_data = {
            "address": address,
            "phone": phone,
            "website": website,
            **location_data,
        }
        buildout_response = api_post(
            "/citations/create/",
            {
                "business": business_uuid,
                "test_mode": False,
                "max_citations": max_citations_used,
                "location_name": location_name or business_name,
                "location_data": buildout_location_data,
            },
        )
        buildout_summary = {
            "requested": requested_citations,
            "max_citations_used": max_citations_used,
            "started": True,
            "created_citations": len(buildout_response.get("citations", [])),
            "message": buildout_response.get("message"),
            "status": buildout_response.get("status"),
        }

    action = "created_business" if created_business else "reused_existing_business"
    if buildout_summary["started"]:
        action = f"{action}_and_started_buildout"

    return {
        "status": "success",
        "action": action,
        "message": "Citation business is ready.",
        "search_results_count": len(search_results),
        "clear_match_count": len(clear_matches),
        "created_business": created_business,
        "match_reasons": match_reasons,
        "business": business,
        "buildout": buildout_summary,
        "guardrails": _build_guardrails(),
    }


def ensure_citation_business_batch(
    arguments: dict,
    api_get: Callable[..., dict],
    api_post: Callable[..., dict],
    ensure_item: Callable[..., dict] = ensure_citation_business,
) -> dict:
    raw_items = arguments.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("items is required and must be a non-empty list")
    if len(raw_items) > MAX_BATCH_ITEMS:
        raise ValueError(f"items may contain at most {MAX_BATCH_ITEMS} entries")

    default_start_buildout = _coerce_bool(arguments.get("start_buildout", False))
    default_requested_citations = (
        _coerce_requested_citations(arguments.get("requested_citations"))
        if default_start_buildout
        else None
    )
    max_total_requested_citations = _coerce_optional_positive_int(
        arguments.get("max_total_requested_citations"),
        "max_total_requested_citations",
    )

    requested_citations_total = 0
    results = []
    action_counts: dict[str, int] = {}

    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            error_result = {
                "status": "error",
                "action": "invalid_item",
                "message": "Each item must be an object.",
                "buildout": {
                    "started": False,
                    "requested": None,
                    "max_citations_used": 0,
                    "created_citations": 0,
                },
                "item_index": index,
                "input": None,
            }
            results.append(error_result)
            action_counts[error_result["action"]] = action_counts.get(error_result["action"], 0) + 1
            continue

        item_arguments = dict(raw_item)
        if default_start_buildout and "start_buildout" not in item_arguments:
            item_arguments["start_buildout"] = True

        start_buildout_for_item = _coerce_bool(item_arguments.get("start_buildout", False))
        if start_buildout_for_item and default_requested_citations is not None and "requested_citations" not in item_arguments:
            item_arguments["requested_citations"] = default_requested_citations

        if start_buildout_for_item and max_total_requested_citations is not None:
            requested_for_item = _coerce_requested_citations(item_arguments.get("requested_citations"))
            remaining_requested = max_total_requested_citations - requested_citations_total
            if remaining_requested <= 0:
                item_arguments["start_buildout"] = False
                item_arguments.pop("requested_citations", None)
            else:
                item_arguments["requested_citations"] = min(requested_for_item, remaining_requested)
                requested_citations_total += int(item_arguments["requested_citations"])

        try:
            item_result = ensure_item(arguments=item_arguments, api_get=api_get, api_post=api_post)
        except Exception as exc:
            action = "invalid_item" if isinstance(exc, ValueError) else "exception"
            item_result = {
                "status": "error",
                "action": action,
                "message": str(exc),
                "buildout": {
                    "started": False,
                    "requested": item_arguments.get("requested_citations"),
                    "max_citations_used": 0,
                    "created_citations": 0,
                },
            }

        item_result["item_index"] = index
        item_result["input"] = _summarize_requested_item(item_arguments)
        action_counts[item_result.get("action", "unknown")] = action_counts.get(
            item_result.get("action", "unknown"),
            0,
        ) + 1
        results.append(item_result)

    total_items = len(results)
    success_count = sum(1 for result in results if result.get("status") == "success")
    blocked_count = sum(1 for result in results if result.get("status") == "blocked")
    error_count = sum(1 for result in results if result.get("status") == "error")
    buildout_started_count = sum(
        1
        for result in results
        if bool((result.get("buildout") or {}).get("started"))
    )
    created_citations_total = sum(
        int((result.get("buildout") or {}).get("created_citations") or 0)
        for result in results
    )

    if success_count == total_items:
        status = "success"
    elif blocked_count == total_items:
        status = "blocked"
    elif error_count == total_items:
        status = "error"
    else:
        status = "partial_success"

    return {
        "status": status,
        "action": "batch_ensure_citation_businesses",
        "message": (
            f"Processed {total_items} items: {success_count} success, "
            f"{blocked_count} blocked, {error_count} errors."
        ),
        "summary": {
            "total_items": total_items,
            "success_count": success_count,
            "blocked_count": blocked_count,
            "error_count": error_count,
            "buildout_started_count": buildout_started_count,
            "created_citations_total": created_citations_total,
            "total_requested_citations": requested_citations_total,
            "max_total_requested_citations": max_total_requested_citations,
            "action_counts": action_counts,
        },
        "results": results,
        "guardrails": _build_batch_guardrails() + _build_guardrails(),
    }


def to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2)
