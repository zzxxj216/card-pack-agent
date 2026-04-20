"""Smoke tests — verify structure of knowledge base and modules.

Runs without any API calls. CI must pass this before running real eval.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.smoke
def test_knowledge_files_present():
    required = [
        "knowledge/taxonomy.md",
        "knowledge/global_style_guide.md",
        "knowledge/global_anti_patterns.md",
        "knowledge/metrics_calibration.md",
        "knowledge/failure_library.md",
        "knowledge/categories/festival.md",
        "knowledge/prompt_templates/planner.v1.md",
        "knowledge/prompt_templates/generator_cards.v1.md",
        "knowledge/prompt_templates/generator_script.v1.md",
        "knowledge/prompt_templates/reviewer.v1.md",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    assert not missing, f"missing: {missing}"


@pytest.mark.smoke
def test_knowledge_loader():
    from card_pack_agent.memory import knowledge
    assert "L1" in knowledge.taxonomy()
    assert len(knowledge.global_anti_patterns()) > 100
    # festival playbook must load and mention "festival" somewhere
    assert "festival" in knowledge.for_category("festival").lower()
    assert knowledge.for_category("nonexistent").startswith("# Category")


@pytest.mark.smoke
def test_config_mock_mode():
    from card_pack_agent.config import AppMode, settings
    assert settings.app_mode == AppMode.MOCK
    assert settings.is_mock


@pytest.mark.smoke
def test_schemas_import():
    from card_pack_agent.schemas import (
        CardPrompt, CaseRecord, EvaluatorReport, L1, L2,
        Pack, Script, StrategyDoc, Tier,
    )
    # Smoke: ensure enums have expected members
    assert L1.FESTIVAL.value == "festival"
    assert L2.RESONANCE_HEALING.value == "resonance_healing"
    assert Tier.VIRAL.value == "viral"
    _ = (CardPrompt, CaseRecord, EvaluatorReport, Pack, Script, StrategyDoc)


@pytest.mark.smoke
def test_llm_mock_response():
    from card_pack_agent.llm import LLMRole, llm
    resp = llm.complete(role=LLMRole.PLANNER, system="ignored", user="ignored")
    # Should be canned StrategyDoc JSON
    import json
    data = json.loads(resp)
    assert data["classification"]["l1"] == "festival"


@pytest.mark.smoke
def test_validate_knowledge_script_passes():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_knowledge.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, f"validate_knowledge failed:\n{result.stdout}\n{result.stderr}"
