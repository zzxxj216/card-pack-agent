"""Step 3: Generator 分批跑一次 — 真 API"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from card_pack_agent.agents.planner import plan
from card_pack_agent.agents.generator import generate_cards
from card_pack_agent.schemas import TopicInput

print("=== Step 3a: Planner ===")
strategy, plan_meta = plan(
    TopicInput(raw_topic="中秋节 独在异乡的年轻人"),
    hint_l1="festival",
    hint_l2="resonance_healing",
)
print(f"Planner done: attempts={plan_meta.attempts}, cost=${plan_meta.estimated_cost_usd:.4f}")

print("\n=== Step 3b: Generator (cards) ===")
cards, cards_meta = generate_cards(strategy)

print(f"\n=== 1. 卡贴数量: {len(cards)} ===")

positions = [c.position for c in cards]
expected = list(range(1, 51))
print(f"\n=== 2. position 连续性: {'OK (1..50)' if positions == expected else f'MISMATCH: {positions[:10]}...'} ===")

print(f"\n=== 3. 前 5 张 prompt 风格检查 ===")
for c in cards[:5]:
    print(f"  pos={c.position} segment={c.segment}")
    print(f"    prompt: {c.prompt[:150]}")
    overlay = c.text_overlay_hint.content_suggestion if c.text_overlay_hint else "None"
    print(f"    overlay: {overlay}")
    print()

print(f"=== 4. hook 卡 vs 普通卡对比 ===")
hooks = [c for c in cards if c.position <= 3]
normals = [c for c in cards if 20 <= c.position <= 22]
print("Hook 卡 prompt 片段:")
for c in hooks:
    print(f"  pos={c.position}: {c.prompt[:120]}")
print("普通卡 prompt 片段:")
for c in normals:
    print(f"  pos={c.position}: {c.prompt[:120]}")

print(f"\n=== 5. Meta ===")
print(f"  attempts (total across batches): {cards_meta.attempts}")
print(f"  input_tokens: {cards_meta.input_tokens}")
print(f"  output_tokens: {cards_meta.output_tokens}")
print(f"  cost: ${cards_meta.estimated_cost_usd:.4f}")
print(f"  model: {cards_meta.model}")
