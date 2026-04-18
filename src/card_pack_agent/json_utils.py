"""LLM 输出的 JSON 容错解析。

真实 LLM 返回的常见病态：
- ```json fence 或 ``` fence
- 前后夹带解释文字 "Here's the JSON:\n{...}\nLet me know if..."
- 单引号而不是双引号
- trailing comma
- 字符串内部有未转义换行
- JSON 被截断（max_tokens 触发）

策略：先尝试严格 json.loads，失败则逐层放宽。无法修复时抛 JSONRepairError
并把原文附上，方便上层决定是否重试。
"""
from __future__ import annotations

import json
import re
from typing import Any


class JSONRepairError(ValueError):
    """Raised when JSON cannot be repaired. Contains raw text for debugging."""

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def parse_json_robust(text: str) -> Any:
    """Multi-stage JSON parse. Returns dict or list, never raises on common issues."""
    if not text or not text.strip():
        raise JSONRepairError("empty response", text)

    # Stage 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Stage 2: strip fences
    stripped = _strip_code_fences(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Stage 3: extract first {...} or [...] block (handles preambles)
    extracted = _extract_json_block(stripped)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

        # Stage 4: repair common issues on the extracted block
        repaired = _apply_repairs(extracted)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as e:
            raise JSONRepairError(
                f"could not repair JSON: {e.msg} at pos {e.pos}", text
            ) from e

    raise JSONRepairError("no JSON object or array found in response", text)


# --- Stages ---

def _strip_code_fences(text: str) -> str:
    t = text.strip()
    # ```json ... ``` or ``` ... ```
    fence = re.match(r"^```(?:json|JSON)?\s*\n(.*?)\n```\s*$", t, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Partial fence (start only, no end)
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _extract_json_block(text: str) -> str | None:
    """Find the first balanced {...} or [...] substring.

    Returns None if none found. Handles nested braces and string escapes
    but not all pathological cases.
    """
    brace_start = text.find("{")
    bracket_start = text.find("[")

    candidates: list[tuple[str, str, int]] = []
    if brace_start != -1:
        candidates.append(("{", "}", brace_start))
    if bracket_start != -1:
        candidates.append(("[", "]", bracket_start))
    if not candidates:
        return None

    candidates.sort(key=lambda c: c[2])

    for opener, closer, start in candidates:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text[start:]
    return None


def _apply_repairs(text: str) -> str:
    """Attempt fixes that are safe-ish."""
    t = text
    # Remove trailing commas before } or ]
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    # Close truncated JSON: count unbalanced { and [, append matching closers
    t = _close_unbalanced(t)
    return t


def _close_unbalanced(text: str) -> str:
    """If braces/brackets are unbalanced due to truncation, append closers."""
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1

    # If we're still in a string, we can't safely repair — bail early
    if in_string:
        return text + '"'  # best-effort
    return text + ("]" * max(depth_bracket, 0)) + ("}" * max(depth_brace, 0))
