"""图像生成的高层 API。

三个入口：

  generate_one(params, provider=...)        -> ImageResult
      单 provider 单张，走缓存

  generate_batch(prompts_with_params, provider=...)  -> list[ImageResult]
      单 provider 并发批量，走缓存

  generate_compare(params, providers=[...]) -> dict[ProviderName, ImageResult]
      多 provider 同一 prompt，用于 A/B 对比评测

所有调用都走 cache。评测脚本可以传 use_cache=False 强制重跑。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import structlog

from ...config import settings
from ...schemas import CardPrompt
from . import cache
from .base import GenerationParams, ImageResult, ProviderName
from .registry import get_provider

log = structlog.get_logger()


def card_to_params(card: CardPrompt, aspect: str = "9:16") -> GenerationParams:
    """Adapter: CardPrompt → GenerationParams."""
    return GenerationParams(
        prompt=card.prompt,
        negative_prompt=card.negative_prompt or "text, watermark, logo, typography",
        aspect_ratio=aspect,
        extra={"card_position": card.position},
    )


def generate_one(
    params: GenerationParams,
    provider: ProviderName | str | None = None,
    use_cache: bool = True,
) -> ImageResult:
    """Single-shot generation through a single provider, cached."""
    p_name = provider or settings.image_provider
    if isinstance(p_name, str):
        p_name = ProviderName(p_name)

    p = get_provider(p_name)

    if use_cache:
        hit = cache.get(p.name, p.model, params)
        if hit is not None:
            log.info("image.cache_hit", provider=p.name.value, model=p.model)
            return hit

    result = p.generate(params)
    if result.ok and use_cache:
        cache.put(result, params)
    return result


def generate_batch(
    cards: list[CardPrompt],
    provider: ProviderName | str | None = None,
    use_cache: bool = True,
    concurrency: int | None = None,
) -> dict[int, ImageResult]:
    """Generate images for a batch of cards concurrently.

    :returns: mapping position → ImageResult
    """
    concurrency = concurrency or settings.image_concurrency
    results: dict[int, ImageResult] = {}

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(generate_one, card_to_params(c), provider, use_cache): c
            for c in cards
        }
        for fut in as_completed(futures):
            card = futures[fut]
            try:
                results[card.position] = fut.result()
            except Exception as e:
                log.error("image.batch_item_failed",
                          position=card.position, error=str(e))
                # Build an error result so downstream can detect failure
                params = card_to_params(card)
                results[card.position] = ImageResult(
                    image_id="",
                    provider=ProviderName(provider or settings.image_provider)
                    if provider else ProviderName.MOCK,
                    model="",
                    image_url="",
                    params_fingerprint=params.fingerprint(),
                    prompt=params.prompt,
                    error=str(e),
                )

    # Report batch stats
    ok_count = sum(1 for r in results.values() if r.ok)
    total_cost = sum(r.cost_usd for r in results.values())
    log.info("image.batch_done",
             total=len(cards), ok=ok_count,
             failed=len(cards) - ok_count,
             total_cost_usd=round(total_cost, 4))

    return results


def generate_compare(
    params: GenerationParams,
    providers: list[ProviderName | str],
    use_cache: bool = True,
) -> dict[str, ImageResult]:
    """Same prompt, N providers, return side-by-side results for A/B evaluation."""
    results: dict[str, ImageResult] = {}

    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        futures = {
            pool.submit(generate_one, params, p, use_cache): p
            for p in providers
        }
        for fut in as_completed(futures):
            p = futures[fut]
            p_str = p.value if isinstance(p, ProviderName) else str(p)
            try:
                results[p_str] = fut.result()
            except Exception as e:
                log.error("image.compare_item_failed",
                          provider=p_str, error=str(e))
                results[p_str] = ImageResult(
                    image_id="",
                    provider=ProviderName(p_str),
                    model="",
                    image_url="",
                    params_fingerprint=params.fingerprint(),
                    prompt=params.prompt,
                    error=str(e),
                )

    return results
