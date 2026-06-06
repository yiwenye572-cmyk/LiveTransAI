from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from backend.state.session_state import SessionState

LLMKind = Literal["correction", "summary", "glossary"]

DISPLAY_LATENCY_SAMPLE_LIMIT = 100
RECENT_DISPLAY_LATENCY_LIMIT = 10
LLM_LATENCY_SAMPLE_LIMIT = 100


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    ordered = sorted(values)
    rank = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _p50_ms(samples: deque[float]) -> float:
    return _percentile(list(samples), 50)


@dataclass
class SessionMetrics:
    display_latency_samples_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=DISPLAY_LATENCY_SAMPLE_LIMIT)
    )
    recent_display_latencies: deque[dict] = field(
        default_factory=lambda: deque(maxlen=RECENT_DISPLAY_LATENCY_LIMIT)
    )

    correction_llm_calls: int = 0
    summary_llm_calls: int = 0
    glossary_llm_calls: int = 0
    llm_tokens_prompt: int = 0
    llm_tokens_completion: int = 0
    llm_tokens_total: int = 0
    llm_errors: int = 0

    correction_latency_samples_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=LLM_LATENCY_SAMPLE_LIMIT)
    )
    summary_latency_samples_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=LLM_LATENCY_SAMPLE_LIMIT)
    )

    def merge_from(self, other: SessionMetrics) -> None:
        self.display_latency_samples_ms.extend(other.display_latency_samples_ms)
        self.recent_display_latencies.extend(other.recent_display_latencies)
        self.correction_llm_calls += other.correction_llm_calls
        self.summary_llm_calls += other.summary_llm_calls
        self.glossary_llm_calls += other.glossary_llm_calls
        self.llm_tokens_prompt += other.llm_tokens_prompt
        self.llm_tokens_completion += other.llm_tokens_completion
        self.llm_tokens_total += other.llm_tokens_total
        self.llm_errors += other.llm_errors
        self.correction_latency_samples_ms.extend(other.correction_latency_samples_ms)
        self.summary_latency_samples_ms.extend(other.summary_latency_samples_ms)

    def record_display_latency(
        self,
        *,
        sentence_id: str,
        latency_ms: float,
        merge_count: int,
        wait_ms: float,
    ) -> None:
        sample = max(0.0, float(latency_ms))
        self.display_latency_samples_ms.append(sample)
        self.recent_display_latencies.append(
            {
                "id": sentence_id,
                "latency_ms": round(sample, 1),
                "merge_count": merge_count,
                "wait_ms": round(max(0.0, float(wait_ms)), 1),
            }
        )

    def record_llm_call(
        self,
        kind: LLMKind,
        *,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        ok: bool = True,
    ) -> None:
        if kind == "correction":
            self.correction_llm_calls += 1
            self.correction_latency_samples_ms.append(max(0.0, float(latency_ms)))
        elif kind == "summary":
            self.summary_llm_calls += 1
            self.summary_latency_samples_ms.append(max(0.0, float(latency_ms)))
        elif kind == "glossary":
            self.glossary_llm_calls += 1

        if ok:
            self.llm_tokens_prompt += max(0, int(prompt_tokens))
            self.llm_tokens_completion += max(0, int(completion_tokens))
            if total_tokens > 0:
                self.llm_tokens_total += int(total_tokens)
            else:
                self.llm_tokens_total += max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
        else:
            self.llm_errors += 1

    def latency_p50_sec(self) -> float:
        return _percentile(list(self.display_latency_samples_ms), 50) / 1000.0

    def latency_p99_sec(self) -> float:
        return _percentile(list(self.display_latency_samples_ms), 99) / 1000.0

    def correction_latency_ms_p50(self) -> float:
        return round(_p50_ms(self.correction_latency_samples_ms), 1)

    def summary_latency_ms_p50(self) -> float:
        return round(_p50_ms(self.summary_latency_samples_ms), 1)

    def session_elapsed_sec(self, state: SessionState) -> float:
        if state.started_at <= 0:
            return 0.0
        end = state.stopped_at if state.stopped_at > 0 else time.time()
        return max(0.0, end - state.started_at)

    def to_payload(self, state: SessionState) -> dict:
        return {
            "sentence_count": state.sentence_count,
            "correction_count": state.correction_count,
            "merge_count": state.merge_count,
            "ast_fragment_count": state.ast_fragment_count,
            "memory_count": len(state.memory_entries),
            "latency_p50": round(self.latency_p50_sec(), 2),
            "latency_p99": round(self.latency_p99_sec(), 2),
            "session_elapsed_sec": round(self.session_elapsed_sec(state), 1),
            "correction_llm_calls": self.correction_llm_calls,
            "summary_llm_calls": self.summary_llm_calls,
            "glossary_llm_calls": self.glossary_llm_calls,
            "llm_tokens_prompt": self.llm_tokens_prompt,
            "llm_tokens_completion": self.llm_tokens_completion,
            "llm_tokens_total": self.llm_tokens_total,
            "correction_latency_ms_p50": self.correction_latency_ms_p50(),
            "summary_latency_ms_p50": self.summary_latency_ms_p50(),
            "llm_errors": self.llm_errors,
        }

    def to_detail_payload(self, state: SessionState) -> dict:
        payload = self.to_payload(state)
        payload.update(
            {
                "source_language": state.source_language,
                "target_language": state.target_language,
                "recent_display_latencies": list(self.recent_display_latencies),
            }
        )
        return payload
