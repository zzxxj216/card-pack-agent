"""Smoke tests for the image subsystem.

All run in mock mode — no network, no API key needed.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
class TestImageProviders:
    def test_mock_provider_roundtrip(self, tmp_path, monkeypatch):
        """Mock provider generates, returns an ImageResult with a valid local path."""
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        provider = get_provider(ProviderName.MOCK)
        params = GenerationParams(
            prompt="a single warm teacup on a windowsill",
            negative_prompt="text, watermark",
            aspect_ratio="9:16",
        )
        result = provider.generate(params)

        assert result.ok
        assert result.provider == ProviderName.MOCK
        assert result.image_url
        assert result.cost_usd == 0.0
        assert result.latency_ms >= 0

        # File was actually written
        from pathlib import Path
        assert Path(result.image_url).exists()

    def test_registry_lists_all_providers(self):
        from card_pack_agent.tools.image.base import ProviderName
        from card_pack_agent.tools.image.registry import list_providers

        providers = list_providers()
        assert ProviderName.MOCK in providers
        assert ProviderName.FLUX_PRO in providers
        assert ProviderName.OPENAI_IMAGE in providers

    def test_unknown_provider_raises(self):
        from card_pack_agent.tools.image.registry import get_provider

        with pytest.raises(ValueError, match="unknown provider"):
            get_provider("nonexistent_provider")


@pytest.mark.smoke
class TestImageCache:
    def test_cache_miss_then_hit(self, tmp_path, monkeypatch):
        """After a successful generate, second call should hit cache."""
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image import cache
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        provider = get_provider(ProviderName.MOCK)
        params = GenerationParams(prompt="cache test prompt", aspect_ratio="9:16")

        # Miss
        assert cache.get(provider.name, provider.model, params) is None

        # Generate and store
        result = provider.generate(params)
        assert result.ok
        cache.put(result, params)

        # Hit
        hit = cache.get(provider.name, provider.model, params)
        assert hit is not None
        assert hit.image_id == result.image_id
        assert hit.image_url == result.image_url

    def test_cache_key_depends_on_params(self, tmp_path, monkeypatch):
        """Different params → different cache entries."""
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image import cache
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import get_provider, reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        provider = get_provider(ProviderName.MOCK)
        p1 = GenerationParams(prompt="same prompt", seed=1)
        p2 = GenerationParams(prompt="same prompt", seed=2)

        r1 = provider.generate(p1)
        cache.put(r1, p1)

        # p2 differs in seed → should NOT hit p1's cache entry
        assert cache.get(provider.name, provider.model, p2) is None
        # But p1 still hits
        assert cache.get(provider.name, provider.model, p1) is not None


@pytest.mark.smoke
class TestGenerateHighLevel:
    def test_generate_one(self, tmp_path, monkeypatch):
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image import generate_one
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        params = GenerationParams(prompt="hello world")
        result = generate_one(params, provider=ProviderName.MOCK)
        assert result.ok
        assert result.provider == ProviderName.MOCK

    def test_generate_batch_returns_map_by_position(self, tmp_path, monkeypatch):
        from card_pack_agent.config import settings
        from card_pack_agent.schemas import CardPrompt, SegmentRole
        from card_pack_agent.tools.image import generate_batch
        from card_pack_agent.tools.image.base import ProviderName
        from card_pack_agent.tools.image.registry import reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        cards = [
            CardPrompt(
                position=i, segment=SegmentRole.HOOK,
                prompt=f"card {i}", negative_prompt="text",
            )
            for i in range(1, 6)
        ]
        results = generate_batch(cards, provider=ProviderName.MOCK, concurrency=2)

        assert set(results.keys()) == {1, 2, 3, 4, 5}
        assert all(r.ok for r in results.values())
        assert all(r.provider == ProviderName.MOCK for r in results.values())

    def test_generate_compare_multiple_providers(self, tmp_path, monkeypatch):
        """Compare must return one result per provider, each OK."""
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image import generate_compare
        from card_pack_agent.tools.image.base import GenerationParams, ProviderName
        from card_pack_agent.tools.image.registry import reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        params = GenerationParams(prompt="compare test")
        # Only mock is safe to call without network
        results = generate_compare(params, providers=[ProviderName.MOCK])
        assert "mock" in results
        assert results["mock"].ok


@pytest.mark.smoke
class TestBench:
    def test_bench_end_to_end_mock(self, tmp_path, monkeypatch):
        """Bench 2 cases × 1 provider (mock). Verify output artifacts exist."""
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image.base import ProviderName
        from card_pack_agent.tools.image.bench import BenchCase, run_bench
        from card_pack_agent.tools.image.registry import reset_instances

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        cases = [
            BenchCase(prompt_id="t1", prompt="case one", aspect_ratio="9:16"),
            BenchCase(prompt_id="t2", prompt="case two", aspect_ratio="9:16"),
        ]
        out = tmp_path / "bench_out"

        results, summaries = run_bench(
            cases=cases,
            providers=[ProviderName.MOCK],
            output_dir=out,
            with_judge=True,  # vision_judge returns canned score in mock mode
        )

        # Shape
        assert len(results) == 2
        assert len(summaries) == 1
        assert summaries[0].provider == "mock"
        assert summaries[0].n_ok == 2

        # Artifacts on disk
        assert (out / "results.jsonl").exists()
        assert (out / "summary.json").exists()
        assert (out / "summary.md").exists()

        md = (out / "summary.md").read_text(encoding="utf-8")
        assert "Image Provider Bench" in md
        assert "`mock`" in md


@pytest.mark.smoke
class TestLegacyShim:
    def test_legacy_generate_image_still_works(self, tmp_path, monkeypatch):
        """Old orchestrator code path uses tools.image_gen shim — must still work."""
        from card_pack_agent.config import settings
        from card_pack_agent.schemas import CardPrompt, SegmentRole
        from card_pack_agent.tools.image.registry import reset_instances
        from card_pack_agent.tools.image_gen import generate_batch, generate_image

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        monkeypatch.setattr(settings, "image_provider", settings.image_provider.MOCK)
        reset_instances()

        card = CardPrompt(
            position=1, segment=SegmentRole.HOOK,
            prompt="legacy path", negative_prompt="text",
        )
        url = generate_image(card)
        assert url  # non-empty string path

        batch_urls = generate_batch([card])
        assert 1 in batch_urls
        assert batch_urls[1]


@pytest.mark.smoke
class TestVisionJudgeMock:
    def test_judge_returns_canned_score_in_mock(self, tmp_path, monkeypatch):
        from card_pack_agent.config import settings
        from card_pack_agent.tools.image.base import (
            GenerationParams, ProviderName,
        )
        from card_pack_agent.tools.image.registry import get_provider, reset_instances
        from card_pack_agent.tools.image.vision_judge import JudgeInput, judge_image

        monkeypatch.setattr(settings, "storage_local_path", tmp_path)
        reset_instances()

        provider = get_provider(ProviderName.MOCK)
        params = GenerationParams(prompt="judge test")
        image = provider.generate(params)

        score = judge_image(JudgeInput(
            image_result=image,
            expected_prompt=params.prompt,
            style_anchor="film photography",
            palette=["#F5A623"],
        ))
        # Mock judge returns 4.0 across the board
        assert 1 <= score.overall <= 5
        assert 1 <= score.prompt_alignment <= 5
