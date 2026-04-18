"""Legacy entry point. Forwards to tools.image.*.

Keeps orchestrator.py and any old callers working unchanged.
Prefer importing from card_pack_agent.tools.image directly in new code.
"""
from __future__ import annotations

from ..schemas import CardPrompt
from .image import generate_batch as _gen_batch
from .image.base import ProviderName


def generate_image(prompt: CardPrompt) -> str:
    """Legacy: single-card generation, returns URL/path.

    New code should use tools.image.generate_one(GenerationParams).
    """
    from ..config import settings
    from .image import generate_one
    from .image.generate import card_to_params

    params = card_to_params(prompt)
    result = generate_one(params, provider=settings.image_provider)
    return result.image_url if result.ok else ""


def generate_batch(prompts: list[CardPrompt]) -> dict[int, str]:
    """Legacy: batch, returns {position: URL}.

    New code should use tools.image.generate_batch which returns {position: ImageResult}.
    """
    from ..config import settings
    results = _gen_batch(prompts, provider=settings.image_provider)
    return {pos: r.image_url if r.ok else "" for pos, r in results.items()}


__all__ = ["generate_image", "generate_batch", "ProviderName"]
