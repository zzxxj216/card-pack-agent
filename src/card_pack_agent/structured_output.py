"""结构化输出调用层。

核心职责：
1. 发 LLM 请求
2. 拿到回复后先做 JSON 容错解析
3. 用 Pydantic schema 验证
4. 验证失败时把错误回传给 LLM 让它修（最多 N 次）
5. 记录 token 消耗和成本
6. 所有 request/response 落日志（失败的必留存）

使用：
    result, meta = structured_call(
        role=LLMRole.PLANNER,
        system=system_prompt,
        user=user_prompt,
        output_model=StrategyDoc,
        max_repair_attempts=2,
    )
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

import structlog
from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .json_utils import JSONRepairError, parse_json_robust
from .llm import LLMRole, _canned_response, _model_for

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


@dataclass
class CallMeta:
    """Instrumentation per LLM call."""

    call_id: str = field(default_factory=lambda: uuid4().hex[:12])
    role: str = ""
    model: str = ""
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    stop_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "role": self.role,
            "model": self.model,
            "attempts": self.attempts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.estimated_cost_usd, 6),
            "stop_reason": self.stop_reason,
        }


# --- Per-model pricing (USD per million tokens, input/output) ---
# Update when pricing changes. Unknown models default to conservative estimate.

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}
_DEFAULT_PRICING = (10.0, 40.0)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = _PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


# --- Raw LLM call with Anthropic SDK retries (network-level) ---

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=10),
    reraise=True,
)
def _call_anthropic(
    *,
    role: LLMRole,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    """Raw messages API call. Returns (text, usage_dict).

    usage_dict has input_tokens, output_tokens, stop_reason.
    """
    if settings.is_mock:
        user_text = next((m["content"] for m in messages if m["role"] == "user"), "")
        return _canned_response(role=role, user=user_text), {
            "input_tokens": 0, "output_tokens": 0, "stop_reason": "end_turn",
        }

    if settings.anthropic_base_url:
        return _call_via_httpx(
            model=model, system=system, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )

    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages,
    )
    text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    text = "\n".join(text_parts)
    usage = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "stop_reason": resp.stop_reason,
    }
    return text, usage


def _call_via_httpx(
    *,
    model: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict]:
    """Direct httpx call for third-party API proxies that don't work with the Anthropic SDK."""
    import httpx as _httpx

    base = settings.anthropic_base_url.rstrip("/")
    url = f"{base}/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
    }
    resp = _httpx.post(url, headers=headers, json=body, timeout=600)
    resp.raise_for_status()
    data = resp.json()

    text_parts = [
        b["text"] for b in data.get("content", []) if b.get("type") == "text"
    ]
    text = "\n".join(text_parts)
    usage_raw = data.get("usage", {})
    usage = {
        "input_tokens": usage_raw.get("input_tokens", 0),
        "output_tokens": usage_raw.get("output_tokens", 0),
        "stop_reason": data.get("stop_reason", "end_turn"),
    }
    return text, usage


# --- Structured call with repair loop ---

REPAIR_PROMPT_TEMPLATE = """你上一次的回复无法被解析为符合要求的 JSON。

错误信息：
{error}

原始回复（前 2000 字符）：
{raw}

请重新输出。注意：
1. 必须是**纯 JSON**，前后不带任何解释文字，不带 markdown fence
2. 所有字段名和枚举值必须严格匹配 schema
3. 不要截断，如果内容多，分段输出也要保证是完整的 JSON
"""


def structured_call(
    *,
    role: LLMRole,
    system: str,
    user: str,
    output_model: type[T],
    max_tokens: int = 4096,
    temperature: float = 0.3,
    max_repair_attempts: int = 2,
    is_list: bool = False,
) -> tuple[T | list[T], CallMeta]:
    """Call LLM, parse JSON, validate with Pydantic, repair-retry on failure.

    :param is_list: Set True if you expect a JSON array of output_model.
    :returns: (model instance or list of instances, metadata)
    """
    model = _model_for(role)
    meta = CallMeta(role=role.value, model=model)

    messages: list[dict] = [{"role": "user", "content": user}]
    last_error: str = ""
    last_raw: str = ""

    for attempt in range(max_repair_attempts + 1):
        meta.attempts = attempt + 1

        try:
            raw, usage = _call_anthropic(
                role=role, model=model, system=system, messages=messages,
                max_tokens=max_tokens, temperature=temperature,
            )
        except Exception as e:
            log.error("structured_call.network_failure",
                      call_id=meta.call_id, attempt=attempt, error=str(e))
            raise

        meta.input_tokens += usage["input_tokens"]
        meta.output_tokens += usage["output_tokens"]
        meta.total_tokens = meta.input_tokens + meta.output_tokens
        meta.estimated_cost_usd = _estimate_cost(
            model, meta.input_tokens, meta.output_tokens
        )
        meta.stop_reason = usage.get("stop_reason")

        last_raw = raw

        # Detect truncation — retry immediately with higher max_tokens (once)
        if usage.get("stop_reason") == "max_tokens" and attempt == 0:
            log.warning("structured_call.truncated",
                        call_id=meta.call_id, bumping_max_tokens=True)
            max_tokens = min(max_tokens * 2, 16384)
            continue

        # Stage 1: JSON parse
        try:
            data = parse_json_robust(raw)
        except JSONRepairError as e:
            last_error = f"JSON parse failed: {e}"
            log.warning("structured_call.parse_failed",
                        call_id=meta.call_id, attempt=attempt, error=last_error)
            _log_failure(meta.call_id, role, system, user, raw, last_error)
            messages = _build_repair_messages(user, raw, last_error)
            continue

        # Stage 2: Pydantic validation
        try:
            if is_list:
                if not isinstance(data, list):
                    # Accept {"items": [...]} or {"cards": [...]}
                    for key in ("items", "cards", "shots", "results", "data"):
                        if isinstance(data, dict) and key in data and isinstance(data[key], list):
                            data = data[key]
                            break
                    else:
                        raise ValueError(f"expected a list, got {type(data).__name__}")
                result = [output_model.model_validate(item) for item in data]
            else:
                result = output_model.model_validate(data)
        except (ValidationError, ValueError) as e:
            last_error = _format_validation_error(e)
            log.warning("structured_call.validation_failed",
                        call_id=meta.call_id, attempt=attempt, error=last_error[:500])
            _log_failure(meta.call_id, role, system, user, raw, last_error)
            messages = _build_repair_messages(user, raw, last_error)
            continue

        # Success
        log.info("structured_call.success", **meta.as_dict())
        return result, meta

    # All attempts exhausted
    log.error("structured_call.exhausted",
              call_id=meta.call_id, attempts=meta.attempts, error=last_error[:500])
    raise StructuredCallError(
        f"structured_call failed after {meta.attempts} attempts: {last_error}",
        meta=meta,
        raw=last_raw,
    )


class StructuredCallError(RuntimeError):
    def __init__(self, message: str, meta: CallMeta, raw: str):
        super().__init__(message)
        self.meta = meta
        self.raw = raw


def _format_validation_error(e: Exception) -> str:
    if isinstance(e, ValidationError):
        errors = e.errors()
        if not errors:
            return str(e)
        # Compact format: show first 5 errors with location + message
        lines = []
        for err in errors[:5]:
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']} (type={err['type']})")
        suffix = f" ...and {len(errors) - 5} more" if len(errors) > 5 else ""
        return "Schema validation errors:\n" + "\n".join(lines) + suffix
    return str(e)


def _build_repair_messages(
    original_user: str, prior_raw: str, error: str,
) -> list[dict]:
    """Build a conversation to ask the LLM to fix its previous output."""
    repair = REPAIR_PROMPT_TEMPLATE.format(error=error, raw=prior_raw[:2000])
    return [
        {"role": "user", "content": original_user},
        {"role": "assistant", "content": prior_raw},
        {"role": "user", "content": repair},
    ]


# --- Failure logging to disk (for later debugging) ---

def _log_failure(call_id: str, role: LLMRole, system: str, user: str,
                 raw: str, error: str) -> None:
    """Write failed exchange to logs/ for postmortem."""
    log_dir = Path("./logs/llm_failures")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    log_file = log_dir / f"{call_id}.json"
    try:
        log_file.write_text(json.dumps({
            "call_id": call_id,
            "role": role.value,
            "error": error,
            "system": system[:5000],
            "user": user[:5000],
            "raw_response": raw,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
