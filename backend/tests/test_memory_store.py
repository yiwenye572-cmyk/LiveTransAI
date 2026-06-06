import unittest

from backend.memory.memory_store import MemoryStore
from backend.state.session_state import SessionState


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryStore()
        self.state = SessionState()
        self.state.displayed_sentences = [
            {
                "id": "d_001",
                "source": "We use federated learning",
                "translation": "我们使用联邦学习",
                "version": 2,
            }
        ]

    def test_append_batch_only_for_corrections(self) -> None:
        window = [{"id": "d_001"}]
        applied = [
            {
                "target_id": "d_001",
                "base_version": 1,
                "new_version": 2,
                "old_translation": "旧译文",
                "new_translation": "我们使用联邦学习",
                "reason": "术语统一",
            }
        ]
        self.store.append_batch(window, applied, self.state)
        self.assertEqual(len(self.state.memory_entries), 1)
        self.assertIn("reason: 术语统一", self.state.memory_entries[0].correction_hints)

    def test_append_batch_skips_empty_corrections(self) -> None:
        window = [{"id": "d_001"}]
        self.store.append_batch(window, [], self.state)
        self.assertEqual(len(self.state.memory_entries), 0)

    def test_recent_prompt_block(self) -> None:
        self.store.append_batch(
            [{"id": "d_001"}],
            [
                {
                    "target_id": "d_001",
                    "old_translation": "旧",
                    "new_translation": "新",
                    "reason": "测试",
                }
            ],
            self.state,
        )
        block = MemoryStore.recent_prompt_block(self.state)
        self.assertIn("【近期纠错记忆】", block)
        self.assertIn("d_001", block)


if __name__ == "__main__":
    unittest.main()
