"""OpenAI-compatible images endpoint via jiekou.ai proxy.

Endpoint: POST https://api.jiekou.ai/v1/images/generations (sync)
Auth:     Bearer {JIEKOU_API_KEY}

Payload (OpenAI-compat):
  model, prompt, quality, n, size

Default model: "gpt-image-1". Override via GenerationParams.extra["model"].
Size: nearest fixed to aspect_ratio (same table as OpenAIImageProvider).
"""
from __future__ import annotations

import base64
import time

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
    download_bytes,
    extract_image_payload,
    jiekou_headers,
    jiekou_url,
)

log = structlog.get_logger()


def _nearest_size(aspect_ratio: str) -> str:
    table = {
        "9:16": "1024x1536",
        "1:1":  "1024x1024",
        "16:9": "1536x1024",
        "4:5":  "1024x1536",
        "3:4":  "1024x1536",
    }
    return table.get(aspect_ratio, "1024x1536")


_PRICING = {
    ("gpt-image-1.5", "1024x1024", "low"):      0.020,
    ("gpt-image-1.5", "1024x1024", "standard"):  0.040,
    ("gpt-image-1.5", "1024x1536", "low"):       0.030,
    ("gpt-image-1.5", "1024x1536", "standard"):  0.060,
    ("gpt-image-1.5", "1024x1024", "high"):      0.19,
    ("gpt-image-1.5", "1024x1536", "high"):      0.25,
}


class JiekouOpenAIProvider(ImageProvider):
    name = ProviderName.JIEKOU_OPENAI
    model = "gpt-image-1.5"

    def __init__(self, model: str = "gpt-image-1.5", quality: str = "low") -> None:
        self.model = model
        self.quality = quality
        self._path = "/v1/images/generations"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"JiekouOpenAIProvider({self.model})")

        size = _nearest_size(params.aspect_ratio or "9:16")
        model = params.extra.get("model", self.model)
        quality = params.extra.get("quality", self.quality)

        payload = {
            "model": model,
            "prompt": params.prompt,
            "size": size,
            "quality": quality,
            "n": 1,
        }

        t0 = time.monotonic()
        try:
            data = self._post(payload)
        except Exception as e:
            log.error("jiekou_openai.generate_failed", error=str(e))
            return self._error_result(params, str(e))

        # OpenAI-compat usually returns data[0].b64_json OR data[0].url
        url, img_bytes = extract_image_payload(data)
        if img_bytes is None and url:
            try:
                img_bytes = download_bytes(url)
            except Exception as e:
                return self._error_result(params, f"image download failed: {e}")
        # OpenAI historical: data[0].b64_json (caught by extract_image_payload)
        if img_bytes is None:
            # Last-resort: try data[0].b64_json explicitly
            items = data.get("data")
            if isinstance(items, list) and items:
                b64 = items[0].get("b64_json")
                if b64:
                    try:
                        img_bytes = base64.b64decode(b64)
                    except Exception:
                        pass
        if img_bytes is None:
            return self._error_result(
                params, f"no image payload in response: keys={list(data.keys())}"
            )

        local_path = write_image_bytes(img_bytes, self.name, ext="png")
        w, h = (int(x) for x in size.split("x"))
        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=model,
            image_url=str(local_path),
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=self.estimate_cost(params),
            width=w,
            height=h,
            raw_response={"size": size, "quality": quality, "model": model},
        )

    def estimate_cost(self, params: GenerationParams) -> float:
        override = params.extra.get("cost_override")
        if isinstance(override, (int, float)):
            return float(override)
        size = _nearest_size(params.aspect_ratio or "9:16")
        quality = params.extra.get("quality", self.quality)
        model = params.extra.get("model", self.model)
        return _PRICING.get((model, size, quality), 0.08)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
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
