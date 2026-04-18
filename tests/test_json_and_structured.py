"""Unit tests for json_utils and structured_output."""
from __future__ import annotations

import pytest


@pytest.mark.smoke
class TestJsonRobust:
    def test_plain_json(self):
        from card_pack_agent.json_utils import parse_json_robust
        assert parse_json_robust('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        from card_pack_agent.json_utils import parse_json_robust
        assert parse_json_robust('```json\n{"a": 1}\n```') == {"a": 1}
        assert parse_json_robust('```\n{"a": 1}\n```') == {"a": 1}

    def test_preamble(self):
        from card_pack_agent.json_utils import parse_json_robust
        text = 'Here is the JSON:\n{"a": 1, "b": "x"}\nLet me know if...'
        assert parse_json_robust(text) == {"a": 1, "b": "x"}

    def test_trailing_comma(self):
        from card_pack_agent.json_utils import parse_json_robust
        text = '{"a": 1, "b": [1, 2, 3,],}'
        assert parse_json_robust(text) == {"a": 1, "b": [1, 2, 3]}

    def test_truncated_object_repaired(self):
        """Simulated max_tokens cutoff mid-output — repair should close braces."""
        from card_pack_agent.json_utils import parse_json_robust
        text = '{"outer": {"inner": [1, 2, 3'
        result = parse_json_robust(text)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_nested_array(self):
        from card_pack_agent.json_utils import parse_json_robust
        text = 'preamble\n```json\n[{"a": 1}, {"a": 2}]\n```'
        assert parse_json_robust(text) == [{"a": 1}, {"a": 2}]

    def test_garbage_raises(self):
        from card_pack_agent.json_utils import JSONRepairError, parse_json_robust
        with pytest.raises(JSONRepairError):
            parse_json_robust("not json at all, just prose")

    def test_empty_raises(self):
        from card_pack_agent.json_utils import JSONRepairError, parse_json_robust
        with pytest.raises(JSONRepairError):
            parse_json_robust("")

    def test_json_inside_prose_extracted(self):
        from card_pack_agent.json_utils import parse_json_robust
        text = (
            'I think the answer is:\n\n'
            '{"field": "value", "nested": {"x": [1,2]}}\n\n'
            'Hope that helps.'
        )
        assert parse_json_robust(text) == {"field": "value", "nested": {"x": [1, 2]}}


@pytest.mark.smoke
class TestStructuredCallMockMode:
    """Structured call roundtrip in mock mode. Verifies schema validation and cost tracking."""

    def test_planner_roundtrip(self):
        from card_pack_agent.agents.planner import plan
        from card_pack_agent.schemas import StrategyDoc, TopicInput

        result, meta = plan(
            TopicInput(raw_topic="中秋节 独自一人"),
            hint_l1="festival",
            hint_l2="resonance_healing",
        )
        assert isinstance(result, StrategyDoc)
        assert meta.attempts >= 1
        assert meta.role == "planner"

    def test_batched_cards_split_correctly(self):
        """12-card batches should split 50 into 5 batches."""
        from card_pack_agent.agents.generator_cards_batched import _plan_batches
        from card_pack_agent.schemas import Segment, SegmentRole

        segments = [
            Segment(range=(1, 3), role=SegmentRole.HOOK),
            Segment(range=(4, 15), role=SegmentRole.SETUP),
            Segment(range=(16, 35), role=SegmentRole.DEVELOPMENT),
            Segment(range=(36, 45), role=SegmentRole.TURN),
            Segment(range=(46, 50), role=SegmentRole.CLOSE),
        ]
        batches = _plan_batches(segments, batch_size=12)

        # Each batch respects batch_size
        for start, end, _role in batches:
            assert end - start + 1 <= 12

        # Coverage: all positions 1..50 exactly once
        covered = []
        for start, end, _ in batches:
            covered.extend(range(start, end + 1))
        assert sorted(covered) == list(range(1, 51))

    def test_cost_summary_accumulates(self):
        from card_pack_agent.orchestrator import run
        from card_pack_agent.schemas import TopicInput

        result = run(
            TopicInput(raw_topic="中秋节"),
            hint_l1="festival",
            hint_l2="resonance_healing",
            generate_images=False,
            persist=False,
        )
        # In mock mode costs are 0 but structure should be present
        assert result.cost is not None
        assert result.cost.total_input_tokens >= 0
        # At minimum planner + generator cards batches + script + judge should have run
        assert "planner" in result.cost.per_role or "generator" in result.cost.per_role
