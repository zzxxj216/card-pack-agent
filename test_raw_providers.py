"""直接 httpx 测试各 jiekou.ai 端点，确认正确的请求格式"""
import httpx, json, time

KEY = "sk_LAwReeB22oqhNb7K0MJFVP_33WHbJDvJeBpWYH_o9zQ"
GEMINI_KEY = "AIzaSyBssayuL_QrqBR7KWov6srJUlMaWFjz0B0"
BASE = "https://api.jiekou.ai"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
PROMPT = "A mooncake on a wooden table, warm light, film photography"

def test_endpoint(name, url, payload, headers=HEADERS):
    print(f"\n=== {name} ===")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)[:200]}")
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=30)
        print(f"Status: {r.status_code}")
        body = r.text
        if len(body) > 300:
            print(f"Body (truncated): {body[:300]}...")
        else:
            print(f"Body: {body}")
        return r.status_code, r.json() if r.status_code == 200 else r.text
    except Exception as e:
        print(f"Error: {e}")
        return 0, str(e)

# 1. Seedream — try minimal payload
test_endpoint("seedream (minimal)", f"{BASE}/v3/seedream-4.5", {
    "prompt": PROMPT,
    "size": "1088x1920",
})

# 2. Seedream — try with all fields from snippet
test_endpoint("seedream (full)", f"{BASE}/v3/seedream-4.5", {
    "prompt": PROMPT,
    "size": "1088x1920",
    "watermark": False,
    "optimize_prompt_options": {"mode": "disable"},
    "sequential_image_generation": "disabled",
})

# 3. Flux Kontext — submit
status, data = test_endpoint("flux_kontext (submit)", f"{BASE}/v3/async/flux-1-kontext-max", {
    "prompt": PROMPT,
    "aspect_ratio": "9:16",
})
if status == 200 and isinstance(data, dict):
    task_id = data.get("id") or data.get("task_id") or data.get("request_id")
    print(f"Task ID: {task_id}")
    if task_id:
        time.sleep(3)
        # Try different poll URLs
        for poll_path in [
            f"/v3/async/tasks/{task_id}",
            f"/v3/tasks/{task_id}",
            f"/v3/async/flux-1-kontext-max/{task_id}",
            f"/v3/task/{task_id}",
            f"/v1/tasks/{task_id}",
        ]:
            r2 = httpx.get(f"{BASE}{poll_path}", headers=HEADERS, timeout=10)
            print(f"  Poll {poll_path}: {r2.status_code} {r2.text[:150]}")
            if r2.status_code == 200:
                break

# 4. Midjourney — submit
status, data = test_endpoint("midjourney (submit)", f"{BASE}/v3/async/mj-txt2img", {
    "text": f"{PROMPT} --ar 9:16 --v 6 --style raw",
})
if status == 200 and isinstance(data, dict):
    task_id = data.get("id") or data.get("task_id") or data.get("request_id")
    print(f"Task ID: {task_id}")
    if task_id:
        time.sleep(3)
        for poll_path in [
            f"/v3/async/tasks/{task_id}",
            f"/v3/tasks/{task_id}",
            f"/v3/async/mj-txt2img/{task_id}",
            f"/v3/task/{task_id}",
        ]:
            r2 = httpx.get(f"{BASE}{poll_path}", headers=HEADERS, timeout=10)
            print(f"  Poll {poll_path}: {r2.status_code} {r2.text[:150]}")
            if r2.status_code == 200:
                break

# 5. Gemini — try with Google key
test_endpoint("gemini (google key)", f"{BASE}/v3/gemini-3.1-flash-image-edit", {
    "prompt": PROMPT,
    "size": "1024x1536",
    "output_format": "png",
}, headers={"Authorization": f"Bearer {GEMINI_KEY}", "Content-Type": "application/json"})

# Also try with jiekou key
test_endpoint("gemini (jiekou key)", f"{BASE}/v3/gemini-3.1-flash-image-edit", {
    "prompt": PROMPT,
    "size": "1024x1536",
    "output_format": "png",
}, headers=HEADERS)
