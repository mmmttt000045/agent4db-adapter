"""Guard the SQL-only ablation's information boundary (run with the RelBench dependencies)."""
import unittest
from unittest.mock import patch

import harness


class SqlOnlyTests(unittest.TestCase):
    def setUp(self):
        self.run = harness.Run.__new__(harness.Run)
        self.run.url = "unused"
        self.run.sql_programs = {}
        self.run.refs = {("a", 1): {"val": 0.6}}
        self.run.tasks = {"a": {"cutoffs": [{"test_timestamp": "2020-01-01"}]}}
        self.run.arm = harness.ARMS["sql-only"]
        self.run.asm = None
        self.rec = dict(best_val=0.8, higher_is_better=True, metric="roc_auc", stop="submitted",
                        final_sql="select * from {seeds};", audit={"result": "clean"})

    def test_only_earlier_own_task_sql_is_retrieved(self):
        self.assertTrue(self.run.save_sql_program("a", 1, self.rec)["saved"])
        with patch.object(harness, "read_sql") as query:
            self.assertIsNone(self.run.find_sql_program("b", 2)["program"])
            self.assertIsNone(self.run.find_sql_program("a", 1)["program"])
            query.assert_not_called()
            result = self.run.find_sql_program("a", 2)
            self.assertEqual(result["program_sql"], self.rec["final_sql"])
            self.assertIn("task.a_val limit 50", query.call_args.args[1])
            self.assertEqual(query.call_args.kwargs["timeout_s"], 300)
            self.assertNotIn("sql", result)  # no compiled definitions

    def test_invalid_publications_leave_previous_program_intact(self):
        self.run.save_sql_program("a", 1, self.rec)
        for change in [{"audit": {"result": "leak"}}, {"audit": {"result": "error"}},
                       {"best_val": 0.6}, {"final_sql": None}, {"stop": "llm_error"}]:
            with self.subTest(change=change):
                self.assertFalse(self.run.save_sql_program("a", 1, {**self.rec, **change})["saved"])
                self.assertEqual(self.run.sql_programs["a"]["sql"], self.rec["final_sql"])

    def test_regression_success_direction(self):
        self.assertTrue(self.run.save_sql_program("a", 1, {**self.rec, "best_val": 0.5,
                                                          "higher_is_better": False})["saved"])

    def test_failed_current_snapshot_check_withholds_sql(self):
        self.run.save_sql_program("a", 1, self.rec)
        with patch.object(harness, "read_sql", side_effect=RuntimeError("missing column")):
            result = self.run.find_sql_program("a", 2)
        self.assertNotIn("program_sql", result)
        self.assertIn("missing column", result["program_sql_unavailable"])

    def test_no_structured_feature_tools_or_extractor(self):
        names = {x["function"]["name"] for x in self.run.tool_specs()}
        self.assertIn("find_program", names)
        self.assertFalse({"find_features", "compose_features"} & names)
        self.assertFalse(self.run.arm.get("extractor"))
        self.assertFalse(self.run.arm.get("feature_memory"))
        self.assertEqual(self.run.arm["middle_mode"], harness.ARMS["mavra"]["middle_mode"])

    def test_happy_model_and_usage_are_checked(self):
        client = harness.Llm({"HAPPY_API_KEY": "test", "HAPPY_MODEL": "test-request-model",
                              "HAPPY_REQUIRE_MODEL": "test-response-model", "HAPPY_REASONING_EFFORT": "low"}, "happy")
        response = {"model": "test-response-model", "choices": [{"message": {"role": "assistant", "content": "ok"},
                                                                  "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
        with patch.object(client, "_post", return_value=(response, 0, 0)) as post:
            result = client.chat([{"role": "user", "content": "test"}])
        self.assertEqual(result["input_tokens"], 12)
        self.assertEqual(post.call_args.args[0]["reasoning_effort"], "low")
        self.assertFalse(client.keep_reasoning)

    def test_gateway_error_is_retried_without_poisoning_history(self):
        client = harness.Llm({"HAPPY_API_KEY": "test", "HAPPY_MODEL": "test-model"}, "happy")
        bad = {"model": "test-model", "choices": [{"finish_reason": "error", "message": {"role": "assistant", "content": None}}],
               "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
        good = {"model": "test-model", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "OK"}}],
                "usage": {"prompt_tokens": 13, "completion_tokens": 2}}
        messages = [{"role": "user", "content": "test"}]
        with patch.object(client, "_post", side_effect=[(bad, 0, 0), (good, 0, 0)]) as post, patch.object(harness.time, "sleep"):
            result = client.chat(messages)
        self.assertEqual(post.call_args_list[0], post.call_args_list[1])
        self.assertEqual(messages, [{"role": "user", "content": "test"}])
        self.assertEqual(result["input_tokens"], 24)
        self.assertEqual(result["output_tokens"], 9)
        self.assertEqual(result["message"]["content"], "OK")
        self.assertEqual(result["retries"], 1)

    def test_empty_gateway_replies_have_a_finite_retry_budget(self):
        client = harness.Llm({"HAPPY_API_KEY": "test", "HAPPY_MODEL": "test-model"}, "happy")
        bad = {"model": "test-model", "choices": [{"finish_reason": "stop", "message": {"role": "assistant"}}]}
        with patch.object(client, "_post", return_value=(bad, 0, 0)) as post, patch.object(harness.time, "sleep"):
            with self.assertRaises(harness.LlmUnavailable):
                client.chat([{"role": "user", "content": "test"}])
        self.assertEqual(post.call_count, 4)


if __name__ == "__main__":
    unittest.main()
