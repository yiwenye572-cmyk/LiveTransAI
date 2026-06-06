import unittest

from backend.state.session_state import SessionState
from backend.utils.session_metrics import SessionMetrics


class SessionMetricsTests(unittest.TestCase):
    def test_display_latency_percentiles(self) -> None:
        metrics = SessionMetrics()
        for latency in (100.0, 200.0, 300.0, 400.0, 500.0):
            metrics.record_display_latency(
                sentence_id=f"d_{int(latency)}",
                latency_ms=latency,
                merge_count=1,
                wait_ms=latency / 2,
            )

        self.assertAlmostEqual(metrics.latency_p50_sec(), 0.3, places=2)
        self.assertAlmostEqual(metrics.latency_p99_sec(), 0.496, places=2)

    def test_recent_display_latencies_capped(self) -> None:
        metrics = SessionMetrics()
        for index in range(15):
            metrics.record_display_latency(
                sentence_id=f"d_{index:03d}",
                latency_ms=float(index),
                merge_count=1,
                wait_ms=0.0,
            )

        self.assertEqual(len(metrics.recent_display_latencies), 10)
        self.assertEqual(metrics.recent_display_latencies[-1]["id"], "d_014")

    def test_record_llm_call_accumulates_tokens(self) -> None:
        metrics = SessionMetrics()
        metrics.record_llm_call(
            "correction",
            latency_ms=120.0,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            ok=True,
        )
        metrics.record_llm_call(
            "summary",
            latency_ms=80.0,
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            ok=True,
        )
        metrics.record_llm_call("glossary", latency_ms=0, ok=False)

        self.assertEqual(metrics.correction_llm_calls, 1)
        self.assertEqual(metrics.summary_llm_calls, 1)
        self.assertEqual(metrics.glossary_llm_calls, 1)
        self.assertEqual(metrics.llm_tokens_prompt, 300)
        self.assertEqual(metrics.llm_tokens_completion, 150)
        self.assertEqual(metrics.llm_tokens_total, 450)
        self.assertEqual(metrics.llm_errors, 1)
        self.assertEqual(metrics.correction_latency_ms_p50(), 120.0)
        self.assertEqual(metrics.summary_latency_ms_p50(), 80.0)

    def test_to_payload_includes_session_counts(self) -> None:
        state = SessionState(
            sentence_count=3,
            correction_count=1,
            merge_count=2,
            ast_fragment_count=5,
            started_at=1000.0,
        )
        metrics = SessionMetrics()
        metrics.record_display_latency(
            sentence_id="d_001",
            latency_ms=500.0,
            merge_count=1,
            wait_ms=400.0,
        )

        payload = metrics.to_payload(state)
        self.assertEqual(payload["sentence_count"], 3)
        self.assertEqual(payload["correction_count"], 1)
        self.assertEqual(payload["latency_p50"], 0.5)
        self.assertIn("session_elapsed_sec", payload)

    def test_merge_from_combines_metrics(self) -> None:
        left = SessionMetrics()
        right = SessionMetrics()
        right.record_llm_call(
            "glossary",
            latency_ms=50.0,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            ok=True,
        )
        left.merge_from(right)
        self.assertEqual(left.glossary_llm_calls, 1)
        self.assertEqual(left.llm_tokens_total, 15)


if __name__ == "__main__":
    unittest.main()
