"""图像生成缓存。

Key = sha256(provider + model + prompt + params_fingerprint)
Value = ImageResult (metadata JSON) + 图片文件

相同 (provider, prompt, params) 的重复调用直接命中缓存，省钱 + 实验可复现。

禁用：实验对比评测时可以 disable 掉（强制真实生成，便于测试方差）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import structlog

from ...config import settings
from .base import GenerationParams, ImageResult, ProviderName

log = structlog.get_logger()


def _cache_dir() -> Path:
    return settings.storage_local_path / "_image_cache"


def _key(provider: ProviderName, model: str, params: GenerationParams) -> str:
    blob = f"{provider.value}::{model}::{params.prompt}::{params.fingerprint()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _meta_path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def get(
    provider: ProviderName, model: str, params: GenerationParams,
) -> ImageResult | None:
    """Return cached result or None."""
    meta_file = _meta_path(_key(provider, model, params))
    if not meta_file.exists():
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        result = ImageResult(
            image_id=data["image_id"],
            provider=ProviderName(data["provider"]),
            model=data["model"],
            image_url=data["image_url"],
            params_fingerprint=data.get("params_fingerprint", ""),
            prompt=data.get("prompt", ""),
            latency_ms=data.get("latency_ms", 0),
            cost_usd=data.get("cost_usd", 0.0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            raw_response=data.get("raw_response", {}),
            error=data.get("error"),
        )
        # Verify the image file still exists (for local-path results)
        if result.image_url and not result.image_url.startswith("http"):
            if not Path(result.image_url).exists():
                return None
        return result
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning("image_cache.corrupted", key=meta_file.name, error=str(e))
        return None


def put(result: ImageResult, params: GenerationParams) -> None:
    """Store result. Silently ignores IO errors."""
    if not result.ok:
        return
    try:
        key = _key(result.provider, result.model, params)
        meta_file = _meta_path(key)
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("image_cache.write_failed", error=str(e))


def clear() -> int:
    """Delete all cache entries. Returns count removed."""
    d = _cache_dir()
    if not d.exists():
        return 0
    files = list(d.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)
