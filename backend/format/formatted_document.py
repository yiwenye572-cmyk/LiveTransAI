from dataclasses import dataclass, field


@dataclass
class FormatSlot:
    sentence_id: str
    version: int
    normalized: str
    paragraph_id: str


@dataclass
class FormattedDocument:
    slots: list[FormatSlot] = field(default_factory=list)

    def has_sentence(self, sentence_id: str) -> bool:
        return any(slot.sentence_id == sentence_id for slot in self.slots)

    def get_slot(self, sentence_id: str) -> FormatSlot | None:
        for slot in self.slots:
            if slot.sentence_id == sentence_id:
                return slot
        return None

    def paragraph_index(self, paragraph_id: str) -> int:
        seen: list[str] = []
        for slot in self.slots:
            if slot.paragraph_id not in seen:
                seen.append(slot.paragraph_id)
        return seen.index(paragraph_id) if paragraph_id in seen else len(seen)

    def sentences_in_paragraph(self, paragraph_id: str) -> int:
        return sum(1 for slot in self.slots if slot.paragraph_id == paragraph_id)

    def build_snapshot(self) -> list[str]:
        paragraphs: list[str] = []
        current_id: str | None = None
        buffer: list[str] = []
        for slot in self.slots:
            if slot.paragraph_id != current_id:
                if buffer:
                    paragraphs.append("".join(buffer))
                buffer = [slot.normalized]
                current_id = slot.paragraph_id
            else:
                buffer.append(slot.normalized)
        if buffer:
            paragraphs.append("".join(buffer))
        return paragraphs
