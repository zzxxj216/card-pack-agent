"""Tests for the 5 newly-wrapped image providers.

No live network — we verify:
  - They're registered
  - extract_image_payload handles multiple response shapes
  - estimate_cost returns a sensible number
  - Providers raise require_real_mode in mock mode (defensive check)
"""
from __future__ import annotations

import base64

import pytest


@pytest.mark.smoke
class TestNewProvidersRegistered:
    def test_all_new_providers_in_registry(self):
        from card_pack_agent.tools.image.base import ProviderName
        from card_pack_agent.tools.image.registry import list_providers

        names = list_providers()
        for p in [
            ProviderName.SEEDREAM_V45,
            ProviderName.FLUX_KONTEXT_MAX,
            ProviderName.MIDJOURNEY_TXT2IMG,
            ProviderName.JIEKOU_OPENAI,
            ProviderName.GEMINI_FLASH_IMAGE_EDIT,
        ]:
            assert p in names, f"{p} missing from registry"

    def test_get_provider_builds_each(self):
        from card_pack_agent.tools.image.base import ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        reset_instances()
        for p in [
            ProviderName.SEEDREAM_V45,
            ProviderName.FLUX_KONTEXT_MAX,
            ProviderName.MIDJOURNEY_TXT2IMG,
            ProviderName.JIEKOU_OPENAI,
            ProviderName.GEMINI_FLASH_IMAGE_EDIT,
        ]:
            provider = get_provider(p)
            assert provider.name == p


@pytest.mark.smoke
class TestResponseExtractor:
    def test_extract_url_openai_shape(self):
        from card_pack_agent.tools.image.providers._jiekou_common import extract_image_payload
        url, b = extract_image_payload({"data": [{"url": "https://example.com/a.png"}]})
        assert url == "https://example.com/a.png"
        assert b is None

    def test_extract_b64_openai_shape(self):
        from card_pack_agent.tools.image.providers._jiekou_common import extract_image_payload
        raw = base64.b64encode(b"\x89PNGfake").decode()
        url, b = extract_image_payload({"data": [{"b64_json": raw}]})
        assert url is None
        assert b == b"\x89PNGfake"

    def test_extract_b64_with_data_uri_prefix(self):
        from card_pack_agent.tools.image.providers._jiekou_common import extract_image_payload
        raw = base64.b64encode(b"hello").decode()
        url, b = extract_image_payload({"image_base64": f"data:image/png;base64,{raw}"})
        assert b == b"hello"

    def test_extract_top_level_image_url(self):
        from card_pack_agent.tools.image.providers._jiekou_common import extract_image_payload
        url, b = extract_image_payload({"image_url": "https://cdn/x.png"})
        assert url == "https://cdn/x.png"

    def test_extract_returns_nones_on_empty(self):
        from card_pack_agent.tools.image.providers._jiekou_common import extract_image_payload
        url, b = extract_image_payload({"status": "pending"})
        assert url is None
        assert b is None

    def test_extract_task_id_variants(self):
        from card_pack_agent.tools.image.providers._jiekou_common import extract_task_id
        assert extract_task_id({"id": "abc123"}) == "abc123"
        assert extract_task_id({"task_id": "def456"}) == "def456"
        assert extract_task_id({"data": {"taskId": "xyz"}}) == "xyz"


@pytest.mark.smoke
class TestEstimateCost:
    def test_each_provider_returns_positive_cost(self):
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        reset_instances()
        params = GenerationParams(prompt="hello", aspect_ratio="9:16")
        for p in [
            ProviderName.SEEDREAM_V45,
            ProviderName.FLUX_KONTEXT_MAX,
            ProviderName.MIDJOURNEY_TXT2IMG,
            ProviderName.JIEKOU_OPENAI,
            ProviderName.GEMINI_FLASH_IMAGE_EDIT,
        ]:
            provider = get_provider(p)
            cost = provider.estimate_cost(params)
            assert cost > 0
            assert cost < 1.0

    def test_cost_override_via_extra(self):
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        reset_instances()
        params = GenerationParams(prompt="hello", extra={"cost_override": 0.123})
        provider = get_provider(ProviderName.SEEDREAM_V45)
        assert provider.estimate_cost(params) == pytest.approx(0.123)


@pytest.mark.smoke
class TestMockModeGuard:
    def test_all_new_providers_block_in_mock_mode(self, monkeypatch):
        """Each provider must refuse to run real in mock mode."""
        from card_pack_agent.config import AppMode, settings
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        reset_instances()
        monkeypatch.setattr(settings, "app_mode", AppMode.MOCK)

        params = GenerationParams(prompt="x", aspect_ratio="9:16")
        for p in [
            ProviderName.SEEDREAM_V45,
            ProviderName.FLUX_KONTEXT_MAX,
            ProviderName.MIDJOURNEY_TXT2IMG,
            ProviderName.JIEKOU_OPENAI,
            ProviderName.GEMINI_FLASH_IMAGE_EDIT,
        ]:
            provider = get_provider(p)
            with pytest.raises(RuntimeError, match="APP_MODE"):
                provider.generate(params)


@pytest.mark.smoke
class TestMjTextComposer:
    def test_appends_ar_flag(self):
        from card_pack_agent.tools.image.base import GenerationParams
        from card_pack_agent.tools.image.providers.midjourney import _compose_mj_text
        params = GenerationParams(prompt="a cat on a bus", aspect_ratio="9:16")
        text = _compose_mj_text(params)
        assert "a cat on a bus" in text
        assert "--ar 9:16" in text

    def test_respects_existing_ar_flag(self):
        from card_pack_agent.tools.image.base import GenerationParams
        from card_pack_agent.tools.image.providers.midjourney import _compose_mj_text
        params = GenerationParams(prompt="test --ar 1:1", aspect_ratio="9:16")
        text = _compose_mj_text(params)
        # Should not double-append
        assert text.count("--ar") == 1
