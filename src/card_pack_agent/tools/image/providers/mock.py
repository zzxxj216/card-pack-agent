"""Mock provider — 零成本、零延迟，用于 APP_MODE=mock 下的 smoke 测试。

产出的是一个小 txt 文件（含 prompt 内容），image_url 指向它。
真实 pipeline 的调用方不应该区分 mock 和真模型，所以 ImageResult 结构一致。
"""
from __future__ import annotations

import time

from ..base import (
    GenerationParams,
    ImageProvider,
    ImageResult,
    ProviderName,
    make_image_id,
    write_image_bytes,
)


class MockProvider(ImageProvider):
    name = ProviderName.MOCK
    model = "mock-v0"

    def generate(self, params: GenerationParams) -> ImageResult:
        t0 = time.monotonic()
        # Emit a tiny placeholder so downstream file-ops have something to work with
        placeholder = (
            f"[MOCK IMAGE]\n"
            f"provider: {self.name.value}\n"
            f"model: {self.model}\n"
            f"prompt: {params.prompt}\n"
            f"negative: {params.negative_prompt}\n"
            f"fingerprint: {params.fingerprint()}\n"
        ).encode("utf-8")
        path = write_image_bytes(placeholder, self.name, ext="txt")

        return ImageResult(
            image_id=make_image_id(),
            provider=self.name,
            model=self.model,
            image_url=str(path),
            params_fingerprint=params.fingerprint(),
            prompt=params.prompt,
            latency_ms=int((time.monotonic() - t0) * 1000),
            cost_usd=0.0,
            width=1080,
            height=1920,
            raw_response={"mock": True},
        )

    def estimate_cost(self, params: GenerationParams) -> float:  # noqa: ARG002
        return 0.0
