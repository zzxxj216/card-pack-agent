"""FLUX provider — 通过 Replicate 调用 black-forest-labs/flux-*。

为什么走 Replicate：不用自己部署，有官方维护的 endpoint，账单统一。
如果换到 fal.ai 或自托管，只需新增一个 class，保留相同 interface。

需要：
  IMAGE_API_KEY = <Replicate token>
  IMAGE_PROVIDER = flux_pro | flux_schnell

价格（2026-04，生产前请 web_search 确认）：
  flux-1.1-pro: ~$0.04 per image
  flux-schnell: ~$0.003 per image
"""
from __future__ import annotations

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


# Conservative price table (USD per image). Update via web search before prod use.
_PRICING = {
    "black-forest-labs/flux-1.1-pro": 0.04,
    "black-forest-labs/flux-pro":     0.055,
    "black-forest-labs/flux-schnell": 0.003,
    "black-forest-labs/flux-dev":     0.025,
}
_DEFAULT_PRICE = 0.04


def _aspect_to_dims(aspect: str) -> tuple[int, int]:
    """9:16 → 1088x1920 (FLUX 要求 16 整除)."""
    table = {
        "9:16":  (1088, 1920),
        "1:1":   (1024, 1024),
        "4:5":   (1088, 1360),
        "16:9":  (1920, 1088),
        "3:4":   (1088, 1440),
    }
    return table.get(aspect, (1088, 1920))


class FluxProvider(ImageProvider):
    name = ProviderName.FLUX_PRO  # overridden in __init__ if using schnell
    model = "black-forest-labs/flux-1.1-pro"

    def __init__(self, model: str = "black-forest-labs/flux-1.1-pro"):
        self.model = model
        self.name = (
            ProviderName.FLUX_SCHNELL if "schnell" in model
            else ProviderName.FLUX_PRO
        )
        self._base_url = "https://api.replicate.com/v1"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"FluxProvider({self.model})")
        if not settings.image_api_key:
            return self._error_result(params, "IMAGE_API_KEY missing")

        width, height = (
            (params.width, params.height)
            if params.width and params.height
            else _aspect_to_dims(params.aspect_ratio)
        )

        input_payload: dict = {
            "prompt": params.prompt,
            "aspect_ratio": params.aspect_ratio,
            "output_format": "png",
            "output_quality": 90,
        }
        if params.seed is not None:
            input_payload["seed"] = params.seed
        # FLUX-schnell ignores guidance/steps; pro accepts them
        if "schnell" not in self.model:
            if params.guidance is not None:
                input_payload["guidance"] = params.guidance
            if params.steps is not None:
                input_payload["num_inference_steps"] = params.steps

        t0 = time.monotonic()
        try:
            output_url = self._run_sync(input_payload)
        except Exception as e:
            log.error("flux.generate_failed", model=self.model, error=str(e))
            return self._error_result(params, str(e))

        # Download the image bytes
        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(output_url)
                r.raise_for_status()
                image_bytes = r.content
        except Exception as e:
            return self._error_result(params, f"image download failed: {e}")

        local_path = write_image_bytes(image_bytes, self.name, ext="png")

        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=self.model,
            image_url=str(local_path),
            image_bytes=None,
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=self.estimate_cost(params),
            width=width,
            height=height,
            raw_response={"replicate_url": output_url},
        )

    def estimate_cost(self, params: GenerationParams) -> float:  # noqa: ARG002
        return _PRICING.get(self.model, _DEFAULT_PRICE)

    # --- HTTP ---

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    def _run_sync(self, input_payload: dict) -> str:
        """Call Replicate /predictions, poll until done, return output URL."""
        headers = {
            "Authorization": f"Bearer {settings.image_api_key}",
            "Content-Type": "application/json",
            "Prefer": "wait",  # tell Replicate to wait synchronously
        }
        url = f"{self._base_url}/models/{self.model}/predictions"

        with httpx.Client(timeout=120) as client:
            # Start + wait-for-completion in one round trip
            r = client.post(url, json={"input": input_payload}, headers=headers)
            r.raise_for_status()
            data = r.json()

            status = data.get("status")
            if status == "succeeded":
                return self._extract_output(data)
            if status == "failed":
                raise RuntimeError(f"replicate failed: {data.get('error')}")

            # Fall back to polling if Prefer: wait didn't finish
            get_url = data.get("urls", {}).get("get")
            if not get_url:
                raise RuntimeError("replicate response missing get URL")

            for _ in range(60):
                time.sleep(2)
                p = client.get(get_url, headers=headers)
                p.raise_for_status()
                pd = p.json()
                status = pd.get("status")
                if status == "succeeded":
                    return self._extract_output(pd)
                if status in ("failed", "canceled"):
                    raise RuntimeError(f"replicate {status}: {pd.get('error')}")
            raise TimeoutError("replicate prediction did not complete in 2 minutes")

    @staticmethod
    def _extract_output(data: dict) -> str:
        out = data.get("output")
        if isinstance(out, list) and out:
            return out[0]
        if isinstance(out, str):
            return out
        raise RuntimeError(f"unexpected replicate output shape: {type(out)}")

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
