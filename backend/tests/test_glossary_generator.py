import json
import unittest

from backend.glossary.generator import GlossaryError, MAX_TERMS, parse_glossary_response
from backend.glossary.glossary_bundle import GlossaryBundle
from backend.state.session_state import SessionState


class ParseGlossaryResponseTests(unittest.TestCase):
    def test_parses_plain_json(self) -> None:
        raw = """
        {
          "tone_hint": "工程向，术语统一",
          "glossary_list": {
            "federated learning": "联邦学习",
            "edge computing": "边缘计算"
          },
          "hot_words_list": ["federated learning"]
        }
        """
        bundle = parse_glossary_response(
            raw,
            scenario="AI 技术分享",
            instruction="工程向分享",
        )
        self.assertEqual(bundle.scenario, "AI 技术分享")
        self.assertEqual(bundle.instruction, "工程向分享")
        self.assertEqual(bundle.tone_hint, "工程向，术语统一")
        self.assertEqual(
            bundle.glossary_list,
            {
                "federated learning": "联邦学习",
                "edge computing": "边缘计算",
            },
        )
        self.assertEqual(bundle.hot_words_list, ["federated learning"])

    def test_strips_markdown_fence(self) -> None:
        raw = """```json
        {"tone_hint": "", "glossary_list": {"GPU": "图形处理器"}, "hot_words_list": []}
        ```"""
        bundle = parse_glossary_response(
            raw,
            scenario="硬件分享",
            instruction="保持简洁",
        )
        self.assertEqual(bundle.glossary_list, {"GPU": "图形处理器"})
        self.assertEqual(bundle.tone_hint, "保持简洁")
        self.assertEqual(bundle.hot_words_list, ["GPU"])

    def test_truncates_to_max_terms(self) -> None:
        glossary = {f"term-{index}": f"译-{index}" for index in range(40)}
        raw = json.dumps({"glossary_list": glossary, "hot_words_list": []})
        bundle = parse_glossary_response(
            raw,
            scenario="长列表",
            instruction="测试截断",
        )
        self.assertEqual(len(bundle.glossary_list), MAX_TERMS)

    def test_raises_when_glossary_empty(self) -> None:
        with self.assertRaises(GlossaryError):
            parse_glossary_response(
                '{"glossary_list": {}, "hot_words_list": []}',
                scenario="空",
                instruction="空",
            )


    def test_filters_invalid_hot_words_from_llm_response(self) -> None:
        raw = """
        {
          "glossary_list": {"GPU": "图形处理器"},
          "hot_words_list": ["GPU", "not-in-glossary"]
        }
        """
        bundle = parse_glossary_response(
            raw,
            scenario="硬件",
            instruction="简洁",
        )
        self.assertEqual(bundle.hot_words_list, ["GPU"])


class GlossaryBundleTests(unittest.TestCase):
    def test_from_client_payload_uses_term_map(self) -> None:
        payload = {
            "scenario": "产品发布会",
            "instruction": "正式语气",
            "tone_hint": "正式",
            "term_map": {"launch": "发布"},
            "hot_words_list": ["launch"],
        }
        bundle = GlossaryBundle.from_client_payload(payload)
        assert bundle is not None
        self.assertEqual(bundle.glossary_list, {"launch": "发布"})
        api = bundle.to_api_dict()
        self.assertEqual(api["term_map"], {"launch": "发布"})
        self.assertEqual(api["term_count"], 1)

    def test_from_client_payload_returns_none_for_empty(self) -> None:
        self.assertIsNone(GlossaryBundle.from_client_payload(None))
        self.assertIsNone(GlossaryBundle.from_client_payload({}))

    def test_normalize_skips_blank_entries(self) -> None:
        glossary = GlossaryBundle._normalize_glossary(
            {"valid": "有效", "": "无效", "blank-value": "  "}
        )
        self.assertEqual(glossary, {"valid": "有效"})


class StaticGlossaryMergeTests(unittest.TestCase):
    def test_static_glossary_not_merged_into_summary_term_map(self) -> None:
        state = SessionState()
        state.static_glossary = {"federated learning": "联邦学习"}
        state.running_summary.apply_payload(
            {"term_map": {"edge computing": "边缘计算"}, "topic": "AI", "bullet_points": []},
            sentence_count=3,
        )
        self.assertNotIn("federated learning", state.running_summary.term_map)
        self.assertEqual(state.running_summary.term_map["edge computing"], "边缘计算")


if __name__ == "__main__":
    unittest.main()
