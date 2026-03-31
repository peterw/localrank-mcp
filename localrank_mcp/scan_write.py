import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID


DEFAULT_SCAN_TYPE = "one-time"
DEFAULT_PIN_COUNT = 35
DEFAULT_RADIUS = 5.0
DEFAULT_DUPLICATE_WINDOW_MINUTES = 30
MAX_SCAN_LIST_PAGE_SIZE = 25
MAX_KEYWORDS = 10
ACTIVE_SCAN_STATUSES = {
    "pending",
    "in-progress",
    "in_progress",
    "scheduled",
    "queued",
}


def to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def parse_datetime_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("datetime value is required")
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        dt = datetime.fromisoformat(raw)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _require_arguments(arguments: Any) -> Dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    return arguments


def _normalize_business_uuid(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("business_uuid is required")
    try:
        return str(UUID(raw))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("business_uuid must be a valid UUID") from exc


def _normalize_scan_type(value: Any) -> str:
    if value is None:
        return DEFAULT_SCAN_TYPE
    normalized = str(value).strip().lower().replace("_", "-")
    if normalized not in {"one-time", "repeating"}:
        raise ValueError("scanType must be either 'one-time' or 'repeating'")
    return normalized


def _normalize_keywords(value: Any) -> List[str]:
    if not isinstance(value, list):
        raise ValueError("keywords must be an array of strings")

    cleaned: List[str] = []
    for item in value:
        keyword = str(item or "").strip()
        if keyword:
            cleaned.append(keyword)

    if not cleaned:
        raise ValueError("keywords must include at least one non-empty keyword")
    if len(cleaned) > MAX_KEYWORDS:
        raise ValueError(f"keywords may contain at most {MAX_KEYWORDS} items")

    return cleaned


def _coerce_positive_int(value: Any, field_name: str, default: int, minimum: int = 1, maximum: Optional[int] = None) -> int:
    if value is None:
        coerced = int(default)
    elif isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    else:
        try:
            coerced = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc

    if coerced < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    if maximum is not None and coerced > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return coerced


def _coerce_positive_float(value: Any, field_name: str, default: float) -> float:
    if value is None:
        coerced = float(default)
    elif isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    else:
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be a number") from exc

    if coerced <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return coerced


def _normalize_frequency(value: Any, scan_type: str) -> Optional[str]:
    raw = str(value or "").strip()
    if scan_type == "repeating" and not raw:
        raise ValueError("frequency is required when scanType is 'repeating'")
    return raw or None


def _keywords_signature(keywords: Iterable[str]) -> tuple:
    return tuple(sorted(str(keyword).strip().lower() for keyword in keywords if str(keyword).strip()))


def _extract_scan_type(scan: Dict[str, Any]) -> str:
    raw_value = scan.get("scanType")
    if raw_value is None:
        raw_value = scan.get("scan_type")
    try:
        return _normalize_scan_type(raw_value)
    except ValueError:
        return DEFAULT_SCAN_TYPE


def _extract_scan_keywords(scan: Dict[str, Any]) -> List[str]:
    keywords = scan.get("keywords") or []
    if isinstance(keywords, list):
        return [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
    return []


def _extract_scan_business_uuid(scan: Dict[str, Any]) -> Optional[str]:
    if isinstance(scan.get("business"), dict):
        value = scan.get("business", {}).get("uuid")
        if value:
            return str(value)
    value = scan.get("business_uuid")
    if value:
        return str(value)
    return None


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _find_recent_duplicates(
    scans: Iterable[Dict[str, Any]],
    *,
    business_uuid: str,
    scan_type: str,
    keyword_signature: tuple,
    now_utc: datetime,
    window_minutes: int,
) -> Dict[str, Any]:
    window_start = now_utc - timedelta(minutes=window_minutes)

    scanned_count = 0
    recent_active_count = 0
    matching_recent: List[Dict[str, Any]] = []

    for scan in scans:
        if not isinstance(scan, dict):
            continue
        scanned_count += 1

        if _extract_scan_business_uuid(scan) != business_uuid:
            continue
        if _extract_scan_type(scan) != scan_type:
            continue

        created_at_raw = scan.get("created_at")
        try:
            created_at = parse_datetime_utc(created_at_raw)
        except Exception:  # noqa: BLE001
            continue

        if created_at < window_start or created_at > now_utc:
            continue

        status_normalized = _normalize_status(scan.get("status"))
        if status_normalized not in ACTIVE_SCAN_STATUSES:
            continue

        recent_active_count += 1

        if _keywords_signature(_extract_scan_keywords(scan)) != keyword_signature:
            continue

        matching_recent.append(
            {
                "uuid": scan.get("uuid"),
                "created_at": scan.get("created_at"),
                "status": scan.get("status"),
                "scanType": scan.get("scanType") or scan.get("scan_type"),
            }
        )

    return {
        "window_minutes": window_minutes,
        "scanned_count": scanned_count,
        "recent_active_count": recent_active_count,
        "matching_recent_count": len(matching_recent),
        "matching_recent": matching_recent,
    }


def create_scan_run(
    arguments: Dict[str, Any],
    *,
    api_get,
    api_post,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    args = _require_arguments(arguments)

    business_uuid = _normalize_business_uuid(args.get("business_uuid"))
    keywords = _normalize_keywords(args.get("keywords"))
    scan_type_value = args.get("scanType") if "scanType" in args else args.get("scan_type")
    scan_type = _normalize_scan_type(scan_type_value)
    frequency = _normalize_frequency(args.get("frequency"), scan_type)
    pin_count_value = args.get("pinCount") if "pinCount" in args else args.get("pin_count")
    pin_count = _coerce_positive_int(pin_count_value, "pinCount", DEFAULT_PIN_COUNT)
    radius = _coerce_positive_float(args.get("radius"), "radius", DEFAULT_RADIUS)
    duplicate_window_minutes = _coerce_positive_int(
        args.get("duplicate_window_minutes"),
        "duplicate_window_minutes",
        DEFAULT_DUPLICATE_WINDOW_MINUTES,
        minimum=1,
        maximum=24 * 60,
    )
    allow_duplicate_recent = bool(args.get("allow_duplicate_recent", False))

    request_snapshot = {
        "business_uuid": business_uuid,
        "scanType": scan_type,
        "keyword_count": len(keywords),
        "keywords": keywords,
        "pinCount": pin_count,
        "radius": radius,
        "frequency": frequency,
        "test_mode": bool(args.get("test_mode", False)),
    }

    now = now_utc or datetime.now(timezone.utc)

    existing_scans_data = api_get(
        "/api/scans/",
        params={
            "business": business_uuid,
            "page_size": MAX_SCAN_LIST_PAGE_SIZE,
        },
    )
    existing_scans = existing_scans_data.get("results", []) if isinstance(existing_scans_data, dict) else []

    keyword_signature = _keywords_signature(keywords)
    duplicate_check = _find_recent_duplicates(
        existing_scans,
        business_uuid=business_uuid,
        scan_type=scan_type,
        keyword_signature=keyword_signature,
        now_utc=now,
        window_minutes=duplicate_window_minutes,
    )

    if duplicate_check["matching_recent_count"] > 0 and not allow_duplicate_recent:
        return {
            "status": "blocked",
            "action": "blocked_recent_duplicate_scan",
            "created_scan": False,
            "message": "A matching scan was already started recently. Reuse that run or set allow_duplicate_recent=true.",
            "request": request_snapshot,
            "duplicate_check": {
                **duplicate_check,
                "override_used": False,
            },
            "scan": {},
        }

    payload = {
        "business_uuid": business_uuid,
        "scanType": scan_type,
        "keywords": keywords,
        "pinCount": pin_count,
        "radius": radius,
        "test_mode": bool(args.get("test_mode", False)),
    }
    if frequency:
        payload["frequency"] = frequency

    created = api_post("/api/scans/", payload)

    return {
        "status": "success",
        "action": "created_scan_run",
        "created_scan": True,
        "message": "Scan run started.",
        "request": request_snapshot,
        "duplicate_check": {
            **duplicate_check,
            "override_used": allow_duplicate_recent,
        },
        "scan": {
            "uuid": created.get("uuid"),
            "status": created.get("status"),
            "scanType": created.get("scanType") or created.get("scan_type"),
            "created_at": created.get("created_at"),
            "business_uuid": (created.get("business") or {}).get("uuid") if isinstance(created.get("business"), dict) else None,
            "business_name": (created.get("business") or {}).get("name") if isinstance(created.get("business"), dict) else None,
            "keywords": created.get("keywords"),
        },
    }
