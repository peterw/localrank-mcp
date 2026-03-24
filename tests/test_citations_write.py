import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "localrank_mcp" / "citations_write.py"
SPEC = importlib.util.spec_from_file_location("localrank_mcp_citations_write", MODULE_PATH)
citations_write = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(citations_write)


class EnsureCitationBusinessTests(unittest.TestCase):
    def test_blocks_ambiguous_exact_matches(self):
        api_get = Mock(
            return_value={
                "businesses": [
                    {
                        "uuid": "biz-1",
                        "name": "Acme Plumbing",
                        "address": "123 Main St",
                        "phone": "(555) 111-2222",
                        "website": "https://acme.com",
                        "citations": {"total": 0},
                    },
                    {
                        "uuid": "biz-2",
                        "name": "Acme Plumbing",
                        "address": "123 Main St",
                        "phone": "5551112222",
                        "website": "https://www.acme.com",
                        "citations": {"total": 0},
                    },
                ]
            }
        )
        api_post = Mock()

        result = citations_write.ensure_citation_business(
            {
                "business_name": "Acme Plumbing",
                "address": "123 Main St",
                "phone": "5551112222",
                "website": "acme.com",
            },
            api_get=api_get,
            api_post=api_post,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["action"], "blocked_ambiguous_match")
        self.assertEqual(result["clear_match_count"], 2)
        api_post.assert_not_called()

    def test_reuses_single_exact_match_without_creating_duplicate(self):
        api_get = Mock(
            return_value={
                "businesses": [
                    {
                        "uuid": "biz-1",
                        "name": "Acme Plumbing",
                        "address": "123 Main St",
                        "phone": "(555) 111-2222",
                        "website": "https://acme.com",
                        "citations": {"total": 0},
                    }
                ]
            }
        )
        api_post = Mock()

        result = citations_write.ensure_citation_business(
            {
                "business_name": "Acme Plumbing",
                "address": "123 Main St",
                "phone": "5551112222",
                "website": "https://www.acme.com",
            },
            api_get=api_get,
            api_post=api_post,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "reused_existing_business")
        self.assertFalse(result["created_business"])
        self.assertEqual(result["business"]["uuid"], "biz-1")
        api_post.assert_not_called()

    def test_creates_business_when_search_returns_zero_results(self):
        api_get = Mock(return_value={"businesses": []})
        api_post = Mock(
            return_value={
                "uuid": "biz-new",
                "business_details": {
                    "name": "Fresh HVAC",
                    "address": "99 Market St",
                    "phone": "5559998888",
                    "phone_number": "5559998888",
                    "website": "https://freshhvac.com",
                },
            }
        )

        result = citations_write.ensure_citation_business(
            {
                "business_name": "Fresh HVAC",
                "address": "99 Market St",
                "phone": "5559998888",
                "website": "https://freshhvac.com",
            },
            api_get=api_get,
            api_post=api_post,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "created_business")
        self.assertTrue(result["created_business"])
        self.assertEqual(result["business"]["uuid"], "biz-new")
        self.assertEqual(api_post.call_count, 1)
        self.assertEqual(api_post.call_args.args[0], "/citations/businesses/")

    def test_passes_through_requested_citations_without_mcp_cap(self):
        api_get = Mock(return_value={"businesses": []})
        api_post = Mock(
            side_effect=[
                {
                    "uuid": "biz-new",
                    "business_details": {
                        "name": "Fresh HVAC",
                        "address": "99 Market St",
                        "phone": "5559998888",
                        "phone_number": "5559998888",
                        "website": "https://freshhvac.com",
                    },
                },
                {"status": "success", "message": "Buildout started", "citations": []},
            ]
        )

        result = citations_write.ensure_citation_business(
            {
                "business_name": "Fresh HVAC",
                "address": "99 Market St",
                "phone": "5559998888",
                "website": "https://freshhvac.com",
                "start_buildout": True,
                "requested_citations": 10,
                "location_data": {"city": "Austin"},
            },
            api_get=api_get,
            api_post=api_post,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["action"], "created_business_and_started_buildout")
        self.assertTrue(result["buildout"]["started"])
        self.assertEqual(result["buildout"]["max_citations_used"], 10)
        buildout_payload = api_post.call_args_list[1].args[1]
        self.assertEqual(buildout_payload["max_citations"], 10)
        self.assertEqual(buildout_payload["location_data"]["address"], "99 Market St")
        self.assertEqual(buildout_payload["location_data"]["phone"], "5559998888")
        self.assertEqual(buildout_payload["location_data"]["website"], "https://freshhvac.com")
        self.assertEqual(buildout_payload["location_data"]["city"], "Austin")

    def test_blocks_buildout_for_existing_business_with_citations(self):
        api_get = Mock(
            return_value={
                "businesses": [
                    {
                        "uuid": "biz-1",
                        "name": "Acme Plumbing",
                        "address": "123 Main St",
                        "phone": "(555) 111-2222",
                        "website": "https://acme.com",
                        "citations": {"total": 7},
                    }
                ]
            }
        )
        api_post = Mock()

        result = citations_write.ensure_citation_business(
            {
                "business_name": "Acme Plumbing",
                "address": "123 Main St",
                "phone": "5551112222",
                "website": "https://acme.com",
                "start_buildout": True,
                "requested_citations": 2,
            },
            api_get=api_get,
            api_post=api_post,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["action"], "blocked_existing_business_has_citations")
        api_post.assert_not_called()


class EnsureCitationBusinessBatchTests(unittest.TestCase):
    def test_rejects_batches_above_max_items(self):
        arguments = {
            "items": [
                {
                    "business_name": f"Biz {index}",
                    "address": f"{index} Main St",
                    "phone": "5551112222",
                    "website": f"https://biz{index}.com",
                }
                for index in range(citations_write.MAX_BATCH_ITEMS + 1)
            ]
        }

        with self.assertRaisesRegex(ValueError, "items may contain at most"):
            citations_write.ensure_citation_business_batch(
                arguments,
                api_get=Mock(),
                api_post=Mock(),
            )

    def test_processes_each_item_once_with_defaults(self):
        ensure_mock = Mock(
            side_effect=[
                {"status": "success", "action": "created_business", "buildout": {"started": True, "created_citations": 2}},
                {"status": "blocked", "action": "blocked_near_match_requires_review", "buildout": {"started": False, "created_citations": 0}},
            ]
        )

        arguments = {
            "start_buildout": True,
            "requested_citations": 2,
            "items": [
                {
                    "business_name": "Fresh HVAC - Downtown",
                    "address": "99 Market St",
                    "phone": "5559998888",
                    "website": "https://freshhvac.com",
                },
                {
                    "business_name": "Fresh HVAC - North",
                    "address": "101 Oak St",
                    "phone": "5559997777",
                    "website": "https://freshhvac.com",
                },
            ],
        }

        result = citations_write.ensure_citation_business_batch(
            arguments,
            api_get=Mock(),
            api_post=Mock(),
            ensure_item=ensure_mock,
        )

        self.assertEqual(ensure_mock.call_count, 2)
        first_call_args = ensure_mock.call_args_list[0].kwargs["arguments"]
        second_call_args = ensure_mock.call_args_list[1].kwargs["arguments"]
        self.assertTrue(first_call_args["start_buildout"])
        self.assertEqual(first_call_args["requested_citations"], 2)
        self.assertTrue(second_call_args["start_buildout"])
        self.assertEqual(second_call_args["requested_citations"], 2)

        self.assertEqual(result["summary"]["total_items"], 2)
        self.assertEqual(result["summary"]["success_count"], 1)
        self.assertEqual(result["summary"]["blocked_count"], 1)
        self.assertEqual(result["summary"]["error_count"], 0)
        self.assertEqual(result["summary"]["buildout_started_count"], 1)
        self.assertEqual(result["summary"]["created_citations_total"], 2)

    def test_captures_item_validation_errors_without_stopping_batch(self):
        ensure_mock = Mock(
            side_effect=[
                ValueError("address is required"),
                {"status": "success", "action": "created_business", "buildout": {"started": False, "created_citations": 0}},
            ]
        )

        result = citations_write.ensure_citation_business_batch(
            {
                "items": [
                    {
                        "business_name": "Bad Row",
                        "address": "",
                        "phone": "5551112222",
                        "website": "https://bad.example",
                    },
                    {
                        "business_name": "Good Row",
                        "address": "10 Pine St",
                        "phone": "5553334444",
                        "website": "https://good.example",
                    },
                ]
            },
            api_get=Mock(),
            api_post=Mock(),
            ensure_item=ensure_mock,
        )

        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["summary"]["error_count"], 1)
        self.assertEqual(result["summary"]["success_count"], 1)
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertEqual(result["results"][0]["action"], "invalid_item")
        self.assertIn("address is required", result["results"][0]["message"])
        self.assertEqual(result["results"][1]["status"], "success")


if __name__ == "__main__":
    unittest.main()
