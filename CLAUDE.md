# CLAUDE.md — Project memory for Claude Code

> 这个文件在每次 Claude Code 启动时自动加载。包含了 card-pack-agent 项目的完整背景，
> 确保 Claude Code 不需要用户每次重复解释项目是什么、架构怎么设计的、哪些坑已经踩过。
>
> **维护原则**：此文件是"项目与 Claude 协作的契约"。任何重大架构决策、踩过的坑、明确的取舍，
> 都应在此登记。遇事先查这里，再问用户。

---

## 1. 项目是什么

**card-pack-agent** 是一个 TikTok 卡贴包生成的 Agent 系统，核心特征是**闭环自优化**：
每次发布后的 TK 数据回灌进记忆，下次遇到同类话题自动复用已验证的成功模式。

- 完整计划：`docs/plan.md`（14-16 周到完整闭环，8 周到 MVP）
- 当前聚焦类目：**节日类**（`knowledge/categories/festival.md`）
- 当前阶段：Phase 0-1 骨架完成，已跑通第一次真 API pipeline

## 2. 核心架构铁律（不要擅自改）

```
输入 → Planner → Generator → Evaluator(守门) → 发布 → Reviewer(异步复盘)
          ↑                                              ↓
          └────────── Memory (vector + .md) ←────────────┘
```

**只有 3 个 Agent**：Planner（唯一大脑）、Generator（执行）、Reviewer（异步复盘）。
其他全部是 tool，不是 agent。**不要**把 Evaluator / ImageGen / Retrieve 改成 agent。

**Evaluator 是规则 + LLM-as-judge 的 checklist，不是 agent**。它只打分和拦截。

**双轨 Memory**：
- 向量库（Qdrant + Postgres）存原始案例和指标
- `knowledge/` 下的 `.md` 存规则、playbook、禁忌
- Agent 只能写 `knowledge/experience_log/`，**不能**直接改 `categories/*.md` 或 `global_*.md`

**三层 Taxonomy 正交**：
- L1 内容域（festival/trending_event/emotional/...）
- L2 叙事机制（resonance_healing/regret_sting/...）— 决定爆款路径的关键
- L3 执行属性（palette/text_density/...）

## 3. 关键踩坑记录（避免重蹈覆辙）

### 3.1 Prompt 模板不能引用 .md 文件路径
`knowledge/prompt_templates/*.md` 是**给人看的规范文档**，LLM 看不到磁盘文件。
真正喂给 LLM 的是 `agents/*.py` 里拼出来的 prompt 字符串。

**任何模板改动必须同步到 agents/*.py 中的 prompt 字符串**，否则跑的永远是代码版本。

### 3.2 LLM 输出 JSON 必然会出错
已踩的坑：markdown fence、前后废话、单引号、trailing comma、max_tokens 截断。
`src/card_pack_agent/json_utils.py` 里的 `parse_json_robust` 处理了这些。
**不要**绕过它直接 `json.loads`。

### 3.3 用代理 API 时 Anthropic SDK 会发重复认证头
Anthropic SDK 0.86.0 同时发 `x-api-key` 和 `Authorization: Bearer`，
经过第三方代理（如 jiekou.ai）会被识别异常返回 401。

**解决方案**：当 `.env` 里配置了 `ANTHROPIC_BASE_URL` 时，
走 `_call_via_httpx()` 路径绕开 SDK（见 `src/card_pack_agent/structured_output.py`）。

⚠️ 检查点：`tools/evaluator.py` 的 `judge_with_llm` 和 `tools/image/vision_judge.py` 
**也必须支持 httpx 分支**，否则用代理时 Judge 会失败或走 mock。

### 3.4 50 张卡贴必须分批生成
单次调用 50 张卡 prompt 容易触发 max_tokens 截断。
`src/card_pack_agent/agents/generator_cards_batched.py` 按 segment 分成每批 ≤12 张。

### 3.5 Script 成本是大头
Script 生成输出 token 容易到 18K，成本 $0.2+。可通过在 prompt 里约束
`shot.notes` 除 key_moments 外必须留空来降低。

### 3.6 Judge 的方差是真实信号
Judge（LLM-as-judge）有真实方差，同一 pack 跑 3 次 overall_score 正常应该差 ±0.1-0.3。
**如果 3 次完全一致，要怀疑 Judge 没真跑**（mock 模式 / 缓存 / httpx 分支没接上）。

### 3.7 Fallback 必须留痕
`orchestrator.py` 在 script 生成失败时 fallback 为最简 Script。
这是对的，但**必须在 Pack 元数据上标 `script_fallback_used=true`**，否则评测会误判。

## 4. 环境与运行约定

- **APP_MODE**：`mock` / `dev` / `prod`
  - `mock`：所有 LLM / 图像 / 向量库调用返回 canned data，不碰网络。smoke 测试必须在此模式跑。
  - `dev`：真 API + 本地 Postgres/Qdrant。可以不起数据库服务，走内存降级。
  - `prod`：真 API + 真数据库，禁止降级。

- **代理 API**：
  - 用户当前使用 `jiekou.ai` 代理
  - `.env` 里必须配 `ANTHROPIC_BASE_URL`
  - 默认模型：Sonnet 4.6（planner / reviewer 也已切到 Sonnet，Opus 太贵先不用）

- **Python 版本**：3.13.2（Windows 10）

## 5. 跑命令前先检查

### 5.1 跑真 API 前
- `.env` 里 `APP_MODE=dev`
- `ANTHROPIC_API_KEY` 已填
- `ANTHROPIC_BASE_URL` 如果是代理就配上
- 先 `make smoke` 确认骨架正常

### 5.2 单测某个 Agent 的推荐顺序（便宜 → 贵）
1. Planner（~$0.05）
2. Generator cards（~$0.5，5 批）
3. Script（~$0.3，单次）
4. Evaluator + Judge（~$0.05）
5. 完整 pipeline（~$0.9 合计）

### 5.3 改了 prompt 之后必跑
```
make smoke                                    # 结构不能坏
python scripts/run_eval.py --suite classify --limit 5   # A 类 eval
```

**不要**改完 prompt 就直接上真 API 跑全量。

## 6. 当前已知状态（截至 2026-04-18）

### ✅ 已验证跑通
- 完整 pipeline 真 API 跑通，pack_id 可生成
- Evaluator verdict = PASS
- Judge overall_score = 4.3（待验证真实性，见第 3.6 条）
- Smoke 测试 33 passed

### 🚧 未启用 / 需确认
- Qdrant / Postgres 未起服务，走内存降级
- Reviewer agent 从未真跑过
- 图像生成真 API（FLUX / OpenAI）未验证，只跑过 mock provider
- 数据回收闭环（Phase 4）未启动

### 🐛 已知小问题
- `internal_dedup` judge 分数偏低（3.6），疑似分批生成的视觉重复
- 图像生成的 `image_gen.py` 兼容层保留，新代码应走 `tools/image/*`

## 7. 用户的优先级

当前用户关心的（按顺序）：
1. 验证 Judge 是不是真跑了（怀疑三次一致是假信号）
2. 跑 3-5 个不同机制的话题积累真实基线
3. 启动 Phase 4 反馈闭环（数据回收 + Reviewer）
4. 图像多模型 bench（已接入 FLUX / OpenAI 代码，待真跑）

**不要**主动建议用户上 Web UI、重构架构、加新 Agent。这些优先级低。

## 8. 与用户协作的原则

- **小步迭代**：一次改动 → 跑 eval → 确认不回退 → 再改下一处。不要堆功能。
- **先验证再写代码**：用户抱怨"效果不好"时，先问 eval 跑了吗、分数多少，
  不要立刻动手改 prompt。
- **花钱谨慎**：每次真 API 调用先估成本（token × 单价），超过 $1 的操作告知用户确认。
- **.md 写入权限**：只能写 `knowledge/experience_log/` 下的新文件（提案）。
  改 `categories/*.md` 或 `global_*.md` 必须用户明确授权。
- **不主动 commit / push**：改完代码让用户自己 review 和提交。

## 9. 常见用户请求的标准回应

| 用户说 | 你应该 |
|---|---|
| "再加一个新 Agent" | 先反问为什么不能做成 tool。架构铁律是 3 个 agent。 |
| "改一下 taxonomy 加个类目" | 指引改 `knowledge/taxonomy.md`，同步 `schemas.py` 的 enum，跑 smoke |
| "怎么让 palette 更多样" | 改 `agents/planner.py` 里的 prompt 字符串，**不是** `prompt_templates/planner.v1.md` |
| "跑一次完整生成" | 先估成本（~$0.9），确认用户接受再跑 |
| "Judge 分数太低" | 先追问哪个维度低，不要直接改 Judge prompt |

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-04-18 | 初版。基于 troubleshooting-log.md 和前期架构讨论生成。 |

---

_维护者：遇到新的重要坑或架构决策，append 到第 3 节或第 6 节。不要删除已有条目。_
