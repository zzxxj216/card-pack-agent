# Card Pack Agent System — 执行计划

**版本**：v1.0
**状态**：Draft / Ready to execute
**预计总工期**：14–16 周到完整闭环，8 周到 MVP

---

## 0. 文档用法

- 本文件是 single source of truth，任何架构/排期/验收标准的变更都必须更新这里再改代码
- 每周 review 一次，勾选完成项，把延期项的新日期和原因写进对应 phase
- `[ ]` = 未开始，`[~]` = 进行中，`[x]` = 完成
- 决策类问题进 §8，不要散落在代码注释里

---

## 1. 项目目标与成功标准

### 1.1 业务目标
构建一个能在 TikTok 上**随时间单调变好**的卡贴包生成系统。对于同类型话题，第 N 次生成的产出质量应该 ≥ 第 N-1 次，而不是忽上忽下。

### 1.2 技术目标
- 任何一次 prompt / taxonomy / 检索逻辑的修改，都能在 30 分钟内跑完离线回归评测
- 新话题进来，从输入到产出完整卡贴包 + 脚本的时间 ≤ 15 分钟
- 知识库人类可读、可审计、可回滚

### 1.3 成功标准（3 个月后度量）
| 指标 | 目标 |
|---|---|
| 同类目下，新生成包的平均表现 tier | 高于回灌历史均值 |
| Offline eval 分数与线上真实 tier 的相关系数 | ≥ 0.5 |
| 触发 `global_anti_patterns` 的产出比例 | < 1% |
| 跨批次视觉/文案 diversity 分数 | 不单调下降 |

---

## 2. 架构摘要

### 2.1 核心组件（只有 3 个 Agent）

```
输入 → Planner/Orchestrator → Generator → Evaluator(守门) → 发布 → Reviewer(异步复盘)
                  ↑                                                      ↓
                  └─────────────── Memory (vector + .md) ←───────────────┘
```

- **Planner**：唯一大脑。分类、检索、产出 strategy doc
- **Generator**：执行层。卡贴 prompt 批量生成 + 脚本生成合并成一个工位
- **Evaluator**：发布前守门。规则 checklist + LLM-as-judge，**不是 agent**，是 tool
- **Reviewer**：异步复盘。归因、抽模式、写 experience_log

其他所有功能（web_search、url_fetch、image_gen、vector_search、metrics_pull）都是 tool，不是 agent。

### 2.2 三层 Taxonomy（正交维度）

| 层 | 取值示例 |
|---|---|
| 一级：内容域 | 节日 / 热点事件 / 情绪 / 知识 / 人物 / 关系 / 成长 |
| 二级：叙事机制 | 遗憾刺痛 / 共鸣治愈 / 反差反转 / 祝福仪式 / 实用清单 / 金句教训 / 冲突张力 |
| 三级：执行属性 | 暖色/冷色、文本密度、单意象/多人物、快/慢节奏、CTA 强弱 |

**检索规则**：先按二级做硬过滤（同叙事机制），再在候选集内用一级 embedding 排序，三级作为生成约束。

### 2.3 双轨 Memory

- **Vector Memory (Qdrant + Postgres)**：存原始案例和指标，解决"找相似的"
- **.md 知识库 (git-managed)**：存规则、playbook、禁忌、experience_log，解决"查规则的"
- Agent 只能向 `experience_log/` 写入"提案"，`categories/`、`global_*.md` 需人工合并

### 2.4 技术栈

| 用途 | 选型 | 备注 |
|---|---|---|
| 编排 | Anthropic Agent SDK | 线性 + 循环 workflow 足够，不上 LangGraph |
| LLM 规划 / 复盘 | Claude Opus 4.7 | 质量敏感 |
| LLM 批量生成 | Claude Sonnet 4.6 | 成本敏感 |
| 图像生成 | FLUX 或 gpt-image-1 | Phase 2 再决定，先占位 |
| 向量库 | Qdrant | 开源、好部署 |
| 结构化库 | Postgres (JSONB) | 案例元数据 + 指标 |
| 对象存储 | R2 / S3 | 卡贴图片 |
| 队列 | BullMQ 或 Celery | 50 张并行生图 |
| 评测 CI | GitHub Actions + 自建 runner | Phase 1 搭 |

---

## 3. 分阶段实施

### Phase 0 — 地基（Week 1–2）

**目标**：把后面所有阶段要用的数据和规则定义清楚。不写任何生成逻辑。

- [ ] **W1-T1** 盘点历史数据：把已经人工做过的卡贴包（哪怕只有 10-30 个）整理到一个表，含：原始话题、50 张卡贴 prompt 或图、脚本、TK 指标
- [ ] **W1-T2** 定义一级 taxonomy（内容域）：7-8 个桶，写进 `knowledge/taxonomy.md`，每个桶给 3 个正例 + 3 个反例
- [ ] **W1-T3** 定义二级 taxonomy（叙事机制）：6-8 个机制，同样给例子
- [ ] **W1-T4** 定义三级执行属性：不需要穷举，给一个枚举集合就行
- [ ] **W1-T5** 人工标注历史数据：把 §W1-T1 的数据全部打上三层标签。这是后面所有 eval 和 memory 的种子，不能跳
- [ ] **W2-T1** 建 `.md` 知识库骨架（目录结构见 §5）
- [ ] **W2-T2** 写 `global_anti_patterns.md`：平台违禁词、品牌红线、视觉禁区、历史踩过的雷。< 2000 字
- [ ] **W2-T3** 写 `global_style_guide.md`：视觉统一性原则、文案基调、品牌声音。< 2000 字
- [ ] **W2-T4** 起搭基础设施：Postgres + Qdrant + 对象存储 + 一个空仓库和 CI pipeline
- [ ] **W2-T5** 把历史数据导入 Postgres，建向量索引占位（暂不查）

**验收标准**：
- 给一个随机新话题，两个不同的人独立用 taxonomy 打标签，至少 2/3 情况下一级 + 二级一致
- 所有基础设施跑起来，能 insert / query / 存图

**交付物**：
- `knowledge/taxonomy.md`
- `knowledge/global_anti_patterns.md`
- `knowledge/global_style_guide.md`
- 带标注的历史数据集（至少 30 条，目标 50+）
- Postgres schema + Qdrant collection
- 空的 CI pipeline

**关键风险**：
- 历史数据不够 30 条 → 人工标 50 个近期 TK 上同类目爆款作为种子
- 二级标签分歧太大 → 当场合并或拆分，不要带着歧义进下一阶段

---

### Phase 1 — Eval Harness（Week 3–4）

**目标**：**在写任何生成代码之前，先能打分**。这是整个项目稳定迭代的前提。

- [ ] **W3-T1** 构建 holdout 数据集：从 Phase 0 的标注数据里随机抽 20%，冻结，永远不用于训练/调 prompt
- [ ] **W3-T2** 实现 A. 分类评测
  - 输入：历史话题文本
  - 输出：taxonomy 标签
  - 打分：一级 accuracy、二级 accuracy、一二级联合 accuracy
- [ ] **W3-T3** 实现 B. 检索评测
  - 输入：一个话题
  - 输出：Top-K 历史相似案例
  - 打分：召回里有多少 tier≥good、叙事机制是否匹配
- [ ] **W3-T4** 实现 C. 生成评测（用 LLM-as-judge）
  - 输入：strategy doc
  - 输出：50 张卡贴 prompt + 脚本
  - 打分维度：风格一致性、结构完整性、类目规则符合度、禁忌踩雷、卡贴内部重复度
  - 用 Claude Opus 4.7 做 judge，prompt 写进 `eval/judges/`
- [ ] **W3-T5** 实现 D. 经验注入评测
  - 同一个 holdout 话题，分别在 "裸跑" / "只读 global" / "读 global + category" / "读全部包括 experience_log" 四种设定下跑生成
  - 观察打分是否单调上升；如果注入反而下降，说明某份 .md 有毒
- [ ] **W4-T1** 四类评测接入 CI：每次 `knowledge/` 或 `prompts/` 变更，自动跑回归
- [ ] **W4-T2** 实现打分看板：简单 HTML 页面，展示每次 run 的四类分数 + diff
- [ ] **W4-T3** 建立 baseline：用最朴素的 prompt 跑一次四类 eval，把数字钉在墙上作为原点

**验收标准**：
- 一次完整 eval run < 30 分钟
- 四类评测都能输出数值打分 + 明细
- CI 能自动阻塞（设分数回退阈值）

**交付物**：
- `eval/datasets/holdout.jsonl`
- `eval/runners/{classify,retrieve,generate,inject}.py`
- `eval/judges/` 下的 judge prompts
- CI 配置
- baseline 分数表（写进本文档 §6）

**关键风险**：
- LLM-as-judge 本身打分不稳 → 每个样本跑 3 次取中位数；定期人工 spot check 10%
- holdout 污染 → 明确分离目录，code review 时检查

---

### Phase 2 — 核心生成链路 MVP（Week 5–7）

**目标**：端到端跑通 输入 → Planner → Generator → Evaluator → 产出。**此阶段不接 Memory**，用 .md 知识库足够。

- [ ] **W5-T1** 实现 Planner
  - Tools: `web_search`, `url_fetch`, `classify_topic`（调 taxonomy）
  - 产出 strategy doc（结构化 JSON + 自然语言说明）
  - System prompt 加载 `global_*.md` + 对应 category playbook
- [ ] **W5-T2** 实现 Generator — 卡贴 prompt 部分
  - 输入 strategy doc，产出 50 条 image prompt
  - 显式控制 pack 内部节奏（前 3-5 张钩子、中段、收尾）
- [ ] **W5-T3** 实现 Generator — 脚本部分
  - 和卡贴共享 strategy doc，保证对齐
  - 产出分镜脚本（每秒对应哪张卡、配文、语气）
- [ ] **W6-T1** 实现 Evaluator（规则 + LLM-judge，不是 agent）
  - 规则层：禁忌词扫描、长度检查、结构检查、卡贴内部视觉重复度
  - Judge 层：调 Phase 1 的 C 类 judge
  - 输出 PASS / FAIL / WARN + 原因
  - FAIL 自动打回 Generator 重跑一次
- [ ] **W6-T2** 接图像生成
  - 先用 FLUX 和 gpt-image-1 各跑 5 个包做 A/B，人工看
  - 确定后固定一家，写 image_gen tool
  - 并发生图（BullMQ 队列，单次控制在 50 并发以内避免被限流）
- [ ] **W7-T1** 端到端集成：写一个 CLI `generate_pack --topic "xxx"`，跑完整流程
- [ ] **W7-T2** 用 Phase 1 的 eval harness 评估 MVP 产出
- [ ] **W7-T3** 人工 review 5-10 个真实产出包，记录问题到 `knowledge/experience_log/w7_review.md`
- [ ] **W7-T4** 把 Phase 0 已有历史数据作为"理想产出"示例，塞进 Planner 的 few-shot

**验收标准**：
- 端到端一次运行 ≤ 15 分钟
- 50 张卡贴 + 脚本，Evaluator 通过率 ≥ 80%
- 人工 review 打分（1-5）均值 ≥ 3.5

**交付物**：
- `agents/planner.py`, `agents/generator.py`
- `tools/evaluator.py`, `tools/image_gen.py`
- CLI: `scripts/generate_pack.py`
- MVP eval 报告

**关键风险**：
- 50 张风格不统一 → 加 style reference 机制；或分批生成，每批共享 seed
- Script 和卡贴对不上 → Generator 必须一次会话内同时产两者，不能分两次调用

---

### Phase 3 — Memory 系统（Week 8–10）

**目标**：让系统开始"有记忆"。Planner 能从历史数据中召回相似高分案例，作为 context 注入生成。

- [ ] **W8-T1** 定义 case record schema（见 §5.2）
- [ ] **W8-T2** 回灌历史数据：把 Phase 0 整理的所有历史包写入 Postgres，生成向量
- [ ] **W8-T3** 实现三路向量
  - 话题向量（标题 + 描述）
  - 卡包整体向量（所有卡贴 prompt 拼接摘要）
  - 单张卡贴向量（用于同张风格检索，Phase 3 先不用，留占位）
- [ ] **W8-T4** 实现 two-stage retrieval
  - Stage 1：按二级 taxonomy 硬过滤
  - Stage 2：候选集内按话题向量 + 时间衰减排序
  - 时间衰减：`score = cosine * exp(-age_days / 90)`
- [ ] **W9-T1** Planner 接入检索
  - 分类后自动调 retrieve，Top-K=5
  - 召回结果结构化摘要 + 2-3 个完整案例塞进 context
  - Token 预算控制：retrieved context 总量 < 8k tokens
- [ ] **W9-T2** 实现 .md skill loader
  - Planner 分类后，动态 load `knowledge/categories/{category}.md`
  - 避免把所有 category 都塞进 system prompt
- [ ] **W9-T3** 跑 Phase 1 的 B 类 (检索) 和 D 类 (注入) eval，确认分数高于 Phase 2 baseline
- [ ] **W10-T1** 为每个一级类目至少写一份 `categories/{x}.md` playbook（结构见 §5.3）
- [ ] **W10-T2** 写 `failure_library.md`：把 Phase 2 发现的所有翻车案例结构化记录
- [ ] **W10-T3** 全量 eval run，对比 Phase 2 baseline

**验收标准**：
- B 类 eval 分数相比"随机召回"基线提升 ≥ 30%
- D 类 eval 确认注入带来正向收益（不是噪声）
- 每个一级类目都有 playbook

**交付物**：
- `tools/retrieve.py`
- `knowledge/categories/*.md`（至少 7 份）
- `knowledge/failure_library.md`
- Phase 2 → Phase 3 的 eval 对比报告

**关键风险**：
- 历史数据不够 → 先手动写 5-10 个"理想范本"塞进案例库，标为 synthetic，eval 时排除
- 召回同质化 → Phase 5 再解决，先记录观察

---

### Phase 4 — 反馈闭环（Week 11–13）

**目标**：让 Reviewer 把线上数据回灌成可复用的经验，闭环跑通。

- [ ] **W11-T1** 建数据回收表单：Google Sheet 或简单 web form，每个发布包手动填 views / completion / likes / shares / 评论关键词 / 印象最深的前 3 张
- [ ] **W11-T2** 定义 tier 分位：基于历史数据的 P90/P60/P30 定 viral/good/mid/bad 阈值，写进 `knowledge/metrics_calibration.md`
- [ ] **W11-T3** 实现 metrics_pull tool：从表单同步到 Postgres
- [ ] **W12-T1** 实现 Reviewer agent
  - 输入：一批近期上线的包 + 指标
  - Step 1: 归因到单张卡（基于评论提到 + 位置 + 人工标的"印象最深"）
  - Step 2: 同类目 top/bottom 对比
  - Step 3: 结构化输出差异规律
  - Step 4: 写入 `knowledge/experience_log/YYYY-Wxx.md`
- [ ] **W12-T2** 建立人工合并流程
  - Reviewer 每周自动产出 experience_log
  - 人工 1 小时 review，把有价值的 merge 到对应 `categories/*.md`
  - 无价值的归档到 `experience_log/rejected/`
- [ ] **W12-T3** 实现 tier 重校准脚本：每 50 个新样本自动重算 P90/P60/P30，提示人工是否更新阈值
- [ ] **W13-T1** 第一次完整闭环 drill：发布 5-10 个真实包 → 填数据 → Reviewer 跑 → 人工合并 → 用更新后的 knowledge 重新跑 Phase 1 eval
- [ ] **W13-T2** 确认 eval 分数在经验合并后上升，未上升则回滚合并

**验收标准**：
- Reviewer 产出的 experience_log 人工 review 有效率 ≥ 30%（低于此说明归因不准）
- 闭环 drill 后整体 eval 分数较 Phase 3 有提升

**交付物**：
- 数据回收表单
- `agents/reviewer.py`
- `knowledge/metrics_calibration.md`
- 合并流程 SOP
- 第一份真实 `experience_log/`

**关键风险**：
- 人工填数据懒 → 表单字段压到最少，用低摩擦工具（Airtable/Sheets）
- Reviewer 归因不准 → Phase 4 初期就接受这点，靠人工 review 过滤，不追求全自动

---

### Phase 5 — 防漂移与持续优化（Week 14+，持续进行）

**目标**：对冲 case-based 系统的天然收敛趋势。

- [ ] **探索预算机制**
  - 每批生成 15-20% 不走检索出的成功模式，随机采样或刻意试低召回 pattern
  - 这部分单独标记 `exploration=true`，单独追踪表现
- [ ] **时间衰减调优**
  - 监控：近 30 天案例在 Top-K 召回中的占比
  - 目标：占比维持在 40-60%，过低说明衰减不够，过高说明盖住了经典
- [ ] **Diversity 监控**
  - 每周计算：本周产出卡贴 embedding 的协方差/方差
  - 单调下降 → 警报，人工介入
- [ ] **Correlation eval**
  - 每季度一次：抽 30 个真实发布的包，看 Evaluator offline 分数与真实 tier 的相关系数
  - < 0.5 → 说明 offline 打分漂了，需要调 judge prompt
- [ ] **人工越狱 slot**
  - 每周留 1-2 个话题，人工喂给 Planner 时强制 `ignore_memory=true`
  - 好就进案例库，差就当学费
- [ ] **TK API 替代人工填表**（取决于 API 可用性）
- [ ] **AI 视频生成替代前期人工剪辑**（Veo 3 / 可灵 / Runway）

此阶段不设 deadline，作为持续运营工作。

---

## 4. 核心优化点优先级（排期冲突时按此取舍）

| 优先级 | 优化点 | 在哪个 Phase |
|---|---|---|
| P0 | 三层 Taxonomy 质量 | Phase 0 |
| P0 | Eval harness | Phase 1 |
| P1 | 检索精度（two-stage + 时间衰减） | Phase 3 |
| P1 | 模式抽取粒度（Reviewer 输出结构化） | Phase 4 |
| P2 | 归因保真度（单卡级别） | Phase 4 |
| P2 | Tier 校准（动态分位） | Phase 4 |
| P3 | Context 注入策略（token budget） | Phase 3 |
| P3 | 探索预算与防漂移 | Phase 5 |

排期冲突时永远保 P0。

---

## 5. 知识库与数据结构

### 5.1 `.md` 知识库目录

```
knowledge/
├── taxonomy.md                    # 三层分类定义 + 边界判定
├── global_style_guide.md          # 全局视觉/叙事
├── global_anti_patterns.md        # 全局禁忌（硬约束）
├── metrics_calibration.md         # tier 分位 + 计算逻辑
├── categories/
│   ├── festival.md
│   ├── trending_event.md
│   ├── emotional.md
│   ├── knowledge.md
│   ├── character.md
│   ├── relationship.md
│   └── growth.md
├── prompt_templates/
│   ├── planner.v{N}.md
│   ├── generator_cards.v{N}.md
│   ├── generator_script.v{N}.md
│   └── reviewer.v{N}.md
├── experience_log/
│   ├── 2026-W15.md
│   ├── 2026-W16.md
│   └── rejected/
└── failure_library.md             # 翻车案例结构化记录
```

### 5.2 Case record schema (Postgres + Qdrant)

```sql
create table cases (
  pack_id uuid primary key,
  topic text,
  topic_l1 text,      -- 内容域
  topic_l2 text,      -- 叙事机制
  topic_l3 jsonb,     -- 执行属性数组
  strategy_doc jsonb,
  cards jsonb,        -- [{id, prompt, image_url, position}]
  script text,
  metrics jsonb,      -- {views, completion_rate, likes, ...}
  tier text,          -- viral / good / mid / bad
  extracted_patterns jsonb,
  is_exploration bool,
  is_synthetic bool,
  created_at timestamptz
);
```

Qdrant collections:
- `topic_vectors` — payload 关联 pack_id + l1 + l2
- `pack_vectors` — 整包语义向量
- `card_vectors` — 单张卡贴向量（Phase 3 占位，Phase 5+ 用）

### 5.3 Category playbook 标准模板

```markdown
# {类目名}

## 判定边界
- 属于：
- 不属于（应归别类）：

## 成功模式
（抽自 viral + good 案例，结构化规则，不是抒情）
1. 视觉层：...
2. 叙事层：...
3. 节奏层：...

## 禁忌
（源自 failure_library 和 experience_log）
1. ... — 参见 failure_library.md#case-{id}

## 推荐 prompt 模板
→ prompt_templates/generator_cards.vN.md §{this_category}

## 未决问题
（正在 A/B、数据不足、等观察的）
```

---

## 6. Metrics & Baseline 占位

每个 phase 完成后填入数字，直接覆盖 `<TBD>`。

| 指标 | Phase 2 baseline | Phase 3 | Phase 4 | 当前 |
|---|---|---|---|---|
| A. 分类 accuracy (L1) | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| A. 分类 accuracy (L1+L2) | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| B. 检索 hit@5 (tier≥good) | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| C. 生成 judge score (avg) | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| C. Evaluator pass rate | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| D. 注入增益（相对裸跑） | — | `<TBD>` | `<TBD>` | `<TBD>` |
| 端到端耗时 (P50) | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |
| Offline-online correlation | — | — | `<TBD>` | `<TBD>` |

---

## 7. 风险与对策

| 风险 | 触发信号 | 对策 |
|---|---|---|
| 历史数据不足 30 条 | Phase 0 盘点时发现 | 人工标 50 个近期同类目爆款作种子 |
| 叙事机制分类主观分歧 | 两人标注一致率 < 2/3 | 当场合并/拆分，写清判定边界 |
| LLM-judge 打分不稳 | 同样本多次 run 方差大 | 3 次取中位数；季度 correlation eval 校准 |
| 知识库自我污染 | D 类 eval 加载经验后分数反降 | 严格卡住 Agent 写入权限，只能写 experience_log |
| 风格收敛 | Diversity 方差单调下降 | 探索预算 + 时间衰减 + 人工越狱 slot |
| 历史经典盖过新趋势 | 召回中近 30 天占比 < 40% | 调整时间衰减系数（半衰期从 90 天降到 60） |
| 图像模型限流 | 50 张生成失败率 > 10% | 切分批次 + 指数退避；Phase 2 末备选模型 |
| 归因不准导致坏模式入库 | Reviewer 经验合并后 eval 分数降 | 回滚合并；提高人工 review 阈值 |

---

## 8. 待决问题（需要人工拍板）

本节永远不要空置——问题解答后把答案写在这里并加日期，不要删除问题。

- [ ] **Q1** 图像模型最终选哪家？FLUX vs gpt-image-1 vs 其他。Phase 2 末定。
- [ ] **Q2** TK 数据能否接 API 还是只能手动收集？影响 Phase 4 自动化程度。
- [ ] **Q3** 是否需要品牌/视觉风格的 LoRA？如果 50 张一致性不靠 prompt 能解决就不做。
- [ ] **Q4** 第一个优先上线的类目是哪个？Phase 3 playbook 写作顺序以此为准。
- [ ] **Q5** 人工 review experience_log 的 owner 是谁？每周 review 时间？
- [ ] **Q6** Phase 5 的探索预算比例最终定多少？先用 20% 跑一个月看 diversity 变化。

---

## 9. 角色与职责建议

| 角色 | 职责 | 投入 |
|---|---|---|
| 系统工程师 | 搭基建、Agent 实现、CI | 全职，14 周 |
| 内容/运营 | Taxonomy 设计、playbook 撰写、experience_log review | 半职，持续 |
| 数据/eval | Holdout 集、judge prompt 调优、correlation eval | 半职，Phase 1 之后持续 |
| 剪辑 | 视频制作，前期人工出片 | 按需 |

单人也能跑，但 Phase 0 的 taxonomy 和 Phase 4 的 review 两块尽量找第二人对 check，避免独断。

---

## 10. 变更记录

| 日期 | 版本 | 变更 | 作者 |
|---|---|---|---|
| 2026-04-17 | v1.0 | 初版 | — |

