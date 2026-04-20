"""直接 httpx 测试 jiekou.ai 图像端点"""
import httpx, json

KEY = "sk_LAwReeB22oqhNb7K0MJFVP_33WHbJDvJeBpWYH_o9zQ"
BASE = "https://api.jiekou.ai"

# Test 1: OpenAI-compat images endpoint
print("=== Test: /v1/images/generations ===")
payload = {
    "model": "gpt-image-1",
    "prompt": "A mooncake on a wooden table, warm light, film photography",
    "n": 1,
    "size": "1024x1536",
}
r = httpx.post(
    f"{BASE}/v1/images/generations",
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    json=payload,
    timeout=120,
)
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:500]}")

if r.status_code != 200:
    # Try without size
    print("\n=== Retry without size ===")
    del payload["size"]
    r2 = httpx.post(
        f"{BASE}/v1/images/generations",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    print(f"Status: {r2.status_code}")
    print(f"Body: {r2.text[:500]}")

    if r2.status_code != 200:
        # Try with quality
        print("\n=== Retry with quality=standard ===")
        payload["quality"] = "standard"
        payload["size"] = "1024x1024"
        r3 = httpx.post(
            f"{BASE}/v1/images/generations",
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        print(f"Status: {r3.status_code}")
        print(f"Body: {r3.text[:500]}")
