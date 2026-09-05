"""OpenAI-compatible structured-output client with fail-closed behavior."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Protocol

import openai
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import ValidationError

from services.ai_analyst.evidence_packet import AIEvidencePacket
from services.ai_analyst.schemas import (
    AIAnalysisResponse,
    AIClientConfig,
    AIClientResult,
    ValidationResult,
)
from services.ai_analyst.validator import validate_ai_response

logger = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROMPT = _ROOT / "prompts" / "exception_analyst.v1.md"


def _is_groq(config: AIClientConfig) -> bool:
    return config.provider.casefold() == "groq" or "api.groq.com" in (config.base_url or "")


def _is_hugging_face(config: AIClientConfig) -> bool:
    return config.provider.casefold() in {"huggingface", "hugging_face", "hf"} or (
        "router.huggingface.co" in (config.base_url or "")
    )


def _provider_error_detail(exc: openai.APIError) -> str:
    parts = [f"status={getattr(exc, 'status_code', 'unknown')}"]
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            if error.get("code"):
                parts.append(f"code={str(error['code'])[:100]}")
            if error.get("message"):
                parts.append(f"message={str(error['message'])[:300]}")
    return " ".join(parts)


class AIAnalyzerClient(Protocol):
    async def analyze_case(
        self,
        case_id: str,
        evidence_packet: AIEvidencePacket,
    ) -> AIClientResult: ...


def render_analysis_prompt(
    evidence_packet: AIEvidencePacket,
    *,
    prompt_path: str | Path = _DEFAULT_PROMPT,
) -> str:
    template = Path(prompt_path).read_text()
    return (
        template.replace(
            "{allowed_exception_codes}",
            json.dumps(evidence_packet.allowed_exception_codes, separators=(",", ":")),
        )
        .replace(
            "{allowed_action_codes}",
            json.dumps(evidence_packet.allowed_action_codes, separators=(",", ":")),
        )
        .replace("{evidence_packet_json}", evidence_packet.model_dump_json())
        .replace(
            "{output_schema_json}",
            json.dumps(AIAnalysisResponse.model_json_schema(), separators=(",", ":")),
        )
    )


class OpenAICompatibleClient:
    def __init__(
        self,
        config: AIClientConfig,
        *,
        prompt_path: str | Path = _DEFAULT_PROMPT,
    ) -> None:
        self.config = config
        self.prompt_path = Path(prompt_path)

    def _estimated_cost(self, prompt_tokens: int, completion_tokens: int) -> int:
        """Calculate estimated cost in micro-dollars (1 micro-dollar = $0.000001)."""
        cost_usd = (
            prompt_tokens * self.config.input_cost_per_1k_tokens
            + completion_tokens * self.config.output_cost_per_1k_tokens
        ) / 1_000
        return int(round(cost_usd * 1_000_000))  # Convert to micro-dollars

    async def analyze_case(
        self,
        case_id: str,
        evidence_packet: AIEvidencePacket,
    ) -> AIClientResult:
        if not self.config.enabled:
            return AIClientResult(failure_type="disabled", failure_reason="AI is disabled.")
        if case_id != evidence_packet.case_id:
            return AIClientResult(
                failure_type="invalid_request",
                failure_reason="Case ID does not match evidence packet.",
            )

        client = openai.AsyncOpenAI(
            api_key=self.config.api_key.get_secret_value(),
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            max_retries=0,
        )
        prompt = render_analysis_prompt(evidence_packet, prompt_path=self.prompt_path)
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Analyze the packet and return the required JSON."},
        ]
        response_format: ResponseFormatJSONSchema = {
            "type": "json_schema",
            "json_schema": {
                "name": "clearledger_ai_analysis",
                "strict": True,
                "schema": AIAnalysisResponse.model_json_schema(),
            },
        }
        result = AIClientResult()
        provider_options = None
        if self.config.model.startswith("openai/gpt-oss"):
            if _is_groq(self.config):
                provider_options = {"reasoning_effort": "low", "include_reasoning": False}
            elif _is_hugging_face(self.config):
                provider_options = {"reasoning_effort": "low"}
        started = time.perf_counter()
        try:
            for attempt in range(self.config.max_retries + 1):
                result.attempts = attempt + 1
                try:
                    completion = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=self.config.model,
                            messages=messages,
                            response_format=response_format,
                            extra_body=provider_options,
                        ),
                        timeout=self.config.timeout_seconds,
                    )
                except (TimeoutError, openai.APITimeoutError):
                    result.failure_type = "timeout"
                    result.failure_reason = "AI provider timed out."
                    logger.warning("AI analysis timed out for case %s", case_id)
                    break
                except openai.APIError as exc:
                    retryable = attempt < self.config.max_retries and (
                        (
                            (_is_groq(self.config) or _is_hugging_face(self.config))
                            and exc.status_code == 400
                        )
                        or (exc.status_code is not None and exc.status_code >= 500)
                    )
                    if retryable:
                        logger.warning(
                            "AI provider failed for case %s; retrying: %s",
                            case_id,
                            _provider_error_detail(exc),
                        )
                        await asyncio.sleep(0.25 * (attempt + 1))
                        continue
                    result.failure_type = "provider_error"
                    result.failure_reason = f"AI provider error: {type(exc).__name__}"
                    logger.warning(
                        "AI provider failed for case %s: %s (%s)",
                        case_id,
                        type(exc).__name__,
                        _provider_error_detail(exc),
                    )
                    break

                if completion.usage is not None:
                    result.prompt_tokens += completion.usage.prompt_tokens or 0
                    result.completion_tokens += completion.usage.completion_tokens or 0
                content = completion.choices[0].message.content or ""
                validation_feedback: list[dict[str, str]]
                try:
                    raw = json.loads(content)
                    result.raw_response = raw if isinstance(raw, dict) else {"value": raw}
                    parsed = AIAnalysisResponse.model_validate(raw)
                    validation = validate_ai_response(parsed, evidence_packet)
                    result.validation = validation
                    if validation.valid:
                        result.response = parsed
                        result.failure_reason = None
                        result.failure_type = None
                        break
                    validation_feedback = validation.errors
                except (json.JSONDecodeError, ValidationError) as exc:
                    validation_feedback = [
                        {
                            "code": "INVALID_STRUCTURED_OUTPUT",
                            "message": str(exc)[:500],
                        }
                    ]
                    result.validation = ValidationResult(valid=False, errors=validation_feedback)

                result.failure_type = "invalid_response"
                result.failure_reason = "AI response failed external validation."
                if attempt < self.config.max_retries:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous JSON was rejected. Correct only these validation "
                                "errors and return a complete JSON object: "
                                f"{json.dumps(validation_feedback)}"
                            ),
                        }
                    )
            return result
        finally:
            result.latency_ms = round((time.perf_counter() - started) * 1_000)
            result.estimated_cost = self._estimated_cost(
                result.prompt_tokens,
                result.completion_tokens,
            )
            await client.close()


async def analyze_case(
    case_id: str,
    evidence_packet: AIEvidencePacket,
    config: AIClientConfig,
) -> AIAnalysisResponse | None:
    """Convenience API matching the service-level Phase 4 contract."""
    return (await OpenAICompatibleClient(config).analyze_case(case_id, evidence_packet)).response
