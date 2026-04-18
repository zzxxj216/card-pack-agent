# Card Pack Agent

TikTok 卡贴包生成的 Agent 系统，核心特征是**闭环自优化**：每次发布后的数据会回灌进记忆，下次遇到同类话题时自动复用已验证的成功模式。

完整实施计划见 [`docs/plan.md`](docs/plan.md)。

## 架构概览

```
输入 → Planner → Generator → Evaluator(守门) → 发布 → Reviewer(异步复盘)
          ↑                                                 ↓
          └────────── Memory (vector + .md) ←───────────────┘
```

只有 **3 个 Agent**：Planner（大脑）、Generator（执行）、Reviewer（复盘）。其他都是 tool。
Evaluator 是规则 + LLM-as-judge 的 checklist，**不是 agent**。

**双轨 Memory**：
- 向量库（Qdrant + Postgres）存原始案例和指标
- `knowledge/` 下的 `.md` 文档存规则、playbook、禁忌

**三层 Taxonomy**：内容域 × 叙事机制 × 执行属性（详见 `knowledge/taxonomy.md`）

## 快速开始

### 1. 环境准备

```bash
# 克隆后
cp .env.example .env
# 编辑 .env，先把 APP_MODE=mock 保留，可以无 API 跑通结构
make dev
```

### 2. Mock 模式跑通（不需要 API Key）

```bash
make smoke
# 跑完应看到绿色 PASSED，验证骨架完整
```

### 3. 真实模式（需要 API + 本地服务）

```bash
# 启动本地 Postgres + Qdrant（docker-compose 待补，当前需自行启动）
# 填 .env 里的 ANTHROPIC_API_KEY 等
# APP_MODE=dev

make init-db     # 建表 + Qdrant collection
make seed        # 灌入 synthetic 种子数据（节日类）
make generate TOPIC="中秋节" CATEGORY=festival
```

### 4. 运行评测

```bash
make eval        # 跑 A/B/C/D 四类评测，结果写到 eval/runs/
```

## 目录结构

```
.
├── docs/plan.md                  # 完整 14-16 周实施计划
├── knowledge/                    # .md 知识库（git 管理，人工审核）
│   ├── taxonomy.md               # 三层分类定义
│   ├── global_style_guide.md     # 全局视觉/叙事准则
│   ├── global_anti_patterns.md   # 全局禁忌（硬约束）
│   ├── metrics_calibration.md    # tier 分位和计算
│   ├── categories/               # 每类目一份 playbook
│   │   └── festival.md           # 节日类（当前聚焦）
│   ├── prompt_templates/         # 带版本号的 prompt
│   ├── experience_log/           # Reviewer 自动产出的周报（待人工 review）
│   └── failure_library.md        # 翻车案例库
├── src/card_pack_agent/
│   ├── agents/                   # Planner / Generator / Reviewer
│   ├── tools/                    # classify / retrieve / evaluator / ...
│   ├── memory/                   # Postgres + Qdrant + .md loader
│   ├── orchestrator.py           # 主编排流程
│   ├── schemas.py                # Pydantic 数据模型
│   ├── llm.py                    # Anthropic SDK 封装
│   └── config.py                 # 配置加载
├── scripts/
│   ├── init_db.py                # 建表 / 建 collection
│   ├── seed_synthetic.py         # 零数据冷启动
│   ├── generate_pack.py          # CLI: 生成一个包
│   └── run_eval.py               # CLI: 跑评测
├── eval/
│   ├── datasets/holdout.*.jsonl  # 冻结的 holdout 集
│   ├── runners/                  # 四类 eval
│   └── judges/                   # LLM-as-judge 的 prompt
├── migrations/                   # SQL 迁移
└── tests/
```

## 开发约定

1. **`.md` 知识库改动等于架构改动**。改 `knowledge/*.md` 之前先想清楚，PR review 必须覆盖
2. **Agent 只写 `experience_log/`，不直接写 `categories/*.md`**。人工 review 后手动 merge
3. **每次改 prompt 或 taxonomy 必须跑 `make eval`**，回归通过才合入
4. **Holdout 集永远不用于调 prompt**。想调试就扩开发集，不要碰 holdout

## 状态

本仓库目前是 **Phase 0 骨架**。对照 [`docs/plan.md`](docs/plan.md) 的 checklist 推进。

当前聚焦类目：**节日类**（`knowledge/categories/festival.md`）
