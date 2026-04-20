"""FLUX 1 Kontext Max provider (via jiekou.ai async proxy).

Endpoint: POST https://api.jiekou.ai/v3/async/flux-1-kontext-max (submit)
          poll via ASYNC_STATUS_URL_CANDIDATES (see _jiekou_common.py)
Auth:     Bearer {JIEKOU_API_KEY}

Payload:
  prompt, images[], seed, guidance_scale, safety_tolerance, aspect_ratio

Defaults:
  - aspect_ratio = "9:16"
  - guidance_scale = 3.5 (FLUX Kontext typical)
  - safety_tolerance = "2" (moderate; 0=strict, 6=permissive — jiekou docs vary)
  - seed = None (provider picks)
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
    extract_task_id,
    jiekou_headers,
    jiekou_url,
    poll_async_result,
)

log = structlog.get_logger()


class FluxKontextMaxProvider(ImageProvider):
    name = ProviderName.FLUX_KONTEXT_MAX
    model = "flux-1-kontext-max"

    def __init__(self) -> None:
        self._submit_path = "/v3/async/flux-1-kontext-max"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"FluxKontextMaxProvider({self.model})")

        payload: dict[str, Any] = {
            "prompt": params.prompt,
            "aspect_ratio": params.aspect_ratio or "9:16",
            "guidance_scale": params.guidance if params.guidance is not None else 3.5,
            "safety_tolerance": str(params.extra.get("safety_tolerance", "2")),
            "images": params.extra.get("images", []),  # reference images if any
        }
        if params.seed is not None:
            payload["seed"] = int(params.seed)

        t0 = time.monotonic()
        try:
            submit = self._submit(payload)
            task_id = extract_task_id(submit)
            log.info("flux_kontext.submitted", task_id=task_id)
            result = poll_async_result(task_id, endpoint_hint=self._submit_path)
        except Exception as e:
            log.error("flux_kontext.failed", error=str(e))
            return self._error_result(params, str(e))

        url, img_bytes = extract_image_payload(result)
        if img_bytes is None and url:
            try:
                img_bytes = download_bytes(url)
            except Exception as e:
                return self._error_result(params, f"image download failed: {e}")
        if img_bytes is None:
            return self._error_result(
                params, f"no image payload in final response: keys={list(result.keys())}"
            )

        local_path = write_image_bytes(img_bytes, self.name, ext="png")
        w, h = aspect_to_wh(params.aspect_ratio or "9:16")
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
            raw_response={"upstream_url": url, "task_id": extract_task_id(submit)},
        )

    def estimate_cost(self, params: GenerationParams) -> float:
        override = params.extra.get("cost_override")
        if isinstance(override, (int, float)):
            return float(override)
        return 0.08  # FLUX Kontext Max conservative estimate

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    def _submit(self, payload: dict) -> dict:
        with httpx.Client(timeout=60) as client:
            r = client.post(jiekou_url(self._submit_path), json=payload, headers=jiekou_headers())
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
