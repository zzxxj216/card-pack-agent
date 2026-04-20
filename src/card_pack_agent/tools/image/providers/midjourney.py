"""Midjourney txt2img provider (via jiekou.ai async proxy).

Endpoint: POST https://api.jiekou.ai/v3/async/mj-txt2img (submit) → poll
Auth:     Bearer {JIEKOU_API_KEY}

Payload (per jiekou snippet): { "text": "<prompt with MJ params appended>" }

MJ params are embedded in the text (--ar 9:16 --v 6 --style raw etc.),
rather than as separate JSON fields. We append sensible defaults when missing.
"""
from __future__ import annotations

import re
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
    aspect_to_wh,
    download_bytes,
    extract_image_payload,
    extract_task_id,
    jiekou_headers,
    jiekou_url,
    poll_async_result,
)

log = structlog.get_logger()


def _compose_mj_text(params: GenerationParams) -> str:
    text = params.prompt.strip()
    # Append --ar if not present
    if not re.search(r"--ar\s+\d+:\d+", text):
        text += f" --ar {params.aspect_ratio or '9:16'}"
    if params.negative_prompt and "--no" not in text:
        text += f" --no {params.negative_prompt}"
    if params.seed is not None and "--seed" not in text:
        text += f" --seed {int(params.seed)}"
    # Let operator pass extra raw MJ flags via extra["mj_flags"]
    extra_flags = params.extra.get("mj_flags")
    if isinstance(extra_flags, str) and extra_flags.strip():
        text += " " + extra_flags.strip()
    return text


class MidjourneyProvider(ImageProvider):
    name = ProviderName.MIDJOURNEY_TXT2IMG
    model = "midjourney"

    def __init__(self) -> None:
        self._submit_path = "/v3/async/mj-txt2img"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"MidjourneyProvider({self.model})")

        text = _compose_mj_text(params)
        payload = {"text": text}

        t0 = time.monotonic()
        try:
            submit = self._submit(payload)
            task_id = extract_task_id(submit)
            log.info("midjourney.submitted", task_id=task_id)
            result = poll_async_result(task_id, endpoint_hint=self._submit_path)
        except Exception as e:
            log.error("midjourney.failed", error=str(e))
            return self._error_result(params, str(e))

        url, img_bytes = extract_image_payload(result)
        if img_bytes is None and url:
            try:
                img_bytes = download_bytes(url)
            except Exception as e:
                return self._error_result(params, f"image download failed: {e}")
        if img_bytes is None:
            return self._error_result(
                params, f"no image in final response: keys={list(result.keys())}"
            )

        local_path = write_image_bytes(img_bytes, self.name, ext="png")
        w, h = aspect_to_wh(params.aspect_ratio or "9:16")
        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=self.model,
            image_url=str(local_path),
            params_fingerprint=params.fingerprint(),
            prompt=text,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=self.estimate_cost(params),
            width=w,
            height=h,
            raw_response={"upstream_url": url, "text": text},
        )

    def estimate_cost(self, params: GenerationParams) -> float:
        override = params.extra.get("cost_override")
        if isinstance(override, (int, float)):
            return float(override)
        # MJ via jiekou proxy — conservative estimate for one "fast" grid→upscale
        return 0.10

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
