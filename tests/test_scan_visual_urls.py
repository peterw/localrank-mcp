import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import localrank_mcp


class ScanVisualUrlTests(unittest.TestCase):
    def assert_url_query(self, url, expected):
        parsed = urlparse(url)
        self.assertEqual(parse_qs(parsed.query), expected)

    def test_scan_summary_includes_map_grid_image_urls(self):
        summary = localrank_mcp.summarize_scan(
            {
                "uuid": "scan-123",
                "business": {"name": "Example Dental"},
                "public_share_token": "token-123",
                "keywords": ["dentist near me"],
            }
        )

        self.assertEqual(
            summary["map_grid_image_png_url"],
            "https://app.localrank.so/api/scans/scan-123/map-grid-image?format=png",
        )
        self.assertEqual(
            summary["map_grid_image_jpg_url"],
            "https://app.localrank.so/api/scans/scan-123/map-grid-image?format=jpg",
        )
        self.assertEqual(summary["map_grid_image_auth"], "Use the same Authorization header as MCP/API requests.")

    def test_scan_detail_includes_keyword_map_grid_image_urls(self):
        summary = localrank_mcp.summarize_scan_detail(
            {
                "uuid": "scan-123",
                "business": {"name": "Example Dental"},
                "public_share_token": "token-123",
                "keyword_results": [
                    {"term": "dentist near me", "avg_rank": 3.2, "best_rank": 1, "found_count": 30},
                ],
            }
        )

        self.assertTrue(
            summary["keyword_rankings"][0]["map_grid_image_png_url"].startswith(
                "https://app.localrank.so/api/scans/scan-123/map-grid-image?"
            )
        )
        self.assert_url_query(
            summary["keyword_rankings"][0]["map_grid_image_png_url"],
            {"keyword": ["dentist near me"], "format": ["png"]},
        )
        self.assert_url_query(
            summary["keyword_rankings"][0]["map_grid_image_jpg_url"],
            {"keyword": ["dentist near me"], "format": ["jpg"]},
        )


if __name__ == "__main__":
    unittest.main()
