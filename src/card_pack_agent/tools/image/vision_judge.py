"""Vision Judge — 用 Claude 的视觉能力给单张图打分。

评分维度（1-5）：
- prompt_alignment:    图是否忠实还原 prompt 描述
- visual_quality:      是否有文字崩坏、多指、面部畸变等常见缺陷
- style_match:         是否符合 strategy 里的 style_anchor + palette
- composition:         构图是否留出了预留文字区域
- overall:             综合判断

用于：
  1. 图像 bench：同一 prompt 多 provider 打分对比
  2. Evaluator 集成：生成完卡贴图可以选择性调用
  3. 驱动 prompt 迭代：分数低的 prompt 自动进入修改队列

注意：vision judge 本身有方差，单张打分不足以决策；
建议只在对比场景（>=2 张）或聚合 10+ 张时使用。
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from ...config import settings
from ...llm import LLMRole
from ...structured_output import structured_call
from .base import ImageResult

log = structlog.get_logger()


class VisionScore(BaseModel):
    prompt_alignment: float = Field(ge=1, le=5)
    visual_quality: float = Field(ge=1, le=5)
    style_match: float = Field(ge=1, le=5)
    composition: float = Field(ge=1, le=5)
    overall: float = Field(ge=1, le=5)
    issues: list[str] = Field(default_factory=list)
    comments: str = ""


@dataclass
class JudgeInput:
    image_result: ImageResult
    expected_prompt: str
    style_anchor: str = ""
    palette: list[str] | None = None
    composition_note: str = ""


VISION_JUDGE_SYSTEM = """你是图像质量评判 Agent。看完一张图后，对照提供的 prompt 和风格要求，按 5 个维度打分（1-5）。

评分严格，宁严勿宽：
- 3 分 = 可以勉强使用
- 4 分 = 质量过关
- 5 分 = 非常出色

维度：
- prompt_alignment: 图是否忠实还原 prompt 关键元素
- visual_quality: 有无技术缺陷（手指、面部、文字崩坏、扭曲）
- style_match: 是否符合要求的 style_anchor 和 palette
- composition: 构图是否合理（预留文字区域、主体清晰）
- overall: 综合判断

常见重大缺陷（任一出现，visual_quality ≤ 2）：
- 图像内直接生成了文字
- 人物手指数异常（6 根 / 粘连 / 缺失）
- 面部畸变、眼神不对称
- 主体被剪切
- 色调与要求明显不符

必须输出纯 JSON，无 markdown fence：
{
  "prompt_alignment": <1-5>,
  "visual_quality": <1-5>,
  "style_match": <1-5>,
  "composition": <1-5>,
  "overall": <1-5>,
  "issues": ["发现的缺陷列表"],
  "comments": "一句话总结"
}
"""


def _load_image_b64(image_url: str) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    if image_url.startswith("http"):
        import httpx
        with httpx.Client(timeout=30) as client:
            r = client.get(image_url)
            r.raise_for_status()
            data = r.content
            media_type = r.headers.get("content-type", "image/png").split(";")[0]
    else:
        data = Path(image_url).read_bytes()
        ext = Path(image_url).suffix.lower().lstrip(".")
        media_type = f"image/{ext if ext in ('png', 'jpeg', 'jpg', 'webp') else 'png'}"
        if media_type == "image/jpg":
            media_type = "image/jpeg"

    return base64.b64encode(data).decode("utf-8"), media_type


def judge_image(inp: JudgeInput) -> VisionScore:
    """对一张图打分。需要 APP_MODE=dev/prod 且有 Anthropic API Key。"""
    if not inp.image_result.ok:
        return VisionScore(
            prompt_alignment=1, visual_quality=1, style_match=1,
            composition=1, overall=1,
            issues=[f"image generation failed: {inp.image_result.error}"],
            comments="no image to judge",
        )

    # In mock mode, return canned score
    if settings.is_mock:
        return VisionScore(
            prompt_alignment=4.0, visual_quality=4.0, style_match=4.0,
            composition=4.0, overall=4.0,
            issues=[], comments="(mock judge)",
        )

    try:
        b64_data, media_type = _load_image_b64(inp.image_result.image_url)
    except Exception as e:
        log.error("vision_judge.load_failed", error=str(e))
        return VisionScore(
            prompt_alignment=1, visual_quality=1, style_match=1,
            composition=1, overall=1,
            issues=[f"could not load image: {e}"],
            comments="",
        )

    palette_str = ", ".join(inp.palette) if inp.palette else "(未指定)"
    user_text = (
        f"# 预期 prompt\n\n{inp.expected_prompt}\n\n"
        f"# 风格要求\n\nstyle_anchor: {inp.style_anchor or '(未指定)'}\n"
        f"palette: {palette_str}\n"
        f"composition_note: {inp.composition_note or '(无)'}\n\n"
        f"# 图像（见附件）\n\n请按 system prompt 要求打分。"
    )

    # Build multi-modal message (Anthropic messages format)
    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            },
        },
        {"type": "text", "text": user_text},
    ]

    # Manual call since structured_call expects plain text user content
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=settings.anthropic_model_judge,
        max_tokens=1024,
        temperature=0.2,
        system=VISION_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )

    from ...json_utils import parse_json_robust
    try:
        data = parse_json_robust(text)
        return VisionScore.model_validate(data)
    except Exception as e:
        log.error("vision_judge.parse_failed", error=str(e), raw=text[:500])
        return VisionScore(
            prompt_alignment=2, visual_quality=2, style_match=2,
            composition=2, overall=2,
            issues=[f"judge parse failed: {e}"],
            comments=text[:200],
        )
