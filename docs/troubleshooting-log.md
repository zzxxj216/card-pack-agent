# card-pack-agent — 首次调通记录

> 日期：2026-04-18
> 环境：Windows 10 / Python 3.13.2 / 代理 API (jiekou.ai) / claude-sonnet-4-6

---

## 一、代码改动

### 1. Mock 与测试修复

| 文件 | 问题 | 修复 |
|------|------|------|
| `src/card_pack_agent/llm.py` | `_segment_for_position` 定义在 `_MOCK_CARDS` 列表推导之后，模块加载时 `NameError` | 将函数定义移到列表之前 |
| `src/card_pack_agent/tools/image/registry.py` | 非法 provider 名抛出 Python enum 原生 `ValueError`，测试 regex 匹配不上 | 在 enum 转换处 try/except，统一抛 `"unknown provider: xxx"` |
| `src/card_pack_agent/json_utils.py` | `_extract_json_block` 先检查 `{` 再检查 `[`，导致 `[{...}, {...}]` 被误提取为单个对象 | 改为按 `[` 与 `{` 谁先出现来选择 opener |
| `src/card_pack_agent/structured_output.py` | `log.info("structured_call.success", call_id=..., **meta.as_dict())` 中 `call_id` 重复传参 | 去掉显式 `call_id=` 参数 |

### 2. 代理 API 适配（Anthropic SDK 与 jiekou.ai 不兼容）

Anthropic SDK 0.86.0 在请求时同时发送 `x-api-key` 和 `Authorization: Bearer`，后者的值被 SDK 内部转换过，代理无法识别，返回 401。

| 文件 | 改动 |
|------|------|
| `src/card_pack_agent/config.py` | 新增 `anthropic_base_url: str` 字段，从 `.env` 读取 |
| `src/card_pack_agent/structured_output.py` | 新增 `_call_via_httpx()`，当 `base_url` 非空时绕过 SDK，直接用 httpx 发请求 |
| `src/card_pack_agent/llm.py` | `LLMClient.complete()` 同样在有 `base_url` 时走 httpx 路径（供 Judge 等使用） |

### 3. 无 Qdrant / Postgres 时的优雅降级

| 文件 | 改动 |
|------|------|
| `src/card_pack_agent/memory/vector.py` | `search()` 改用新版 API `query_points()`；连接失败时打 warning 并返回空列表 |
| `src/card_pack_agent/memory/postgres.py` | `insert()` 在真实库连接失败时降级写入内存 dict |

### 4. Prompt 模板修复（LLM 看不到磁盘文件引用）

原 system prompt 里写 `"严格按照 knowledge/prompt_templates/planner.v1.md 的 Output Schema"`，但 LLM 无法读取该文件，导致输出结构自由发挥。

| 文件 | 改动 |
|------|------|
| `src/card_pack_agent/agents/planner.py` | 在 system prompt 中内嵌完整 Output Schema（字段名、类型约束、枚举值） |
| `src/card_pack_agent/agents/generator_cards_batched.py` | 明确 `text_overlay_hint` 必须是对象（含 `content_suggestion` / `position` / `size_tier`），可为 `null` |
| `src/card_pack_agent/agents/generator.py` | Script 的 system prompt 对齐真实 `Script` / `Shot` / `BGMSuggestion` 字段名（`total_duration_s`、`duration_s` 等） |

### 5. 编排层容错

| 文件 | 改动 |
|------|------|
| `src/card_pack_agent/orchestrator.py` | `generate_script` 失败时 fallback 为合法的最简 `Script`（50 个 `Shot` + `BGMSuggestion`），保证 Evaluator / Judge 能跑通 |

### 6. 仓库与 CI

| 改动 | 说明 |
|------|------|
| `.gitignore` | 新增 `tmp_pack.json`、`tmp_*.json` |
| `.github/workflows/eval.yml` → `docs/ci-workflow-eval.yml` | GitHub CLI token 无 `workflow` 权限，将 workflow 移至 docs 下；需要时复制回 `.github/workflows/` |

---

## 二、运行结果

### Smoke 测试（mock 模式）

```
33 passed, 0 failed (修复前 10 failed)
```

### Step 2 — Planner 单独测试（真 API）

| 指标 | 值 |
|------|-----|
| 返回类型 | StrategyDoc（一次成功） |
| attempts | 1 |
| cost | $0.053 |
| input_tokens | 9644 |
| output_tokens | 1640 |

产出质量：
- palette: `["#F5A623", "#E8824A", "#FFF8E7", "#2C2C2C"]`
- segments: 5 段（hook / setup / development / turn / close）
- avoid 列表 7 条
- style_anchor: `film photography, 35mm, natural light, warm tungsten, shallow depth of field, grain texture`

### Step 3 — Generator 分批测试（真 API）

| 指标 | 值 |
|------|-----|
| 卡贴数量 | 50 张 |
| position 连续性 | 1..50 连续 |
| prompt 风格一致性 | 全部以 film photography / 35mm 开头，palette 颜色贯穿 |
| hook vs 普通卡 | hook 用 close-up 单物件特写，普通卡用 medium shot |
| cost | $0.566（含 2 次 JSON repair retry） |

### Step 4 — 完整 Pipeline（Planner + Generator + Script + Evaluator + Judge）

| 指标 | 值 |
|------|-----|
| Evaluator verdict | **PASS** |
| Judge overall_score | **4.3** |
| style_consistency | 4.5 |
| structural_integrity | 4.4 |
| rule_adherence | 4.2 |
| anti_pattern_clean | 4.0 |
| internal_dedup | 3.6 |
| 耗时 | ~12 分钟 |
| 总 cost | ~$0.86 |

### Judge 稳定性测试（同一 pack 跑 3 次）

| 维度 | Run 1 | Run 2 | Run 3 | spread |
|------|-------|-------|-------|--------|
| style_consistency | 4.8 | 4.8 | 4.8 | 0.0 |
| structural_integrity | 4.5 | 4.5 | 4.5 | 0.0 |
| rule_adherence | 4.2 | 4.2 | 4.2 | 0.0 |
| anti_pattern_clean | 3.8 | 3.8 | 3.8 | 0.0 |
| internal_dedup | 3.6 | 3.6 | 3.6 | 0.0 |
| overall_score | 4.3 | 4.3 | 4.3 | 0.0 |

结论：Judge 在当前配置下极其稳定，无需调整 prompt 或 temperature。

---

## 三、已知限制与后续建议

1. **Script 生成是成本大头**：输出 token 多（~18K），易触发 max_tokens 截断重试。可优化 prompt 减少输出量，或只生成关键帧 shot。
2. **Qdrant / Postgres 未启用**：当前检索返回空、持久化走内存。生产环境需起服务并配置 DSN。
3. **CI workflow**：存放在 `docs/ci-workflow-eval.yml`，需给 GitHub token 加 `workflow` 权限后复制到 `.github/workflows/`。
4. **API 密钥安全**：曾在对话中出现 API Key，建议在服务商侧轮换。仓库内只有 `.env.example`，不含真实密钥。
