"""快速测试图像生成 — jiekou_openai provider"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from card_pack_agent.tools.image.base import GenerationParams
from card_pack_agent.tools.image.generate import generate_one

params = GenerationParams(
    prompt="film photography, 35mm, warm tungsten glow, shallow depth of field. A single mooncake on a worn wooden table, beside a crumpled takeout container. Soft amber desk lamp light. Dark blurred background. Palette: #F5A623, #E8824A, #FFF8E7.",
    negative_prompt="text, watermark, logo, typography, people, faces",
    aspect_ratio="9:16",
)

print("=== Generating with jiekou_openai (gpt-image-1) ===")
result = generate_one(params, provider="jiekou_openai", use_cache=False)
print(f"OK: {result.ok}")
print(f"Error: {result.error}")
print(f"Image URL/path: {result.image_url}")
print(f"Latency: {result.latency_ms}ms")
print(f"Cost: ${result.cost_usd}")
print(f"Size: {result.width}x{result.height}")
