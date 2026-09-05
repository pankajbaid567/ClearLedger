"""Grounded Settlement Q&A Service.

Answers questions strictly from computed reconciliation facts and cash invariants,
following the safety rules defined in prompts/grounded_qa.v1.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CashPositionSnapshot, ReconciliationCase, ReconciliationRun
from db.repositories import CaseRepository, RunRepository
from packages.domain.money import format_paise
from services.ai_analyst.schemas import AIClientConfig

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_QA_PROMPT = _ROOT / "prompts" / "grounded_qa.v1.md"
_CASE_ID_PATTERN = re.compile(r"\bCASE_[A-Za-z0-9_]+\b")
_MONEY_PATTERN = re.compile(r"-?₹[\d,]+\.\d{2}")


class QuestionResult(BaseModel):
    run_id: str
    question: str
    answer: str
    cited_case_ids: list[str] = Field(default_factory=list)
    provider: str
    model: str
    grounded: bool = True


@dataclass
class GroundedQAService:
    session: AsyncSession
    config: AIClientConfig
    prompt_path: Path = field(default_factory=lambda: _DEFAULT_QA_PROMPT)

    async def answer_question(
        self,
        run_id: uuid.UUID,
        question: str,
    ) -> QuestionResult:
        """Answer a question about a reconciliation run using computed facts."""
        runs_repo = RunRepository(self.session)
        cases_repo = CaseRepository(self.session)

        run = await runs_repo.get(run_id)
        if run is None:
            return QuestionResult(
                run_id=str(run_id),
                question=question,
                answer=f"Reconciliation run {run_id} was not found.",
                cited_case_ids=[],
                provider="system",
                model="none",
                grounded=False,
            )

        cases: list[ReconciliationCase] = []
        offset = 0
        total = 1
        while offset < total:
            page, total = await cases_repo.list_cases(run_id, offset=offset, limit=500)
            cases.extend(page)
            offset += len(page)
            if not page:
                break
        if len(cases) != total:
            raise RuntimeError(
                f"Q&A evidence collection incomplete: loaded {len(cases)} of {total} cases"
            )
        cash_snapshot = await cases_repo.cash_position(run_id)

        computed_data = self._build_computed_data(run, cash_snapshot, cases, question)
        available_case_ids = {case.case_id for case in cases}

        if self.config.provider.casefold() in {"mock", "offline", "demo"}:
            answer, cited = self._deterministic_answer(
                question, computed_data, run, cash_snapshot, cases, available_case_ids
            )
            return QuestionResult(
                run_id=str(run_id),
                question=question,
                answer=answer,
                cited_case_ids=cited,
                provider="mock",
                model=self.config.model or "clearledger-mock-v1",
                grounded=True,
            )

        if self.config.enabled and self.config.api_key.get_secret_value():
            try:
                answer, cited = await self._call_llm(question, computed_data, available_case_ids)
                return QuestionResult(
                    run_id=str(run_id),
                    question=question,
                    answer=answer,
                    cited_case_ids=cited,
                    provider=self.config.provider,
                    model=self.config.model,
                    grounded=True,
                )
            except Exception as exc:
                logger.warning("AI Q&A call failed, falling back to deterministic: %s", exc)

        # Deterministic grounded fallback
        answer, cited = self._deterministic_answer(
            question, computed_data, run, cash_snapshot, cases, available_case_ids
        )
        return QuestionResult(
            run_id=str(run_id),
            question=question,
            answer=answer,
            cited_case_ids=cited,
            provider="deterministic_grounded_engine",
            model="invariants_v1",
            grounded=True,
        )

    def _build_computed_data(
        self,
        run: ReconciliationRun,
        cash: CashPositionSnapshot | None,
        cases: list[ReconciliationCase],
        question: str,
    ) -> dict[str, Any]:
        evaluation = run.evaluation or {}
        metrics = evaluation.get("aggregate") if isinstance(evaluation, dict) else None
        metrics = metrics if isinstance(metrics, dict) else None

        # Aggregate exceptions
        exceptions_by_code: dict[str, list[str]] = defaultdict(list)
        reconciled_cases: list[str] = []
        for case in cases:
            if case.case_state == "RECONCILED":
                reconciled_cases.append(case.case_id)
            elif case.exception_code:
                exceptions_by_code[case.exception_code].append(case.case_id)

        # Check for specific case query
        mentioned_cases = _CASE_ID_PATTERN.findall(question)
        specific_cases_detail: list[dict[str, Any]] = []
        for c in cases:
            if c.case_id in mentioned_cases:
                specific_cases_detail.append(
                    {
                        "case_id": c.case_id,
                        "state": c.case_state,
                        "cash_bucket": c.cash_bucket,
                        "gross_inr": format_paise(c.gross_amount_paise),
                        "net_inr": format_paise(c.net_amount_paise),
                        "residual_inr": format_paise(c.residual_paise),
                        "exception_code": c.exception_code,
                        "exception_severity": c.exception_severity,
                        "owner_role": c.owner_role,
                        "next_action": c.next_action,
                    }
                )

        return {
            "run_id": str(run.id),
            "status": run.status,
            "total_cases": len(cases),
            "reconciled_cases_count": len(reconciled_cases),
            "exception_cases_count": len(cases) - len(reconciled_cases),
            "stp_rate": f"{(len(reconciled_cases) / len(cases) * 100):.1f}%" if cases else "0%",
            "metrics": {
                "evaluation_status": "EVALUATED" if metrics is not None else "NOT_EVALUATED",
                "dataset_id": evaluation.get("dataset_id") if metrics is not None else None,
                "precision": metrics.get("relationship_precision") if metrics else None,
                "recall": metrics.get("relationship_recall") if metrics else None,
                "f1": metrics.get("relationship_f1") if metrics else None,
                "false_positives": metrics.get("false_positive_count") if metrics else None,
                "unexplained_residual_inr": format_paise(
                    sum(
                        abs(case.residual_paise)
                        for case in cases
                        if case.case_state == "RECONCILED"
                    )
                ),
            },
            "cash_position": {
                "available": cash is not None,
                "bank_confirmed": format_paise(
                    getattr(cash, "bank_confirmed_paise", 0) if cash else 0
                ),
                "settlement_in_transit": format_paise(
                    getattr(cash, "settlement_confirmed_in_transit_paise", 0) if cash else 0
                ),
                "expected_settlement": format_paise(
                    getattr(cash, "expected_settlement_paise", 0) if cash else 0
                ),
                "at_risk": format_paise(getattr(cash, "at_risk_paise", 0) if cash else 0),
                "unresolved": format_paise(getattr(cash, "unresolved_paise", 0) if cash else 0),
                "safe_cash": format_paise(getattr(cash, "safe_cash_paise", 0) if cash else 0),
                "scheduled_refunds": format_paise(
                    getattr(cash, "scheduled_refunds_paise", 0) if cash else 0
                ),
                "known_disputes": format_paise(
                    getattr(cash, "known_disputes_paise", 0) if cash else 0
                ),
                "reserve_holds": format_paise(
                    getattr(cash, "known_reserve_holds_paise", 0) if cash else 0
                ),
            },
            "exceptions_by_code": {
                code: {"count": len(ids), "case_ids": ids}
                for code, ids in exceptions_by_code.items()
            },
            "specific_queried_cases": specific_cases_detail,
        }

    async def _call_llm(
        self,
        question: str,
        computed_data: dict[str, Any],
        available_case_ids: set[str],
    ) -> tuple[str, list[str]]:
        template = self.prompt_path.read_text()
        prompt = template.replace(
            "{computed_data_json}", json.dumps(computed_data, indent=2)
        ).replace("{user_question}", question)

        client = openai.AsyncOpenAI(
            api_key=self.config.api_key.get_secret_value(),
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            max_retries=0,
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ],
                temperature=0.1,
            ),
            timeout=self.config.timeout_seconds,
        )
        answer = response.choices[0].message.content or "No response generated."
        self._validate_generated_answer(answer, computed_data, available_case_ids)
        cited = sorted(set(_CASE_ID_PATTERN.findall(answer)) & available_case_ids)
        return answer, cited

    @staticmethod
    def _validate_generated_answer(
        answer: str,
        computed_data: dict[str, Any],
        available_case_ids: set[str],
    ) -> None:
        """Fail closed when generated prose introduces unsupported identifiers or money."""
        unknown_cases = set(_CASE_ID_PATTERN.findall(answer)) - available_case_ids
        if unknown_cases:
            raise ValueError(f"answer cited unknown cases: {sorted(unknown_cases)}")

        def collect_money(value: Any) -> set[str]:
            if isinstance(value, dict):
                return set().union(*(collect_money(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(collect_money(item) for item in value))
            if isinstance(value, str):
                return set(_MONEY_PATTERN.findall(value))
            return set()

        unsupported_money = set(_MONEY_PATTERN.findall(answer)) - collect_money(computed_data)
        if unsupported_money:
            raise ValueError(
                f"answer introduced unsupported monetary facts: {sorted(unsupported_money)}"
            )

        metric_status = computed_data.get("metrics", {}).get("evaluation_status")
        accuracy_terms = re.search(r"\b(precision|recall|f1|accuracy)\b", answer, re.I)
        unavailable_language = re.search(r"\b(not evaluated|unavailable)\b", answer, re.I)
        if metric_status != "EVALUATED" and accuracy_terms and not unavailable_language:
            raise ValueError("answer claimed accuracy without a compatible evaluation")

    def _deterministic_answer(
        self,
        question: str,
        computed_data: dict[str, Any],
        run: ReconciliationRun,
        cash: CashPositionSnapshot | None,
        cases: list[ReconciliationCase],
        available_case_ids: set[str],
    ) -> tuple[str, list[str]]:
        """Fallback rule-based answers grounded strictly in computed facts."""
        q_lower = question.lower()
        cases_map = {c.case_id: c for c in cases}
        cited: list[str] = []

        # 1. Check if asking about specific case(s)
        mentioned = _CASE_ID_PATTERN.findall(question)
        if mentioned:
            lines: list[str] = []
            for cid in mentioned:
                case = cases_map.get(cid)
                if case:
                    cited.append(cid)
                    lines.append(f"### Case `{cid}` Details (Computed Fact)")
                    lines.append(f"- **State:** `{case.case_state}`")
                    lines.append(
                        f"- **Amounts:** Gross: {format_paise(case.gross_amount_paise)}, "
                        f"Net: {format_paise(case.net_amount_paise)}, "
                        f"Residual: {format_paise(case.residual_paise)}"
                    )
                    lines.append(f"- **Cash Bucket:** `{case.cash_bucket}`")
                    if case.exception_code:
                        lines.append(f"- **Exception Code:** `{case.exception_code}`")
                    if case.next_action:
                        lines.append(
                            f"- **Recommended Operator Action:** `{case.next_action}` "
                            f"(Assigned to: `{case.owner_role or 'Finance Ops'}`)"
                        )

                    # Domain-specific narrative for known edge cases
                    if "ambiguous" in (case.exception_code or "").lower():
                        lines.append(
                            "\n**Root Cause:** ClearLedger identified multiple candidate "
                            "bank credits of identical value within the settlement SLA window. "
                            "Under strict fail-closed rules, neither candidate was force-matched "
                            "to prevent false-positive misallocation."
                        )
                    elif self._contains_untrusted_instruction(case.record_snapshot or []):
                        lines.append(
                            "\n**Security Analysis:** Bank narration contained an instruction "
                            "to ignore rules and force reconciliation. ClearLedger treated the "
                            "narration strictly as untrusted data; deterministic token extraction "
                            "isolated only valid identifiers, and the case remained in exception "
                            "queue without state change."
                        )
            if lines:
                return "\n".join(lines), cited

        # 2. Cash position & liquidity questions
        cash_terms = ("cash", "position", "balance", "safe", "liquidity", "transit")
        if any(term in q_lower for term in cash_terms):
            cp = computed_data["cash_position"]
            if not cp["available"]:
                return (
                    "Cash position is unavailable because this run has no persisted snapshot.",
                    cited,
                )
            answer = (
                "### Cash Position Breakdown (Authoritative Integer Paise)\n\n"
                f"- **Bank Confirmed:** {cp['bank_confirmed']} *(verified credits in bank)*\n"
                f"- **Settlement In Transit:** {cp['settlement_in_transit']} *(within bank SLA)*\n"
                f"- **Expected Settlement:** {cp['expected_settlement']} *(pending batch)*\n"
                f"- **At Risk:** {cp['at_risk']} *(overdue or inconsistent SLA)*\n"
                f"- **Unresolved:** {cp['unresolved']} *(open exceptions)*\n\n"
                f"**Controlled Safe Cash:** **{cp['safe_cash']}** *(bank-confirmed net batch "
                "movements only; settlement fees and components are already reflected in net "
                "amounts).*\n\n"
                f"Tracked commitments: refunds {cp['scheduled_refunds']}, disputes "
                f"{cp['known_disputes']}, reserves {cp['reserve_holds']}."
            )
            return answer, cited

        # 3. Exceptions & Unresolved questions
        if any(term in q_lower for term in ("exception", "unresolved", "error", "fail", "issue")):
            exc_by_code = computed_data["exceptions_by_code"]
            total_exc = computed_data["exception_cases_count"]
            lines = [
                f"### Exception Queue Overview ({total_exc} Cases Total)\n",
                "ClearLedger refuses to force-match ambiguous records. Exceptions:",
            ]
            for code, data in sorted(exc_by_code.items()):
                sample_ids = data["case_ids"][:3]
                cited.extend(sample_ids)
                lines.append(
                    f"- **`{code}`** ({data['count']} cases): e.g. "
                    f"{', '.join(f'`{cid}`' for cid in sample_ids)}"
                )
            lines.append(
                "\nAll exceptions are routed with failed invariant checks, affected entity IDs, "
                "and recommended operator actions."
            )
            return "\n".join(lines), sorted(set(cited))

        # 4. Accuracy, Precision, STP questions
        metric_terms = ("stp", "precision", "recall", "accuracy", "match rate", "f1")
        if any(term in q_lower for term in metric_terms):
            m = computed_data["metrics"]
            stp = computed_data["stp_rate"]
            tot = computed_data["total_cases"]
            rec = computed_data["reconciled_cases_count"]
            if m["evaluation_status"] != "EVALUATED":
                return (
                    "### Reconciliation Throughput\n\n"
                    f"- **Straight-Through Processing (STP):** **{stp}** "
                    f"({rec}/{tot} reconciled)\n"
                    "- **Accuracy:** **Not evaluated** because no compatible ground-truth "
                    "evaluation is attached to this run.\n"
                    f"- **Operational unexplained residual:** "
                    f"**{m['unexplained_residual_inr']}** in reconciled cases."
                ), cited
            answer = (
                "### Reconciliation & Audit Metrics (Evaluated vs Ground Truth)\n\n"
                f"- **Straight-Through Processing (STP):** **{stp}** ({rec}/{tot} reconciled)\n"
                f"- **Verified Match Precision:** **{m['precision']:.4f}**\n"
                f"- **Relationship Recall:** **{m['recall']:.4f}**\n"
                f"- **F1 Score:** **{m['f1']:.4f}**\n"
                f"- **False Positive Count:** **{m['false_positives']}**\n"
                f"- **Unexplained Residual:** **{m['unexplained_residual_inr']}** across cases."
            )
            return answer, cited

        # 5. Default run overview
        tot = computed_data["total_cases"]
        rec = computed_data["reconciled_cases_count"]
        exc = computed_data["exception_cases_count"]
        stp = computed_data["stp_rate"]
        cp = computed_data["cash_position"]
        answer = (
            f"### Run `{str(run.id)[:8]}` Summary\n\n"
            f"Processed **{tot} cases** with an STP rate of **{stp}** "
            f"({rec} verified, {exc} exceptions).\n\n"
            f"- **Safe Cash:** {cp['safe_cash']} (Bank Confirmed: {cp['bank_confirmed']})\n"
            f"- **Unexplained Residual:** "
            f"{computed_data['metrics']['unexplained_residual_inr']}\n\n"
            "You can ask me specific questions such as:\n"
            "- *'Why is CASE_AMB0073 unresolved?'*\n"
            "- *'What is our bank confirmed vs at-risk cash?'*\n"
            "- *'Which cases had fee variances?'*\n"
            "- *'What is our STP rate and precision?'*"
        )
        return answer, cited

    @staticmethod
    def _contains_untrusted_instruction(value: Any) -> bool:
        if isinstance(value, dict):
            return any(GroundedQAService._contains_untrusted_instruction(v) for v in value.values())
        if isinstance(value, list):
            return any(GroundedQAService._contains_untrusted_instruction(v) for v in value)
        if not isinstance(value, str):
            return False
        normalized = value.casefold()
        return any(
            phrase in normalized
            for phrase in (
                "ignore all rules",
                "ignore previous instructions",
                "mark this as reconciled",
                "system prompt",
            )
        )
