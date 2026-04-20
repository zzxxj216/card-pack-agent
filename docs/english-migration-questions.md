# English Migration — Open Questions for the Operator

> 这份文档列出英文化迁移完成后仍需你(运营/产品)拍板的问题。
> 每一条都是可以独立回答的。回答后我会把结论沉淀到对应的 `.md` / 代码文件里。
>
> 相关完成情况见本文档末尾的 "Completed work" 一览。
>
> **Last updated**: 2026-04-20

---

## How to use this doc

对于每一条，给出以下之一即可：
- **✅ 接受** — 我会按当前默认值落地（文档里已写的那版）
- **❌ 改为 X** — 你给出替代答案，我修改到对应文件
- **⏳ 暂缓** — 不想现在决定，先留白，下次回滚时再看

---

## A. 语言与文案策略

### A1. "纯英文输出" 的边界
**当前默认**：所有用户可见产出(卡贴 overlay / script / hook / CTA)100% 英文；
`knowledge/` 下的规则/模板 100% 英文；`CLAUDE.md` 保留中文；代码注释保留原样。

**需要确认**：
- [ ] `docs/plan.md` 是否需要翻成英文？(当前是中文，我没动它)
- [ ] `docs/troubleshooting-log.md` 是否需要翻译？(当前中文)
- [ ] `README.md` 是否需要翻译？我倾向双语 README 或直接英文 README，
      你倾向哪种？

### A2. Bilingual retrieval pool 的长期策略
**当前默认**：
- `scripts/seed_synthetic.py` 新增 `--include-legacy-cn` flag，默认不开
- 保留 5 条 CN festival seed 作为历史参考，新增 15 条 EN festival + 5 EN emotional + 3 EN trending
- 向量库 payload 里带 `"language": "en" | "zh"`

**需要确认**：
- [ ] 线上 retrieval 召回时是否要按 `language="en"` 过滤？
      还是允许 CN case 也能被召回用作"结构参考"？
- [ ] 如果只用 EN，那 CN seeds 留着的唯一用途就是 ablation / 回归测试。
      你是否倾向彻底清掉 CN seeds？

### A3. 英文词数硬约束
**当前默认** (`knowledge/global_style_guide.md` §2):
- Typography 单张卡贴 ≈ **12 个英文单词** 上限
- Hook ≤ 8 words, body ≤ 14 words (写在 `agents/generator_cards_batched.py` 的 prompt 里)

**需要确认**：
- [ ] 12 词上限是否偏严？我基于 TikTok 竖屏可读性估算的，但没 A/B 过。
      是否接受先跑着看，如果 Evaluator 频繁刷 `text_density` 扣分再调？

---

## B. 禁词 / 敏感话题

### B1. `_DEFAULT_BANNED_WORDS` 的英文清单
**当前默认** (`src/card_pack_agent/tools/evaluator.py`):
```
EN: suicide, kill myself, kms, self-harm, cutting myself,
    underage, guaranteed cure, miracle cure
CN (legacy): 自杀, 自残, 割腕, 跳楼, 上吊
```

**需要确认**：
- [ ] 这个 EN 清单覆盖够吗？建议追加的候选：
      `overdose`, `OD`, `starve yourself`, `thinspo`,
      `pro-ana`, `pro-mia`, `unalive`(TK 规避词但该词本身也是高风险),
      `HIV+`(可能误伤医学教育内容), `groom`(英语里常用于家长给小孩洗头发，
      容易误伤)
      我没加它们，等你确认"是否加"以及"加哪个"。
- [ ] 是否需要把 banned words 移到 `knowledge/banned_words.txt` 这种可在线编辑的文件，
      让运营直接维护而不必改代码？我可以做这个重构。

### B2. `_STALE_MEMES` 的清单
**当前默认**:
```
EN: no cap, slay queen, it's giving, main character energy,
    living rent free, understood the assignment, ate and left no crumbs
CN (legacy): 破防, emo 了, 治愈感拉满, 氛围感, yyds, 绝绝子, 狠狠
```

**需要确认**：
- [ ] 这 7 个 EN 词 2026Q1 是否仍算 stale？有可能其中某些对你目标受众(比如 Z-gen)
      还在有效期内。
- [ ] 要不要加：`era(如 "healing era")`, `chronically online`, `girl dinner`,
      `rizz`, `NPC`？

### B3. Sensitive dates — 英文化替换
**当前默认** (`knowledge/global_anti_patterns.md` §3.1):
替换后的敏感日期列表：
- September 11 (U.S.)
- Holocaust Remembrance Day
- MLK Day
- Juneteenth
- Memorial Day (U.S.) / Veterans Day (U.S.) / Remembrance Day (UK/CA/AU)
- Indigenous Peoples' Day
- Religious observances (Yom Kippur, Good Friday, Ashura)

**需要确认**：
- [ ] 要不要加 **Pulse nightclub anniversary (6/12)** / **Columbine (4/20)** /
      **Hurricane Katrina anniversary** 这类非官方但情绪敏感的日期？
- [ ] 加拿大的 National Day for Truth and Reconciliation (Orange Shirt Day, 9/30)
      要不要加？

---

## C. 内容域扩张 (L1 categories)

### C1. 新 L1 playbook 的数据验证门槛
**当前默认** (`knowledge/categories/emotional.md`, `trending_event.md` 都写了
`**Validation progress**: 0 / 30 packs`):
参考 `festival.md` 的习惯 —— 30 个真实发布 pack 之前，playbook 视为 unvalidated。

**需要确认**：
- [ ] `trending_event` 的 decay 是 24 小时，30 个 pack 门槛很难攒齐。
      是否要对这 L1 单独设较低阈值(例如 10 个)？
- [ ] `emotional` vs `festival` 比例你期望如何？比如一个月内你希望发
      10 个 festival + 5 个 emotional + 5 个 trending？这会影响我后续 seed / eval suite 的比例。

### C2. `trending_event` 的 scope 保守度
**当前默认** (`knowledge/categories/trending_event.md`):
- 完全拉黑：partisan politics, disasters/tragedies, 未经 reputable source 确认的 claim
- 只做 condolence frame 的：loss-of-life 事件
- 不做 impersonation

**需要确认**：
- [ ] 是否过于保守？如果你的运营判断"能做"但 playbook 说"不做"，
      以谁为准？当前默认是 playbook 为 hard gate，Planner 遇到 trending 话题会拒绝。
- [ ] Sports moments 里的"球队球员本人" ≠ "news personality"。
      现在 playbook 一刀切禁止 impersonation，是否要对体育领域放宽？

### C3. 是否还要加 L1?
**当前默认**：只做 festival / emotional / trending_event 三个。
`knowledge/taxonomy.md` 已经列出了 8 个 L1 候选
(relationship / growth / knowledge / identity / lifestyle 暂未做 playbook)。

**需要确认**：
- [ ] 下一个要做 playbook 的 L1 是哪个？我的建议顺序是：
      `relationship` (母亲节/父亲节之外还能挂) → `lifestyle` (cozy / wellness aesthetic 话题很吃 TK) → 其余按流量实测。
- [ ] 还是先不扩，把现有 3 个 L1 的 pack 基线打实再说？

---

## D. 品牌红线

### D1. 品牌 / 合作方不可说的话
**当前默认** (`knowledge/global_anti_patterns.md` §6):
目前这一节是空壳占位，只写了"参见品牌红线附件"但没附件。

**需要确认**：
- [ ] 是否有品牌合作方？如果有，给我一份：
      - 绝对不能提的竞品名
      - 可以提但必须小心的话题 (如 "不能暗示治疗效果" / "不能做对比断言")
      - 必须加的免责声明 (如 "This is not medical advice")
- [ ] 如果没有品牌合作，是否要为未来合作预留一个 `knowledge/brand_redlines/` 目录？
      我可以现在先建好 template。

### D2. 受众地域
**当前默认** (`knowledge/global_style_guide.md` §Audience):
primary = US/CA/UK/AU; spelling = American English; currency = USD/£/CA$ ok;
date format = "Nov 28" 而非 "28 Nov" 或 "11/28"。

**需要确认**：
- [ ] 如果目标受众实际是 UK-first，spelling 默认改 British English？
- [ ] 日期格式统一 American 还是按受众地域切换？当前默认是 American。

---

## E. 真 API 验证 (待授权才会跑)

### E1. 第一批 EN pack 的成本预估
一轮 Smoke (~$0)+ A-suite classify eval (~$0.05) + 1 个 EN pack 真跑 ×3 Judge
verify variance (~$1.2) ≈ **合计 $1.3**。

**需要确认**：
- [ ] 是否授权我按这个预算跑一轮，把 Judge 方差(CLAUDE.md §3.6)和
      英文化后的第一个真 pack 质量验证给你？
- [ ] 如果授权，跑哪个话题作为首测？我的推荐：
      **"Mother's Day — the things I never got to say" (regret_sting / emotional)**
      因为它是英文化改动后相对"新"的组合(L1=festival + 敏感情绪 mechanism)，
      最容易暴露问题。

### E2. Eval suite 扩建
`scripts/run_eval.py --suite classify` 当前基于 CN 的 case，英文化后可能命中率异常。
**需要确认**：
- [ ] 是否要我先用 mock 模式生成 10 个 EN fixture，再跑 classify suite 看基线？
      这块不花钱。

---

## F. 结构与 CI

### F1. `validate_knowledge.py` 放宽的边界
**当前默认**：
- 只检查 `## Scope` / `## Success patterns` 必须有(substring 匹配)
- 加了 `CATEGORY_TABOO_MARKERS = ["-specific taboos", "Mechanisms to avoid", "taboos"]` 任一即可

**需要确认**：
- [ ] 是否需要把 `## Visual notes` / `## Open questions` 也列为必需？
      我没加这两节是因为不是每个 playbook 都一定要，但如果你想强制，我可以加。

### F2. 测试 fixture
当前 `test_evaluator_catches_banned_words` 还用的是中文 fixture("想自杀的夜晚")。
**需要确认**：
- [ ] 是否要把这个测试改成英文 fixture (e.g. "nights I wanted to kms")？
      或双份都保留？我倾向双份(覆盖率 ↑)，但等你定。

---

## Completed work (一览，供你核对)

### Stage B — 代码与 prompt (all done)
- `agents/planner.py` — SYSTEM + USER 全英文 prompt，所有 free-text 字段要求英文
- `agents/generator_cards_batched.py` — SYSTEM + BATCH 全英文；加 8/14 词数约束
- `agents/generator.py` (script) — SYSTEM + USER 全英文；加"non-key_moment notes 留空"的成本约束
- `agents/reviewer.py` — SYSTEM + USER 全英文；**同时修了预存的 bug(以前让 LLM "see schema in xxx.md"，LLM 读不到文件)**，把 JSON schema 直接 inline 进 prompt
- `tools/evaluator.py` — JUDGE_SYSTEM 全英文，dimensions inline；banned_words / stale_memes / emo_words 改双语并 casefold
- `llm.py` — mock 的 `_canned_response` 改双语 regex，支持 "positions X to Y" 识别
- `memory/knowledge_loader.py` — 把唯一一条中文字符串英文化

### Stage C — Knowledge base (all done)
- `knowledge/global_style_guide.md` → v0.2 英文版，加 audience block, word count, 英文 filler 清单
- `knowledge/global_anti_patterns.md` → v0.2 英文版，敏感日期替换成英语世界版本
- `knowledge/taxonomy.md` → v0.2 英文版，例子全换
- `knowledge/categories/festival.md` → v0.2 英文版，festival scope 扩到全球
- `knowledge/categories/emotional.md` → **新建** v0.1
- `knowledge/categories/trending_event.md` → **新建** v0.1

### Stage D — Scripts / tests (all done)
- `scripts/validate_knowledge.py` → 改为 substring 匹配 heading，支持任意编号
- `scripts/seed_synthetic.py` → **重写**；`SeedSpec` dataclass；15 EN festival + 5 EN emotional + 3 EN trending + 5 legacy CN；新增 `--category` / `--include-legacy-cn` flag；payload 里带 language
- `tests/test_smoke_structure.py` → 断言语言改为英文

### 验证状态
- ✅ `APP_MODE=mock pytest -m smoke` → **33 passed**
- ✅ `python scripts/seed_synthetic.py --category all --n 5` → 运行正常
- ✅ `python scripts/seed_synthetic.py --category festival --include-legacy-cn --n 20` → 运行正常，语言 tag 正确
- ⏳ 真 API pipeline 验证 — 等待你对 E1 的授权
- ⏳ `docs/plan.md` / `docs/troubleshooting-log.md` / `README.md` — 等待 A1 的决定

---

## 回答建议格式

你可以直接回复类似：

```
A1: README 英文，plan/troubleshooting 保留中文
A2: retrieval 按 language="en" 过滤；CN seeds 清掉
A3: ✅
B1: 加 overdose / OD / thinspo；banned_words 挪到 .txt
B2: ✅，但加 era / chronically online
B3: 加 Pulse / Columbine，不加 Orange Shirt
C1: trending 阈值降到 10；比例 6:3:1
C2: ✅
C3: 先不扩
D1: 暂无合作，先建 template 目录
D2: American 默认
E1: ✅ 授权跑 Mother's Day regret_sting
E2: ✅ 先建 EN fixture
F1: ✅
F2: 双份保留
```

我按你的回答逐条落地，不做二次确认（除非遇到和现有规则冲突）。
