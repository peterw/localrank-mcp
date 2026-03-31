import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "localrank_mcp" / "scan_write.py"
SPEC = importlib.util.spec_from_file_location("localrank_mcp_scan_write", MODULE_PATH)
scan_write = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(scan_write)


class CreateScanRunTests(unittest.TestCase):
    def test_blocks_recent_duplicate_scan_when_guard_enabled(self):
        api_get = Mock(
            return_value={
                "results": [
                    {
                        "uuid": "scan-existing",
                        "business": {"uuid": "11111111-1111-1111-1111-111111111111"},
                        "keywords": ["plumber near me", "water heater repair"],
                        "scanType": "one-time",
                        "status": "PENDING",
                        "created_at": "2026-03-31T12:00:00Z",
                    }
                ]
            }
        )
        api_post = Mock()

        result = scan_write.create_scan_run(
            {
                "business_uuid": "11111111-1111-1111-1111-111111111111",
                "keywords": ["Plumber Near Me", "Water Heater Repair"],
                "scanType": "one-time",
                "duplicate_window_minutes": 60,
            },
            api_get=api_get,
            api_post=api_post,
            now_utc=scan_write.parse_datetime_utc("2026-03-31T12:15:00Z"),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["action"], "blocked_recent_duplicate_scan")
        self.assertEqual(result["duplicate_check"]["matching_recent_count"], 1)
        api_post.assert_not_called()

    def test_requires_frequency_for_repeating_scan(self):
        with self.assertRaisesRegex(ValueError, "frequency is required"):
            scan_write.create_scan_run(
                {
                    "business_uuid": "11111111-1111-1111-1111-111111111111",
                    "keywords": ["plumber near me"],
                    "scanType": "repeating",
                },
                api_get=Mock(return_value={"results": []}),
                api_post=Mock(),
            )

    def test_posts_scan_payload_when_no_duplicate(self):
        api_get = Mock(
            return_value={
                "results": [
                    {
                        "uuid": "old-scan",
                        "business": {"uuid": "11111111-1111-1111-1111-111111111111"},
                        "keywords": ["plumber near me"],
                        "scanType": "one-time",
                        "status": "COMPLETED",
                        "created_at": "2026-03-31T10:00:00Z",
                    }
                ]
            }
        )
        api_post = Mock(
            return_value={
                "uuid": "new-scan",
                "status": "PENDING",
                "scanType": "one-time",
                "business": {"uuid": "11111111-1111-1111-1111-111111111111", "name": "Acme Plumbing"},
                "keywords": ["plumber near me"],
                "created_at": "2026-03-31T12:15:00Z",
            }
        )

        result = scan_write.create_scan_run(
            {
                "business_uuid": "11111111-1111-1111-1111-111111111111",
                "keywords": ["Plumber Near Me"],
                "scanType": "one-time",
                "pinCount": 35,
                "radius": 5,
                "duplicate_window_minutes": 30,
            },
            api_get=api_get,
            api_post=api_post,
            now_utc=scan_write.parse_datetime_utc("2026-03-31T12:15:00Z"),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "created_scan_run")
        self.assertEqual(result["scan"]["uuid"], "new-scan")
        self.assertEqual(result["duplicate_check"]["matching_recent_count"], 0)

        self.assertEqual(api_post.call_count, 1)
        self.assertEqual(api_post.call_args.args[0], "/api/scans/")
        payload = api_post.call_args.args[1]
        self.assertEqual(payload["business_uuid"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(payload["scanType"], "one-time")
        self.assertEqual(payload["keywords"], ["Plumber Near Me"])
        self.assertEqual(payload["pinCount"], 35)
        self.assertEqual(payload["radius"], 5.0)


if __name__ == "__main__":
    unittest.main()
