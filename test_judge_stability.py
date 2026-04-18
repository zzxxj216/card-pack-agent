"""Step 4b: Judge 稳定性测试 — 同一个 pack 跑 3 次 Judge"""
import json
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from card_pack_agent.schemas import Pack
from card_pack_agent.tools.evaluator import judge_with_llm

pack = Pack.model_validate_json(
    open("tmp_pack.json", "r", encoding="utf-8").read()
)

scores = []
for i in range(1, 4):
    print(f"=== Judge run {i} ===")
    result = judge_with_llm(pack)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    scores.append(result)
    print()

print("=== Variance Analysis ===")
keys = scores[0].keys()
for k in keys:
    vals = [s[k] for s in scores]
    avg = sum(vals) / len(vals)
    spread = max(vals) - min(vals)
    print(f"  {k}: {vals}  avg={avg:.2f}  spread={spread:.1f}")
