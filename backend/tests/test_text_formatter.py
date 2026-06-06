import unittest

from backend.format.text_formatter import TextFormatter
from backend.state.session_state import SessionState


def _sentence(
    sid: str,
    translation: str,
    *,
    version: int = 1,
    start_time: int = 0,
    end_time: int = 1000,
) -> dict:
    return {
        "id": sid,
        "source": "hello world",
        "translation": translation,
        "version": version,
        "start_time": start_time,
        "end_time": end_time,
    }


class TextFormatterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.formatter = TextFormatter()
        self.state = SessionState()

    def test_normalize_punctuation_and_term_map(self) -> None:
        self.state.running_summary.term_map = {"federated learning": "联邦学习"}
        result = self.formatter.normalize_text(
            "我们使用 federated learning，",
            self.state.running_summary.term_map,
        )
        self.assertTrue(result.endswith("。"))
        self.assertNotIn("，。", result)
        self.assertIn("联邦学习", result)

    def test_normalize_fixes_comma_period_artifacts(self) -> None:
        samples = [
            ("在第五门课程中，", "在第五门课程中。"),
            ("你将学习序列模型，", "你将学习序列模型。"),
            ("简称 RNN）、", "简称 RNN）。"),
            ("以及其它问题，。", "以及其它问题。"),
        ]
        for raw, expected in samples:
            with self.subTest(raw=raw):
                self.assertEqual(
                    self.formatter.normalize_text(raw, {}),
                    expected,
                )

    def test_flush_window_appends_once(self) -> None:
        self.state.displayed_sentences.append(_sentence("d_001", "第一句"))
        self.state.displayed_sentences.append(_sentence("d_002", "第二句", start_time=1200, end_time=2200))

        deltas = self.formatter.flush_window(self.state.displayed_sentences, self.state)
        self.assertEqual(len(deltas), 2)
        self.assertEqual(deltas[0]["sentence_id"], "d_001")
        self.assertTrue(self.state.formatted_doc.has_sentence("d_001"))

        again = self.formatter.flush_window(self.state.displayed_sentences, self.state)
        self.assertEqual(len(again), 0)

    def test_build_patches_after_correction(self) -> None:
        self.state.displayed_sentences.append(_sentence("d_001", "旧译文"))
        self.formatter.flush_window(self.state.displayed_sentences, self.state)
        self.state.displayed_sentences[0]["translation"] = "新译文"
        self.state.displayed_sentences[0]["version"] = 2

        patches = self.formatter.build_patches(
            [
                {
                    "target_id": "d_001",
                    "base_version": 1,
                    "new_version": 2,
                    "old_translation": "旧译文",
                    "new_translation": "新译文",
                    "reason": "测试",
                }
            ],
            self.state,
        )
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]["new_text"], "新译文。")

    def test_flush_remaining(self) -> None:
        self.state.displayed_sentences.append(_sentence("d_001", "遗留句"))
        deltas = self.formatter.flush_remaining(self.state)
        self.assertEqual(len(deltas), 1)


if __name__ == "__main__":
    unittest.main()
