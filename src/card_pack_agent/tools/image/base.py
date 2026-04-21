"""图像生成 Provider 接口与通用类型。

所有模型（FLUX / gpt-image-1 / Replicate / 自托管）都实现 ImageProvider，
调用方不关心底层差异。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


class ProviderName(str, Enum):
    """注册表里的 provider 名字。新增模型在这里加一行。"""

    MOCK = "mock"
    FLUX_PRO = "flux_pro"          # Black Forest Labs, via Replicate or fal.ai
    FLUX_SCHNELL = "flux_schnell"  # 快速/便宜版
    OPENAI_IMAGE = "openai_image"  # gpt-image-1 (OpenAI direct)
    REPLICATE = "replicate"        # 通用 Replicate 模型 (SDXL / custom LoRA)
    STABILITY = "stability"        # Stability AI 直接 API
    # jiekou.ai proxy endpoints
    SEEDREAM_V45 = "seedream_v45"                    # /v3/seedream-4.5
    FLUX_KONTEXT_MAX = "flux_kontext_max"            # /v3/async/flux-1-kontext-max
    MIDJOURNEY_TXT2IMG = "midjourney_txt2img"        # /v3/async/mj-txt2img
    JIEKOU_OPENAI = "jiekou_openai"                  # /v1/images/generations (OpenAI-compat via jiekou)
    # Google direct
    GEMINI_FLASH_IMAGE_EDIT = "gemini_flash_image_edit"  # /v3/gemini-3.1-flash-image-edit


@dataclass
class GenerationParams:
    """传递给 provider 的生成参数。各 provider 按需取用，忽略不懂的字段。"""

    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "9:16"   # TikTok 主力
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    guidance: float | None = None
    seed: int | None = None
    style_reference_url: str | None = None   # 用于风格一致性锁定
    extra: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """用于缓存 key 的稳定哈希，不含 prompt 本身（prompt 另参与）。"""
        data = {
            "negative_prompt": self.negative_prompt,
            "aspect_ratio": self.aspect_ratio,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "guidance": self.guidance,
            "seed": self.seed,
            "style_reference_url": self.style_reference_url,
            "extra": self.extra,
        }
        blob = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class ImageResult:
    """单次图像生成的结果。"""

    image_id: str                       # internal uuid
    provider: ProviderName
    model: str                          # 具体 model slug (flux-pro-1.1 / gpt-image-1)
    image_url: str                      # 本地路径或 https URL
    image_bytes: bytes | None = None    # 可选：小图可存内存，大图只留 URL
    params_fingerprint: str = ""
    prompt: str = ""
    latency_ms: int = 0
    cost_usd: float = 0.0
    width: int = 0
    height: int = 0
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.image_url)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider.value
        d["created_at"] = self.created_at.isoformat()
        d.pop("image_bytes", None)  # don't serialize raw bytes
        return d


@runtime_checkable
class ImageProvider(Protocol):
    """所有图像模型客户端实现这个接口。"""

    name: ProviderName
    model: str   # provider-specific model identifier

    def generate(self, params: GenerationParams) -> ImageResult:
        """阻塞调用，返回单张图的结果。失败时 ImageResult.error 被设置。"""
        ...

    def estimate_cost(self, params: GenerationParams) -> float:
        """预估单张调用成本（USD）。不联网。用于预算检查。"""
        ...


# --- Helpers ---

def make_image_id() -> str:
    return uuid4().hex[:12]


def write_image_bytes(
    data: bytes, provider: ProviderName, ext: str = "png",
    base_dir: Path | None = None,
) -> Path:
    """把字节落地到 storage_local_path/<provider>/<uuid>.<ext>，返回路径。"""
    from ...config import settings
    base = base_dir or settings.storage_local_path
    target = base / provider.value
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{make_image_id()}.{ext}"
    path.write_bytes(data)
    return path
