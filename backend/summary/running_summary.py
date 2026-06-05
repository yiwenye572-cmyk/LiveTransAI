from dataclasses import dataclass, field


@dataclass
class RunningSummary:
    topic: str = ""
    term_map: dict[str, str] = field(default_factory=dict)
    bullet_points: list[str] = field(default_factory=list)
    last_summarized_at: int = 0

    def to_prompt_block(self) -> str:
        if not self.topic and not self.term_map and not self.bullet_points:
            return "（暂无摘要）"

        lines: list[str] = []
        if self.topic:
            lines.append(f"主题: {self.topic}")
        if self.term_map:
            terms = "；".join(f"{en} → {zh}" for en, zh in self.term_map.items())
            lines.append(f"术语: {terms}")
        if self.bullet_points:
            lines.append("要点:")
            lines.extend(f"- {point}" for point in self.bullet_points)
        return "\n".join(lines)

    def apply_payload(self, payload: dict, *, sentence_count: int) -> None:
        self.topic = str(payload.get("topic", self.topic)).strip()
        self.bullet_points = [
            str(item).strip() for item in payload.get("bullet_points", []) if str(item).strip()
        ][:8]

        term_map = payload.get("term_map", {})
        if isinstance(term_map, dict):
            self.term_map = {
                str(key).strip(): str(value).strip()
                for key, value in term_map.items()
                if str(key).strip() and str(value).strip()
            }

        self.last_summarized_at = sentence_count

    def to_ws_payload(self, *, sentence_count: int) -> dict:
        return {
            "type": "summary",
            "topic": self.topic,
            "term_map": dict(self.term_map),
            "bullet_points": list(self.bullet_points),
            "updated_at_sentence": sentence_count,
        }
