import asyncio
import base64
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("LOCALRANK_API_KEY", "lr_test")

import localrank_mcp  # noqa: E402

# Another test module may import localrank_mcp first, before the env var is set.
localrank_mcp.API_KEY = localrank_mcp.API_KEY or "lr_test"

JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"


def image_response(status=200, content_type="image/jpeg", content=JPEG_BYTES):
    return httpx.Response(status, headers={"content-type": content_type}, content=content,
                          request=httpx.Request("GET", "https://app.localrank.so/x"))


def run(coro):
    return asyncio.run(coro)


class UsageTaggingTests(unittest.TestCase):
    def test_api_requests_carry_tool_and_transport_in_user_agent(self):
        localrank_mcp.set_transport("sse")
        localrank_mcp.current_tool.set("client_report")
        with mock.patch.object(localrank_mcp.httpx, "get") as get:
            get.return_value = httpx.Response(200, json={}, request=httpx.Request("GET", "https://api"))
            localrank_mcp.api_get("/api/businesses/")
        headers = get.call_args.kwargs["headers"]
        self.assertEqual(
            headers["User-Agent"],
            f"localrank-mcp/{localrank_mcp.CLIENT_VERSION} (transport=sse; tool=client_report)",
        )
        self.assertTrue(headers["Authorization"].startswith("Api-Key "))

    def test_call_tool_sets_current_tool(self):
        with mock.patch.object(localrank_mcp, "api_get", return_value={"results": [], "count": 0}):
            run(localrank_mcp.call_tool("list_businesses", {}))
        # call_tool runs in its own context under asyncio.run, so check via a direct call.
        async def probe():
            await localrank_mcp.call_tool("list_businesses", {})
            return localrank_mcp.current_tool.get()
        with mock.patch.object(localrank_mcp, "api_get", return_value={"results": [], "count": 0}):
            self.assertEqual(run(probe()), "list_businesses")


class PromptTests(unittest.TestCase):
    def test_lists_three_prompts(self):
        prompts = run(localrank_mcp.list_prompts())
        self.assertEqual(
            [p.name for p in prompts],
            ["monthly-client-update", "whats-changed-this-week", "renewal-pitch"],
        )
        monthly = prompts[0]
        self.assertEqual([(a.name, a.required) for a in monthly.arguments], [("business_name", True)])

    def test_get_prompt_fills_business_name_and_names_existing_tools(self):
        result = run(localrank_mcp.get_prompt("monthly-client-update", {"business_name": "Acme {Plumbing}"}))
        text = result.messages[0].content.text
        self.assertIn('business_name="Acme {Plumbing}"', text)
        self.assertIn("client_report", text)
        self.assertIn("draft_client_email", text)
        self.assertIn("Do not change anything", text)

    def test_every_tool_named_in_a_prompt_exists(self):
        tool_names = {t.name for t in run(localrank_mcp.list_tools())}
        for name, spec in localrank_mcp.PROMPTS.items():
            named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", spec["text"])) - {"business_name"}
            self.assertTrue(named, name)
            self.assertLessEqual(named, tool_names, f"{name} names unknown tools")

    def test_missing_required_argument_raises(self):
        with self.assertRaises(ValueError):
            run(localrank_mcp.get_prompt("renewal-pitch", {}))

    def test_unknown_prompt_raises(self):
        with self.assertRaises(ValueError):
            run(localrank_mcp.get_prompt("nope", {}))


class MapImageTests(unittest.TestCase):
    def test_fetch_map_image_returns_image_content(self):
        with mock.patch.object(localrank_mcp.httpx, "get", return_value=image_response()) as get:
            image = localrank_mcp.fetch_map_image("scan-1")
        self.assertEqual(image.type, "image")
        self.assertEqual(image.mimeType, "image/jpeg")
        self.assertEqual(base64.b64decode(image.data), JPEG_BYTES)
        self.assertEqual(get.call_args.args[0], "https://app.localrank.so/api/scans/scan-1/map-grid-image")
        self.assertEqual(get.call_args.kwargs["params"], {"format": "jpg"})
        self.assertIn("Authorization", get.call_args.kwargs["headers"])

    def test_fetch_map_image_returns_none_when_not_an_image(self):
        for resp in (
            image_response(status=401, content_type="application/json", content=b"{}"),
            image_response(status=200, content_type="application/json", content=b"{}"),
        ):
            with mock.patch.object(localrank_mcp.httpx, "get", return_value=resp):
                self.assertIsNone(localrank_mcp.fetch_map_image("scan-1"))

    def test_fetch_map_image_returns_none_on_timeout(self):
        with mock.patch.object(localrank_mcp.httpx, "get", side_effect=httpx.ReadTimeout("slow")):
            self.assertIsNone(localrank_mcp.fetch_map_image("scan-1"))

    def scans(self):
        return {"results": [
            {"uuid": "new", "business": {"name": "Acme Plumbing"}, "avg_rank": 4.0, "keywords": ["plumber"], "public_share_token": "tok"},
            {"uuid": "old", "business": {"name": "Acme Plumbing"}, "avg_rank": 7.0, "keywords": ["plumber"]},
        ]}

    def fake_api_get(self, endpoint, params=None):
        if endpoint == "/api/scans/":
            return self.scans()
        rank = 4.0 if "new" in endpoint else 7.0
        return {"created_at": "2026-09-01", "avg_rank": rank, "public_share_token": "tok",
                "keyword_results": [{"keyword": "plumber", "avg_rank": rank, "best_rank": 1}]}

    def test_client_report_attaches_latest_scan_heat_map(self):
        with mock.patch.object(localrank_mcp, "api_get", side_effect=self.fake_api_get), \
             mock.patch.object(localrank_mcp.httpx, "get", return_value=image_response()) as get:
            result = run(localrank_mcp.call_tool("client_report", {"business_name": "acme"}))
        self.assertEqual([c.type for c in result], ["text", "image"])
        self.assertIn("/api/scans/new/map-grid-image", get.call_args.args[0])
        self.assertIn('"wins"', result[0].text)

    def test_draft_client_email_attaches_image_and_can_opt_out(self):
        with mock.patch.object(localrank_mcp, "api_get", side_effect=self.fake_api_get), \
             mock.patch.object(localrank_mcp.httpx, "get", return_value=image_response()):
            with_image = run(localrank_mcp.call_tool("draft_client_email", {"business_name": "acme"}))
            without = run(localrank_mcp.call_tool("draft_client_email", {"business_name": "acme", "include_map_image": False}))
        self.assertEqual([c.type for c in with_image], ["text", "image"])
        self.assertEqual([c.type for c in without], ["text"])

    def test_report_still_returns_text_when_image_unavailable(self):
        with mock.patch.object(localrank_mcp, "api_get", side_effect=self.fake_api_get), \
             mock.patch.object(localrank_mcp.httpx, "get", side_effect=httpx.ConnectError("down")):
            result = run(localrank_mcp.call_tool("client_report", {"business_name": "acme"}))
        self.assertEqual([c.type for c in result], ["text"])


class CliTaggingTests(unittest.TestCase):
    def test_cli_sets_cli_transport_and_command_name(self):
        from localrank_mcp import cli
        seen = {}

        def fake_cmd(_args):
            seen["ua"] = localrank_mcp.client_user_agent()

        parser = mock.Mock()
        parser.parse_args.return_value = mock.Mock(func=mock.Mock(side_effect=fake_cmd, __name__="cmd_businesses_list"))
        with mock.patch.object(cli, "build_parser", return_value=parser):
            cli.main()
        self.assertIn("transport=cli; tool=cli:businesses_list", seen["ua"])


if __name__ == "__main__":
    unittest.main()
