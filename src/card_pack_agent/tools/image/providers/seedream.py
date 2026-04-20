"""Seedream 4.5 provider (via jiekou.ai proxy).

Endpoint: POST https://api.jiekou.ai/v3/seedream-4.5 (sync)
Auth:     Bearer {JIEKOU_API_KEY}

Payload shape (per jiekou snippet):
  size, image[], prompt, watermark, optimize_prompt_options.mode,
  sequential_image_generation, sequential_image_generation_options.max_images

Assumptions (to be verified on first live call, see raw_response):
  - Single-image-per-call use case → sequential_image_generation = "disabled"
  - optimize_prompt_options.mode = "disable" to keep our crafted prompts
  - watermark = False
  - size = "<width>x<height>" string

Pricing: unknown at wrap time; default estimate 0.02 USD/image (adjust after
first invoice). Set explicit override via GenerationParams.extra["cost_override"].
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ....config import settings
from ..base import (
    GenerationParams,
    ImageProvider,
    ImageResult,
    ProviderName,
    make_image_id,
    write_image_bytes,
)
from ._jiekou_common import (
    aspect_to_wh,
    download_bytes,
    extract_image_payload,
    jiekou_headers,
    jiekou_url,
)

log = structlog.get_logger()


class SeedreamProvider(ImageProvider):
    name = ProviderName.SEEDREAM_V45
    model = "seedream-4.5"

    def __init__(self) -> None:
        self._path = "/v3/seedream-4.5"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"SeedreamProvider({self.model})")

        w, h = (
            (params.width, params.height)
            if params.width and params.height
            else aspect_to_wh(params.aspect_ratio)
        )
        # seedream requires at least 3686400 pixels (1920x1920)
        if w * h < 3686400:
            w, h = max(w, 1920), max(h, 1920)

        payload: dict[str, Any] = {
            "prompt": params.prompt,
            "size": f"{w}x{h}",
            "watermark": bool(params.extra.get("watermark", False)),
        }
        # Only include image field when reference images are provided
        ref_images = params.extra.get("image", [])
        if ref_images:
            payload["image"] = ref_images

        t0 = time.monotonic()
        try:
            data = self._post(payload)
        except Exception as e:
            log.error("seedream.generate_failed", error=str(e))
            return self._error_result(params, str(e))

        url, img_bytes = extract_image_payload(data)
        if img_bytes is None and url:
            try:
                img_bytes = download_bytes(url)
            except Exception as e:
                return self._error_result(params, f"image download failed: {e}")
        if img_bytes is None:
            return self._error_result(
                params, f"no image payload found in response; keys={list(data.keys())}"
            )

        local_path = write_image_bytes(img_bytes, self.name, ext="png")
        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=self.model,
            image_url=str(local_path),
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=self.estimate_cost(params),
            width=w,
            height=h,
            raw_response={"upstream_url": url, "size": f"{w}x{h}"},
        )

    def estimate_cost(self, params: GenerationParams) -> float:
        override = params.extra.get("cost_override")
        if isinstance(override, (int, float)):
            return float(override)
        return 0.02

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=15),
        reraise=True,
    )
    def _post(self, payload: dict) -> dict:
        with httpx.Client(timeout=120) as client:
            r = client.post(jiekou_url(self._path), json=payload, headers=jiekou_headers())
            r.raise_for_status()
            return r.json() if r.content else {}

    def _error_result(self, params: GenerationParams, error: str) -> ImageResult:
        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=self.model,
            image_url="",
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            error=error,
        )
