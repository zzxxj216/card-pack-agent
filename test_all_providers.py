"""批量测试所有图像 provider"""
import os, sys, json, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from card_pack_agent.tools.image.base import GenerationParams
from card_pack_agent.tools.image.generate import generate_one

PROMPT = (
    "film photography, 35mm, warm tungsten glow, shallow depth of field, grain texture. "
    "A single mooncake on a worn wooden table, beside a crumpled takeout container. "
    "Soft amber desk lamp light. Dark blurred background. "
    "Palette: #F5A623, #E8824A, #FFF8E7."
)

params = GenerationParams(
    prompt=PROMPT,
    negative_prompt="text, watermark, logo, typography, people, faces",
    aspect_ratio="9:16",
)

PROVIDERS = [
    "jiekou_openai",
    "seedream_v45",
    "flux_kontext_max",
    "midjourney_txt2img",
    "gemini_flash_image_edit",
]

results = []
for name in PROVIDERS:
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    t0 = time.time()
    try:
        r = generate_one(params, provider=name, use_cache=False)
        elapsed = time.time() - t0
        row = {
            "provider": name,
            "ok": r.ok,
            "error": r.error,
            "image_path": r.image_url if r.ok else None,
            "latency_ms": r.latency_ms,
            "cost": r.cost_usd,
            "size": f"{r.width}x{r.height}" if r.ok else None,
            "wall_time_s": round(elapsed, 1),
        }
    except Exception as e:
        elapsed = time.time() - t0
        row = {
            "provider": name,
            "ok": False,
            "error": str(e)[:200],
            "image_path": None,
            "latency_ms": 0,
            "cost": 0,
            "size": None,
            "wall_time_s": round(elapsed, 1),
        }
    results.append(row)
    status = "OK" if row["ok"] else f"FAIL: {row['error'][:80]}"
    print(f"  -> {status}  ({row['wall_time_s']}s)")

print(f"\n\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"{'Provider':<25} {'OK':<5} {'Time':>7} {'Cost':>7} {'Size':<12} Error")
print("-" * 90)
for r in results:
    ok_str = "Y" if r["ok"] else "N"
    t_str = f"{r['wall_time_s']}s"
    c_str = f"${r['cost']:.3f}" if r["cost"] else "-"
    s_str = r["size"] or "-"
    e_str = (r["error"] or "")[:40]
    print(f"{r['provider']:<25} {ok_str:<5} {t_str:>7} {c_str:>7} {s_str:<12} {e_str}")
