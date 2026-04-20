"""Gemini 3.1 Flash Image Edit provider (via jiekou.ai, Google key).

Endpoint: POST https://api.jiekou.ai/v3/gemini-3.1-flash-image-edit (sync)
Auth:     Bearer {GEMINI_API_KEY}  (AIza... — Google key, NOT jiekou sk_ key)

Payload:
  size, google.{web_search, image_search}, prompt, image_urls[],
  aspect_ratio, image_base64s[], output_format

Note: this is an EDIT endpoint. Pure text-to-image likely needs at least one
reference image. We accept extra["image_urls"] / extra["image_base64s"] and
pass them through. If neither is provided, the call may fail server-side and
we surface the error cleanly.
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
    jiekou_url,
)

log = structlog.get_logger()


class GeminiFlashImageEditProvider(ImageProvider):
    name = ProviderName.GEMINI_FLASH_IMAGE_EDIT
    model = "gemini-3.1-flash-image-edit"

    def __init__(self) -> None:
        self._path = "/v3/gemini-3.1-flash-image-edit"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"GeminiFlashImageEditProvider({self.model})")
        if not settings.gemini_api_key:
            return self._error_result(params, "GEMINI_API_KEY missing")

        w, h = (
            (params.width, params.height)
            if params.width and params.height
            else aspect_to_wh(params.aspect_ratio or "9:16")
        )

        payload: dict[str, Any] = {
            "prompt": params.prompt,
            "size": f"{w}x{h}",
            "aspect_ratio": params.aspect_ratio or "9:16",
            "output_format": params.extra.get("output_format", "png"),
            "image_urls": params.extra.get("image_urls", []),
            "image_base64s": params.extra.get("image_base64s", []),
            "google": {
                "web_search": bool(params.extra.get("web_search", False)),
                "image_search": bool(params.extra.get("image_search", False)),
            },
        }

        t0 = time.monotonic()
        try:
            data = self._post(payload)
        except Exception as e:
            log.error("gemini_flash_image.generate_failed", error=str(e))
            return self._error_result(params, str(e))

        url, img_bytes = extract_image_payload(data)
        if img_bytes is None and url:
            try:
                img_bytes = download_bytes(url)
            except Exception as e:
                return self._error_result(params, f"image download failed: {e}")
        if img_bytes is None:
            return self._error_result(
                params, f"no image payload in response: keys={list(data.keys())}"
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
        return 0.03

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=15),
        reraise=True,
    )
    def _post(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {settings.gemini_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120) as client:
            r = client.post(jiekou_url(self._path), json=payload, headers=headers)
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
