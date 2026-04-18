"""通用 Replicate provider — 任何 Replicate 托管的 text-to-image 模型。

用法：设置 IMAGE_MODEL 为 model slug (owner/model) 或 slug:version。
支持 SDXL、社区 LoRA、自训模型等。

例子：
  IMAGE_MODEL=stability-ai/sdxl
  IMAGE_MODEL=stability-ai/sdxl:7762fd07...   # pinned version

与 FLUX provider 的区别：FluxProvider 专门针对 FLUX endpoint 的 input schema；
ReplicateProvider 是通用兜底，input 走 extra。
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

log = structlog.get_logger()


class ReplicateProvider(ImageProvider):
    name = ProviderName.REPLICATE
    model = ""  # 从 settings 读取

    def __init__(self, model: str | None = None):
        self.model = model or settings.image_model or "stability-ai/sdxl"
        self._base_url = "https://api.replicate.com/v1"

    def generate(self, params: GenerationParams) -> ImageResult:
        settings.require_real_mode(f"ReplicateProvider({self.model})")
        if not settings.image_api_key:
            return self._error_result(params, "IMAGE_API_KEY missing")

        # Generic SDXL-style input; model-specific tweaks go in params.extra
        input_payload: dict[str, Any] = {
            "prompt": params.prompt,
            "negative_prompt": params.negative_prompt,
            "width": params.width or 1024,
            "height": params.height or 1536,
        }
        if params.steps is not None:
            input_payload["num_inference_steps"] = params.steps
        if params.guidance is not None:
            input_payload["guidance_scale"] = params.guidance
        if params.seed is not None:
            input_payload["seed"] = params.seed
        # extra overrides take priority for model-specific fields
        input_payload.update(params.extra or {})

        t0 = time.monotonic()
        try:
            output_url = self._run_sync(input_payload)
        except Exception as e:
            log.error("replicate.generate_failed", model=self.model, error=str(e))
            return self._error_result(params, str(e))

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
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=self.estimate_cost(params),
            width=input_payload["width"],
            height=input_payload["height"],
            raw_response={"replicate_url": output_url, "model": self.model},
        )

    def estimate_cost(self, params: GenerationParams) -> float:  # noqa: ARG002
        # Replicate is GPU-time priced; we give a rough $0.02 default
        return 0.02

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=20),
        reraise=True,
    )
    def _run_sync(self, input_payload: dict) -> str:
        headers = {
            "Authorization": f"Bearer {settings.image_api_key}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        }
        # Handle both "owner/model" and "owner/model:version" syntax
        if ":" in self.model:
            endpoint = f"{self._base_url}/predictions"
            body = {
                "version": self.model.split(":", 1)[1],
                "input": input_payload,
            }
        else:
            endpoint = f"{self._base_url}/models/{self.model}/predictions"
            body = {"input": input_payload}

        with httpx.Client(timeout=120) as client:
            r = client.post(endpoint, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()

            status = data.get("status")
            if status == "succeeded":
                return self._extract_output(data)
            if status == "failed":
                raise RuntimeError(f"replicate failed: {data.get('error')}")

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
            raise TimeoutError("replicate did not complete in 2 minutes")

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
