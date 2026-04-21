"""Anthropic SDK 封装。Mock 模式下返回 canned data，生产走真实 API。"""
from __future__ import annotations

import json
from enum import Enum
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings

log = structlog.get_logger()


class LLMRole(str, Enum):
    PLANNER = "planner"
    GENERATOR = "generator"
    REVIEWER = "reviewer"
    JUDGE = "judge"


def _model_for(role: LLMRole) -> str:
    return {
        LLMRole.PLANNER: settings.anthropic_model_planner,
        LLMRole.GENERATOR: settings.anthropic_model_generator,
        LLMRole.REVIEWER: settings.anthropic_model_reviewer,
        LLMRole.JUDGE: settings.anthropic_model_judge,
    }[role]


class LLMClient:
    """Anthropic messages API 的薄封装，按 role 路由模型。"""

    def __init__(self) -> None:
        self._client: Any = None  # lazy init to avoid import cost in mock mode

    def _real_client(self) -> Any:
        if self._client is None:
            settings.require_real_mode("LLMClient")
            from anthropic import Anthropic
            client_kwargs: dict = {"api_key": settings.anthropic_api_key}
            if settings.anthropic_base_url:
                client_kwargs["base_url"] = settings.anthropic_base_url
            self._client = Anthropic(**client_kwargs)
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def complete(
        self,
        *,
        role: LLMRole,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Return raw text response. JSON parsing handled by caller."""
        if settings.is_mock:
            return _canned_response(role=role, user=user)

        model = _model_for(role)
        log.info("llm.call", role=role.value, model=model, user_len=len(user))

        if settings.anthropic_base_url:
            return self._call_via_httpx(
                model=model, system=system, user=user,
                max_tokens=max_tokens, temperature=temperature,
            )

        resp = self._real_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts)

    def _call_via_httpx(
        self, *, model: str, system: str, user: str,
        max_tokens: int, temperature: float,
    ) -> str:
        import httpx
        base = settings.anthropic_base_url.rstrip("/")
        resp = httpx.post(
            f"{base}/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()
        parts = [
            b["text"] for b in data.get("content", [])
            if b.get("type") == "text"
        ]
        return "\n".join(parts)

    def complete_json(
        self,
        *,
        role: LLMRole,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Convenience: run complete() then parse JSON, stripping code fences if present."""
        text = self.complete(
            role=role, system=system, user=user,
            max_tokens=max_tokens, temperature=temperature,
        )
        return parse_json_loose(text)


def parse_json_loose(text: str) -> dict[str, Any]:
    """Strip ```json fences and parse. Raise if still invalid."""
    t = text.strip()
    if t.startswith("```"):
        # remove first fence line
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        # remove trailing fence
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    # sometimes model prepends the word "json\n"
    if t.startswith("json\n"):
        t = t[5:]
    return json.loads(t)


# --- Mock canned responses (for APP_MODE=mock smoke tests) ---

def _canned_response(role: LLMRole, user: str) -> str:  # noqa: ARG001
    """Return structural but obviously fake data. Shape matches Pydantic schemas."""
    if role == LLMRole.PLANNER:
        return json.dumps(_MOCK_STRATEGY_DOC)
    if role == LLMRole.GENERATOR:
        # Detect whether caller is asking for cards or script by cheap heuristic
        if (
            "分镜脚本" in user
            or "shot-list" in user.lower()
            or "shots" in user.lower()
            or "total_duration" in user.lower()
        ):
            return json.dumps(_MOCK_SCRIPT)
        # Parse range_start / range_end from user prompt if present (batched path).
        # Supports both Chinese ("position X 到 Y") and English ("positions X to Y").
        import re as _re
        m_start = _re.search(
            r"positions?\s+(\d+)\s*(?:到|to|-|–)\s*(\d+)",
            user,
            _re.IGNORECASE,
        )
        if m_start:
            start, end = int(m_start.group(1)), int(m_start.group(2))
            cards_slice = [c for c in _MOCK_CARDS if start <= c["position"] <= end]
            return json.dumps(cards_slice)
        return json.dumps(_MOCK_CARDS)
    if role == LLMRole.REVIEWER:
        return json.dumps(_MOCK_REVIEW)
    if role == LLMRole.JUDGE:
        return json.dumps({
            "overall_score": 3.8,
            "dimensions": {
                "style_consistency": 4.0,
                "structural_integrity": 4.0,
                "rule_adherence": 3.5,
                "anti_pattern_clean": 4.0,
                "internal_dedup": 3.5,
            },
            "comments": "Mock judge output. Structure looks ok.",
        })
    return "{}"


_MOCK_STRATEGY_DOC: dict[str, Any] = {
    "version": "1.0",
    "topic": "MOCK_TOPIC",
    "classification": {
        "l1": "festival",
        "l2": "resonance_healing",
        "l3": ["palette:warm", "text:minimal", "subject:single_object", "pace:slow", "cta:soft", "style:realistic"],
        "reasoning": "Mock classification",
    },
    "referenced_cases": [],
    "structure": {
        "total_cards": 50,
        "segments": [
            {"range": [1, 3], "role": "hook", "notes": "single warm object"},
            {"range": [4, 15], "role": "setup", "notes": "scene details"},
            {"range": [16, 35], "role": "development", "notes": "memory fragments"},
            {"range": [36, 45], "role": "turn", "notes": "soft turn"},
            {"range": [46, 50], "role": "close", "notes": "quiet close"},
        ],
    },
    "visual_direction": {
        "palette": ["#F5A623", "#E8824A", "#FFF8E7"],
        "main_subject": "single warm-toned everyday object",
        "composition_note": "large negative space top for text overlay",
        "style_anchor": "film photography, 35mm, natural light",
    },
    "copy_direction": {
        "tone": "克制、温柔、具体",
        "text_density": "minimal",
        "pronoun": "你",
        "hook_type": "独立意象 + 错位时态",
        "cta": {"intensity": "soft", "example": "评论区说说你的今年"},
    },
    "avoid": ["全家团圆刻板叙事", "连续三张以上情绪渲染词"],
    "script_hint": {
        "narrative_arc": "物件 → 场景 → 回忆 → 当下 → 留白",
        "pacing_note": "1.5-2s 每张，35-40s 总时长",
    },
}

def _segment_for_position(i: int, total: int) -> str:
    if i <= 3:
        return "hook"
    if i <= int(total * 0.3):
        return "setup"
    if i <= int(total * 0.7):
        return "development"
    if i <= int(total * 0.9):
        return "turn"
    return "close"


_MOCK_CARDS: list[dict[str, Any]] = [
    {
        "position": i,
        "segment": _segment_for_position(i, 50),
        "prompt": f"MOCK card {i} prompt, warm tones, single object, film photography",
        "negative_prompt": "text, watermark, logo, typography, captions",
        "composition_note": "subject lower-left, negative space top",
        "text_overlay_hint": {
            "content_suggestion": f"mock overlay {i}",
            "position": "top-center",
            "size_tier": "body" if i > 3 else "hook",
        },
    }
    for i in range(1, 51)
]


_MOCK_SCRIPT_POSITIONS = [1, 8, 20, 30, 40, 48, 50]
_MOCK_SCRIPT: dict[str, Any] = {
    "version": "1.0",
    "total_duration_s": round(2.0 * len(_MOCK_SCRIPT_POSITIONS), 2),
    "bgm_suggestion": {
        "mood": "slow, warm, acoustic",
        "reference": "mock reference",
        "tempo_curve": "slow throughout",
    },
    "has_voiceover": False,
    "shots": [
        {
            "position": p,
            "duration_s": 2.0,
            "text_overlay": {
                "content": f"mock overlay {p}",
                "position": "top-center",
                "size_tier": "body",
                "animation": "fade-in",
                "dwell_s": 1.5,
            },
            "sfx": None,
            "voiceover": None,
            "notes": "",
        }
        for p in _MOCK_SCRIPT_POSITIONS
    ],
    "key_moments": [
        {"position": 1, "role": "hook", "craft_note": "mock"},
        {"position": 30, "role": "emotional_peak", "craft_note": "mock"},
        {"position": 50, "role": "close", "craft_note": "mock"},
    ],
}

_MOCK_REVIEW: dict[str, Any] = {
    "window": {"start": "2026-04-01", "end": "2026-04-14", "category": "festival"},
    "sample_size": {"top": 0, "bottom": 0},
    "per_pack_attribution": [],
    "cross_pack_contrast": {"visual": [], "copy": [], "narrative": [], "pacing": []},
    "extracted_rules": [],
    "open_questions": ["Mock mode — no real data"],
    "summary_for_humans": "Mock review output.",
}


# Module-level singleton
llm = LLMClient()
