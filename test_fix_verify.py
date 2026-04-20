"""验证修复后的参数"""
import httpx, json, time, base64

KEY = "sk_LAwReeB22oqhNb7K0MJFVP_33WHbJDvJeBpWYH_o9zQ"
BASE = "https://api.jiekou.ai"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
PROMPT = "A mooncake on a wooden table, warm light, film photography"

# 1. Seedream — 1920x1920 + optimize_prompt_options.mode=standard
print("=== seedream (fixed) ===")
r = httpx.post(f"{BASE}/v3/seedream-4.5", headers=HEADERS, json={
    "prompt": PROMPT,
    "size": "1920x1920",
    "watermark": False,
    "optimize_prompt_options": {"mode": "standard"},
}, timeout=120)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    url, _ = None, None
    # Try to find image
    if "data" in data:
        for item in data["data"]:
            if "url" in item:
                url = item["url"]
            elif "b64_json" in item:
                print(f"  Got b64 image, length={len(item['b64_json'])}")
    elif "image_url" in data:
        url = data["image_url"]
    print(f"  Image URL: {str(url)[:100] if url else 'None (check b64)'}")
else:
    print(f"  Error: {r.text[:300]}")

# 2. Gemini — jiekou key + output_format=image/png
print("\n=== gemini (jiekou key + mime type) ===")
r = httpx.post(f"{BASE}/v3/gemini-3.1-flash-image-edit", headers=HEADERS, json={
    "prompt": PROMPT,
    "size": "1024x1536",
    "output_format": "image/png",
}, timeout=120)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  Keys: {list(data.keys())[:10]}")
    print(f"  Body (truncated): {json.dumps(data, ensure_ascii=False)[:200]}")
else:
    print(f"  Error: {r.text[:300]}")

# 3. Flux kontext — try GET with different poll patterns
print("\n=== flux_kontext poll URL discovery ===")
# Submit first
r = httpx.post(f"{BASE}/v3/async/flux-1-kontext-max", headers=HEADERS, json={
    "prompt": PROMPT, "aspect_ratio": "9:16",
}, timeout=30)
if r.status_code == 200:
    task_id = r.json().get("task_id") or r.json().get("id")
    print(f"  Task ID: {task_id}")
    time.sleep(5)
    for path in [
        f"/v3/async/tasks/{task_id}",
        f"/v3/async/task/{task_id}",
        f"/v3/task/{task_id}",
        f"/v3/tasks/{task_id}",
        f"/v1/tasks/{task_id}",
        f"/v3/async/flux-1-kontext-max/tasks/{task_id}",
        f"/v3/async/result/{task_id}",
        f"/v3/result/{task_id}",
        f"/v3/async/status/{task_id}",
    ]:
        r2 = httpx.get(f"{BASE}{path}", headers=HEADERS, timeout=10)
        status_str = "OK" if r2.status_code == 200 else str(r2.status_code)
        print(f"  {path}: {status_str} {r2.text[:80]}")
