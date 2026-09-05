"""Metrics and behavior for disabled or failed AI analysis."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIUsageMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    mode: str
    eligible_cases: int = 0
    skipped_clean_cases: int = 0
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: int = 0  # Micro-dollars ($0.000001)
    total_latency_ms: int = 0
    average_latency_ms: float = 0.0
    cases_improved: int = 0
    rejected_outputs: int = 0
    timeouts: int = 0
    provider_errors: int = 0
    deterministic_only: bool = True
    warnings: list[str] = Field(default_factory=list)

    def finalize(self) -> AIUsageMetrics:
        self.average_latency_ms = (
            round(self.total_latency_ms / self.calls, 2) if self.calls else 0.0
        )
        self.deterministic_only = self.cases_improved == 0
        return self


def ai_disabled_metrics(*, total_cases: int, eligible_cases: int) -> AIUsageMetrics:
    return AIUsageMetrics(
        enabled=False,
        mode="DETERMINISTIC_ONLY",
        eligible_cases=eligible_cases,
        skipped_clean_cases=max(total_cases - eligible_cases, 0),
        deterministic_only=True,
        warnings=["AI analysis unavailable; deterministic results were preserved."],
    )
