"""Image generation subsystem.

入口：
  generate_one / generate_batch / generate_compare  → tools/image/generate.py
  run_bench                                          → tools/image/bench.py
  judge_image                                        → tools/image/vision_judge.py

扩展新 provider：
  1. providers/<name>.py — 实现 ImageProvider
  2. registry.py _BUILDERS — 加一行
  3. base.ProviderName enum — 加一个值
"""
from .base import (
    GenerationParams,
    ImageProvider,
    ImageResult,
    ProviderName,
)
from .generate import generate_batch, generate_compare, generate_one
from .registry import get_provider, list_providers

__all__ = [
    "GenerationParams",
    "ImageProvider",
    "ImageResult",
    "ProviderName",
    "generate_batch",
    "generate_compare",
    "generate_one",
    "get_provider",
    "list_providers",
]
