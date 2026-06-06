import unittest

from backend.glossary.glossary_bundle import GlossaryBundle
from backend.glossary.hot_words import MAX_HOT_WORDS, derive_hot_words
from backend.translator.ast_corpus import AstCorpus


class DeriveHotWordsTests(unittest.TestCase):
    def test_keeps_llm_hot_words_in_glossary(self) -> None:
        glossary = {
            "federated learning": "联邦学习",
            "edge computing": "边缘计算",
        }
        result = derive_hot_words(
            glossary,
            ["federated learning", "edge computing"],
        )
        self.assertEqual(result, ["federated learning", "edge computing"])

    def test_filters_hot_words_not_in_glossary(self) -> None:
        glossary = {"GPU": "图形处理器"}
        result = derive_hot_words(glossary, ["GPU", "hallucinated term"])
        self.assertEqual(result, ["GPU"])

    def test_heuristic_fallback_when_llm_empty(self) -> None:
        glossary = {
            "AI": "人工智能",
            "GPU": "图形处理器",
            "federated learning": "联邦学习",
        }
        result = derive_hot_words(glossary, [])
        self.assertIn("federated learning", result)
        self.assertIn("GPU", result)
        self.assertNotIn("AI", result)

    def test_respects_max_count(self) -> None:
        glossary = {f"term-{index}": f"译-{index}" for index in range(30)}
        result = derive_hot_words(glossary, [], max_count=MAX_HOT_WORDS)
        self.assertEqual(len(result), MAX_HOT_WORDS)

    def test_case_insensitive_match_for_llm_hot_words(self) -> None:
        glossary = {"GPU": "图形处理器"}
        result = derive_hot_words(glossary, ["gpu"])
        self.assertEqual(result, ["GPU"])


class GlossaryBundleHotWordsTests(unittest.TestCase):
    def test_from_client_payload_derives_hot_words(self) -> None:
        payload = {
            "scenario": "网课",
            "instruction": "深度学习",
            "term_map": {
                "deep learning": "深度学习",
                "GPU": "图形处理器",
            },
            "hot_words_list": ["deep learning", "unknown"],
        }
        bundle = GlossaryBundle.from_client_payload(payload)
        assert bundle is not None
        self.assertEqual(bundle.hot_words_list, ["deep learning"])


class AstCorpusTests(unittest.TestCase):
    def test_is_empty(self) -> None:
        self.assertTrue(AstCorpus().is_empty)
        self.assertFalse(AstCorpus(hot_words=["GPU"]).is_empty)
        self.assertFalse(AstCorpus(glossary={"GPU": "图形处理器"}).is_empty)


if __name__ == "__main__":
    unittest.main()
