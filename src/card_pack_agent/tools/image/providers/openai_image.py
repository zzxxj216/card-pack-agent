"""OpenAI gpt-image-1 provider。

需要单独的 OPENAI_API_KEY（配到 .env 里 IMAGE_API_KEY 或另起变量）。
为保持 .env 精简，我们约定 provider=openai_image 时 IMAGE_API_KEY 就是 OpenAI key。

价格参考（2026-04，用前请 web_search 核实）：
  gpt-image-1 standard 1024x1024: ~$0.04
  gpt-image-1 high quality 1024x1024: ~$0.19
  1024x1536 (9:16-ish): price varies
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

log = structlog.get_logger()


# Size table: OpenAI image API supports fixed sizes only
# Pick nearest to requested aspect ratio
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
    ("gpt-image-1", "1024x1024", "standard"): 0.040,
    ("gpt-image-1", "1024x1536", "standard"): 0.060,
    ("gpt-image-1", "1024x1024", "high"):     0.19,
    ("gpt-image-1", "1024x1536", "high"):     0.25,
}


class OpenAIImageProvider(ImageProvider):
    name = ProviderName.OPENAI_IMAGE
    model = "gpt-image-1"

    def __init__(self, quality: str = "standard"):
        self.quality = quality   # "standard" | "high"
        self._base_url = "https://api.openai.com/v1"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"OpenAIImageProvider({self.model})")
        if not settings.image_api_key:
            return self._error_result(params, "IMAGE_API_KEY missing")

        size = _nearest_size(params.aspect_ratio)

        payload = {
            "model": self.model,
            "prompt": params.prompt,
            "size": size,
            "quality": self.quality,
            "n": 1,
        }

        t0 = time.monotonic()
        try:
            b64_data = self._call_api(payload)
        except Exception as e:
            log.error("openai_image.generate_failed", error=str(e))
            return self._error_result(params, str(e))

        image_bytes = base64.b64decode(b64_data)
        local_path = write_image_bytes(image_bytes, self.name, ext="png")

        width, height = (int(x) for x in size.split("x"))
        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=self.model,
            image_url=str(local_path),
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=self.estimate_cost(params),
            width=width,
            height=height,
            raw_response={"size": size, "quality": self.quality},
        )

    def estimate_cost(self, params: GenerationParams) -> float:
        size = _nearest_size(params.aspect_ratio)
        return _PRICING.get((self.model, size, self.quality), 0.08)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    def _call_api(self, payload: dict) -> str:
        headers = {
            "Authorization": f"Bearer {settings.image_api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{self._base_url}/images/generations",
                            json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            items = data.get("data", [])
            if not items:
                raise RuntimeError(f"no image in response: {data}")
            b64 = items[0].get("b64_json")
            if not b64:
                raise RuntimeError("response missing b64_json field")
            return b64

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
