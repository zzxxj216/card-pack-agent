"""测试真实 embedding + Qdrant 本地存储端到端"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from card_pack_agent.memory.vector import vector_store, COLLECTION_TOPIC, embed

# 1. Create collections with new dim
vector_store.ensure_collections()

# 2. Embed + upsert
vec = embed("中秋节 独在异乡的年轻人")
print(f"Embed dim: {len(vec)}")
vector_store.upsert(COLLECTION_TOPIC, "mid-autumn-001", vec, {
    "topic": "中秋节 独在异乡的年轻人",
    "l1": "festival", "l2": "resonance_healing", "tier": "good",
})

# 3. Exact search
results = vector_store.search(COLLECTION_TOPIC, vec, top_k=3)
print(f"Exact search results: {len(results)}")
for r in results:
    print(f"  id={r.id} score={r.score:.4f} topic={r.payload.get('topic', '?')}")

# 4. Semantic search — different but related query
vec2 = embed("一个人过节")
results2 = vector_store.search(COLLECTION_TOPIC, vec2, top_k=3)
print(f"Semantic search results: {len(results2)}")
for r in results2:
    print(f"  id={r.id} score={r.score:.4f} topic={r.payload.get('topic', '?')}")

print("Done")
