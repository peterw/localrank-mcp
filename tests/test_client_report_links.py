import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("LOCALRANK_API_KEY", "lr_test")

import localrank_mcp  # noqa: E402
from localrank_mcp.client_report_links import BusinessNotFound, client_report_link  # noqa: E402

localrank_mcp.API_KEY = localrank_mcp.API_KEY or "lr_test"

UUID = "329c907f-8973-408a-9d36-94bf81704fc6"
SECOND_UUID = "0b7d2b1e-5d0e-4c1e-9f55-2f1f3c1a7c11"
TOKEN = "871fa427-6bdb-46e0-9a66-3e1a594fc56a"
LINK = f"https://app.localrank.so/share/report/{TOKEN}"
HARBOR = {"uuid": UUID, "name": "Harbor Dental", "cid": "123", "url": "https://maps.google.com/?cid=123",
          "address": "12 Harbor Way"}


def grouped(*records):
    """/api/businesses/ groups records by place: a list of representative + scans."""
    return [{"representative_business": record, "scans": [{"business": record}]} for record in records]


class ClientReportLinkTests(unittest.TestCase):
    def setUp(self):
        self.get = mock.Mock(return_value=grouped(HARBOR))
        self.post = mock.Mock(return_value={"token": TOKEN, "live": True, "business_name": "Harbor Dental"})
        self.delete = mock.Mock()

    def call(self, business, disable=False):
        return client_report_link(business, disable=disable, api_get=self.get, api_post=self.post,
                                  api_delete=self.delete, app_base="https://app.localrank.so/")

    def test_same_permanent_url_on_every_call(self):
        first, second = self.call(UUID), self.call(UUID)
        self.assertEqual(first["url"], LINK)
        self.assertEqual(second["url"], LINK)
        self.assertTrue(first["live"])
        self.get.assert_not_called()  # a UUID needs no lookup
        self.post.assert_called_with(f"/business/api/businesses/{UUID}/client_report/", {})

    def test_exact_name_is_case_and_entity_insensitive(self):
        self.get.return_value = grouped({**HARBOR, "name": "Harbor Dental &amp; Implants"})
        self.assertEqual(self.call("harbor dental & implants")["business_id"], UUID)

    def test_duplicate_records_for_one_place_resolve_to_one_business(self):
        self.get.return_value = grouped(HARBOR, {**HARBOR, "uuid": SECOND_UUID, "cid": None,
                                                 "url": "https://maps.google.com/maps?cid=123"})
        self.assertEqual(self.call("Harbor Dental")["url"], LINK)

    def test_ambiguous_or_partial_name_never_writes(self):
        two_locations = grouped(HARBOR, {**HARBOR, "uuid": SECOND_UUID, "cid": "456", "url": "https://x?cid=456"})
        for records, phrase in [(two_locations, "2 different locations"), (grouped(HARBOR), "Similar")]:
            self.get.return_value = records
            name = "Harbor Dental" if records is two_locations else "Harbor"
            with self.assertRaisesRegex(BusinessNotFound, phrase):
                self.call(name)
        with self.assertRaises(BusinessNotFound):
            self.call("  ")
        self.post.assert_not_called()
        self.delete.assert_not_called()

    def test_disable_turns_off_without_creating(self):
        result = self.call(UUID, disable=True)
        self.assertFalse(result["live"])
        self.assertIsNone(result["url"])
        self.delete.assert_called_once_with(f"/business/api/businesses/{UUID}/client_report/")
        self.post.assert_not_called()


class ClientReportToolTests(unittest.TestCase):
    def test_tools_are_listed_with_one_business_argument(self):
        tools = {tool.name: tool for tool in asyncio.run(localrank_mcp.list_tools())}
        for name in ("get_client_report_link", "disable_client_report_link"):
            self.assertEqual(tools[name].inputSchema["required"], ["business"])

    def test_tool_returns_the_url_built_from_the_backend_token(self):
        with mock.patch.object(localrank_mcp, "api_post",
                               return_value={"token": TOKEN, "live": True, "business_name": "Harbor Dental"}) as post:
            result = asyncio.run(localrank_mcp.call_tool("get_client_report_link", {"business": UUID}))
        payload = json.loads(result[0].text)
        self.assertEqual(payload["url"], f"{localrank_mcp.APP_BASE.rstrip('/')}/share/report/{TOKEN}")
        self.assertTrue(payload["live"])
        post.assert_called_once_with(f"/business/api/businesses/{UUID}/client_report/", {})

    def test_requests_carry_the_tool_name_for_usage_tracking(self):
        async def call():
            with mock.patch.object(localrank_mcp.httpx, "delete") as delete:
                delete.return_value = httpx.Response(204, request=httpx.Request("DELETE", "https://api"))
                await localrank_mcp.call_tool("disable_client_report_link", {"business": UUID})
            return delete.call_args.kwargs["headers"]
        headers = asyncio.run(call())
        self.assertIn("tool=disable_client_report_link", headers["User-Agent"])
        self.assertTrue(headers["Authorization"].startswith("Api-Key "))

    def test_list_businesses_returns_usable_uuids_from_grouped_api(self):
        with mock.patch.object(localrank_mcp, "api_get", return_value=grouped(HARBOR)):
            result = asyncio.run(localrank_mcp.call_tool("list_businesses", {}))
        self.assertEqual(json.loads(result[0].text)["businesses"], [
            {"uuid": UUID, "name": "Harbor Dental", "place_id": None}])


if __name__ == "__main__":
    unittest.main()
