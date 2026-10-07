"""Permanent client report links.

One URL per client business. It never changes unless the agency makes a new link,
and it always shows that business's newest completed scan, so it can go into a
recurring client email once. The get/disable tools are write tools: they only ever
act on one business, picked by UUID or by an exact, unambiguous name. Listing is
read-only. LocalRank never sends the email: the backend returns a ready draft
(the same text the app copies) and the agency or its agent sends it.
"""
import html
import re
import uuid

CID_IN_URL = re.compile(r"[?&]cid=(\d+)")
ENDPOINT = "/business/api/businesses/{}/client_report/"
LIST_ENDPOINT = "/business/api/client-reports/"
LINK_NOTE = (
    "This URL stays the same and always shows the newest completed scan. "
    "Paste it into the client's monthly email once; no login needed. "
    "email_draft is a ready subject and body; LocalRank does not send it."
)
NOT_SCHEDULED = (
    "No scan is scheduled for this business, so the link will not update on its own. "
    "Tell the user before sending. A recurring scan uses credits, so ask before scheduling one."
)


class BusinessNotFound(ValueError):
    """Raised before any write when the business cannot be picked safely."""


def business_records(items):
    """Flatten /api/businesses/ (grouped by place) into one record per business UUID."""
    records = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        candidates = [item.get("representative_business") or item]
        candidates.extend(scan.get("business") or {} for scan in item.get("scans") or [] if isinstance(scan, dict))
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("uuid"):
                records.setdefault(candidate["uuid"], candidate)
    return list(records.values())


def _name(record):
    return html.unescape(str(record.get("name") or "")).strip().casefold()


def _identity(record):
    """The Google identifier the backend uses to pick a business's scans."""
    cid = str(record.get("cid") or "").strip()
    if not cid.isdigit():
        match = CID_IN_URL.search(record.get("url") or "")
        cid = match.group(1) if match else ""
    if cid:
        return f"cid:{cid}"
    return f"place:{record['place_id']}" if record.get("place_id") else f"uuid:{record['uuid']}"


def _choices(records):
    return [{"uuid": r.get("uuid"), "name": r.get("name"), "address": r.get("address")} for r in records[:5]]


def resolve_business(value, api_get):
    """Return the business UUID for a UUID or an exact business name."""
    value = str(value or "").strip()
    if not value:
        raise BusinessNotFound("business is required: a business UUID or its exact name.")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        pass

    records, page = [], 1
    while True:
        data = api_get("/api/businesses/", params={"page": page, "page_size": 100})
        records.extend(business_records(data.get("results", []) if isinstance(data, dict) else data))
        if not isinstance(data, dict) or not data.get("next"):
            break
        page += 1

    wanted = html.unescape(value).casefold()
    exact = [r for r in records if _name(r) == wanted]
    # Several records for one place (re-added, different map URL) are the same client.
    locations = {}
    for record in exact:
        locations.setdefault(_identity(record), record)
    if len(locations) == 1:
        return next(iter(locations.values()))["uuid"]
    if locations:
        raise BusinessNotFound(
            f"'{value}' matches {len(locations)} different locations. Pass one uuid: "
            f"{_choices(list(locations.values()))}")
    similar = [r for r in records if wanted in _name(r)]
    hint = f" Similar: {_choices(similar)}" if similar else " Use list_businesses to find the exact name or uuid."
    raise BusinessNotFound(f"No business is named exactly '{value}'.{hint}")


def client_report_link(business, *, disable, api_get, api_post, api_delete, app_base):
    business_id = resolve_business(business, api_get)
    endpoint = ENDPOINT.format(business_id)
    if disable:
        api_delete(endpoint)
        return {"business_id": business_id, "live": False, "url": None,
                "message": "Client link turned off. The old URL now shows 'This report is no longer available'."}
    state = api_post(endpoint, {})
    live = bool(state.get("live") and state.get("token"))
    if not live:
        return {"business": state.get("business_name"), "business_id": business_id, "live": False, "url": None,
                "message": "The link could not be turned on."}
    result = {"business_id": business_id, "live": True, **_sendable(state, app_base)}
    result["message"] = LINK_NOTE if result["next_scan_date"] else f"{LINK_NOTE} {NOT_SCHEDULED}"
    return result


def _sendable(state, app_base):
    """What an agent needs to send one client its monthly email."""
    return {
        "business": state.get("business_name"),
        "url": f"{app_base.rstrip('/')}/share/report/{state['token']}",
        "latest_scan_date": state.get("latest_scan_date"),
        "next_scan_date": state.get("next_scan_date"),
        "email_draft": state.get("email_draft"),
    }


def list_client_report_links(*, api_get, app_base):
    """Every live client link in the account with its email draft: the whole monthly send in one call."""
    states = api_get(LIST_ENDPOINT)
    links = [_sendable(state, app_base) for state in states or [] if state.get("live") and state.get("token")]
    stale = [link["business"] for link in links if not link["next_scan_date"]]
    message = (f"{len(links)} live client link(s). Each email_draft is a ready subject and body; "
               "LocalRank does not send it.") if links else (
        "No live client links yet. Use get_client_report_link to turn one on for a business.")
    if stale:
        links_word = "that link will not update on its own" if len(stale) == 1 else \
            "those links will not update on their own"
        message += (f" No scan is scheduled for {', '.join(stale)}, so {links_word}. Tell the user before sending; "
                    "a recurring scan uses credits, so ask before scheduling one.")
    return {"count": len(links), "links": links, "message": message}
