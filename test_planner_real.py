"""Step 2: Planner 单独测试 — 真 API 调用"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from card_pack_agent.agents.planner import plan
from card_pack_agent.schemas import StrategyDoc, ClarificationRequest, TopicInput

print("=== Calling Planner (real API) ===")
try:
    result, meta = plan(
        TopicInput(raw_topic="中秋节 独在异乡的年轻人"),
        hint_l1="festival",
        hint_l2="resonance_healing",
    )
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")
    sys.exit(1)

print(f"\n=== 1. 返回类型: {type(result).__name__} ===")
if isinstance(result, StrategyDoc):
    print("  -> 成功返回 StrategyDoc")
elif isinstance(result, ClarificationRequest):
    print(f"  -> 要求澄清: {result.questions}")
else:
    print(f"  -> 未知类型: {result}")

print(f"\n=== 2. attempts: {meta.attempts} ===")
if meta.attempts > 1:
    print("  ⚠ 触发了重试，检查 ./logs/llm_failures/")

print(f"\n=== 3. cost: ${meta.estimated_cost_usd:.4f} ===")
print(f"  input_tokens={meta.input_tokens}, output_tokens={meta.output_tokens}")

print(f"\n=== 4. Strategy Doc 内容 ===")
if isinstance(result, StrategyDoc):
    print(result.model_dump_json(indent=2, ensure_ascii=False))
else:
    print("(非 StrategyDoc，跳过)")

print(f"\n=== Meta ===")
print(meta.as_dict())
