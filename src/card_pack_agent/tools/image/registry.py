"""Provider 注册表。

运行时通过名字拿到 provider 实例，而不是硬编码 import。
新接一个模型：
  1. 在 providers/ 下新建一个类实现 ImageProvider
  2. 在本文件的 _BUILDERS 里加一行
"""
from __future__ import annotations

from typing import Callable

from .base import ImageProvider, ProviderName


_INSTANCES: dict[ProviderName, ImageProvider] = {}


def _build_mock() -> ImageProvider:
    from .providers.mock import MockProvider
    return MockProvider()


def _build_flux_pro() -> ImageProvider:
    from .providers.flux import FluxProvider
    return FluxProvider(model="black-forest-labs/flux-1.1-pro")


def _build_flux_schnell() -> ImageProvider:
    from .providers.flux import FluxProvider
    return FluxProvider(model="black-forest-labs/flux-schnell")


def _build_openai_image() -> ImageProvider:
    from .providers.openai_image import OpenAIImageProvider
    return OpenAIImageProvider()


def _build_replicate() -> ImageProvider:
    from .providers.replicate import ReplicateProvider
    return ReplicateProvider()


_BUILDERS: dict[ProviderName, Callable[[], ImageProvider]] = {
    ProviderName.MOCK: _build_mock,
    ProviderName.FLUX_PRO: _build_flux_pro,
    ProviderName.FLUX_SCHNELL: _build_flux_schnell,
    ProviderName.OPENAI_IMAGE: _build_openai_image,
    ProviderName.REPLICATE: _build_replicate,
}


def get_provider(name: ProviderName | str) -> ImageProvider:
    """Lazy-built singleton per provider."""
    if isinstance(name, str):
        try:
            name = ProviderName(name)
        except ValueError:
            raise ValueError(f"unknown provider: {name}") from None
    if name not in _INSTANCES:
        builder = _BUILDERS.get(name)
        if builder is None:
            raise ValueError(f"unknown provider: {name}")
        _INSTANCES[name] = builder()
    return _INSTANCES[name]


def list_providers() -> list[ProviderName]:
    return list(_BUILDERS.keys())


def reset_instances() -> None:
    """For tests. Clears cached provider instances."""
    _INSTANCES.clear()
