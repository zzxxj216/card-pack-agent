"""探测 jiekou.ai 支持的 embedding 模型"""
import httpx

KEY = "sk_LAwReeB22oqhNb7K0MJFVP_33WHbJDvJeBpWYH_o9zQ"
URL = "https://api.jiekou.ai/openai/v1/embeddings"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
    "text-embedding-v3",
    "embedding-3",
    "embedding-v1",
    "bge-large-zh-v1.5",
    "bge-m3",
]

for model in MODELS:
    try:
        r = httpx.post(URL, headers=HEADERS, json={"model": model, "input": "test"}, timeout=15)
        if r.status_code == 200:
            dim = len(r.json()["data"][0]["embedding"])
            print(f"  OK  {model:<30} dim={dim}")
        else:
            reason = r.json().get("metadata", {}).get("reason", r.text[:80])
            print(f"  FAIL {model:<30} {r.status_code} {reason}")
    except Exception as e:
        print(f"  ERR  {model:<30} {type(e).__name__}")

# Also try listing models
print("\n=== List models ===")
try:
    r = httpx.get("https://api.jiekou.ai/openai/v1/models", headers=HEADERS, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        models = [m["id"] for m in data.get("data", [])]
        embed_models = [m for m in models if "embed" in m.lower() or "bge" in m.lower()]
        print(f"Embedding-related: {embed_models}")
        if not embed_models:
            print(f"All models ({len(models)}): {models[:20]}")
    else:
        print(r.text[:200])
except Exception as e:
    print(f"Error: {e}")
