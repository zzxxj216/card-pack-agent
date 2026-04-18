# Taxonomy — 三层分类定义

**最后更新**：v0.1 — 初版，仅覆盖节日类的详细定义。其他一级类目待后续 phase 补齐。

---

## 设计原则

三层是**正交维度**，不是层级包含关系。一个卡包同时持有三个维度的标签，任意维度可独立过滤和检索。

检索时推荐 two-stage：先按 L2（叙事机制）硬过滤，再在候选集内用 L1 向量排序，L3 作为生成约束。

---

## L1 · 内容域（Content Domain）

| Tag | 定义 | 包含 | 不包含（归别处） |
|---|---|---|---|
| `festival` | 以节日/纪念日/日历特殊日为核心叙事 | 传统节日、洋节、官方假期、生日纪念日 | 节日期间发生的热点事件（→ `trending_event`） |
| `trending_event` | 以当下热点/新闻/公共事件为核心 | 突发新闻、社会事件、明星事件、体育赛事 | 评论性解读（→ `emotional`) |
| `emotional` | 以情绪/心理状态为核心，不依赖外部事件 | 孤独、焦虑、疲惫、治愈、共鸣类 | 由具体事件触发的情绪（→ 事件类） |
| `knowledge` | 以知识/技能/信息为核心 | 科普、教程、冷知识、榜单 | 个人经验分享（→ `growth`） |
| `character` | 以具体人物（真实或虚构）为核心 | 人物传记、角色解读、历史人物 | 人物引发的新闻（→ `trending_event`） |
| `relationship` | 以人与人关系为核心 | 亲情、友情、爱情、职场关系 | 节日中的亲情叙事（→ `festival`） |
| `growth` | 以个人成长/经验/反思为核心 | 人生教训、阶段感悟、转变故事 | 方法论教程（→ `knowledge`） |

**归属争议处理**：当一个话题同时属于多个 L1 时，选**最主导的叙事动机**。例：母亲节发一个"后悔没早点理解妈妈"的故事，主导是节日（→ `festival`）；平时发同样故事，主导是关系（→ `relationship`）。

---

## L2 · 叙事机制（Narrative Mechanism）

这层决定**爆款的结构路径**，比 L1 更能预测表现。

| Tag | 核心动力 | 典型开头 | 典型结尾 |
|---|---|---|---|
| `resonance_healing` | 共鸣治愈：让人感到被理解、被温柔相待 | "你是不是也..." | "原来不止我一个人" |
| `regret_sting` | 遗憾刺痛：触发怀念/失去/来不及感 | "如果当时..." | "再也回不去了" |
| `contrast_twist` | 反差反转：先铺垫再颠覆预期 | 看似 A... | "其实是 B" |
| `blessing_ritual` | 祝福仪式：直接祝福，温和正能量 | "愿你..." | "祝..." |
| `utility_share` | 实用转发：工具价值/攻略/清单 | "送礼清单" | "收藏转发" |
| `aphorism_lesson` | 金句教训：结论式、格言式 | "这就是..." | "记住这一点" |
| `conflict_tension` | 冲突张力：节日/现实/预期间的矛盾 | "别人在..." / "而我..." | "这就是生活" |

**一个卡包可能混合机制**，但应有一个**主导机制**。标签填主导的那个。

---

## L3 · 执行属性（Execution Attributes）

枚举标签集合，一个包可打多个。不强制分类，用于生成时的约束和检索的精细过滤。

### 色调
- `palette:warm` `palette:cool` `palette:neutral` `palette:high_contrast`

### 文本密度
- `text:minimal`（单句/短词为主）
- `text:medium`（2-3 行）
- `text:heavy`（段落级）

### 视觉主体
- `subject:single_object`（单一意象：一杯茶、一张椅子）
- `subject:single_person` `subject:multi_person`
- `subject:scene`（场景无人物）
- `subject:text_only`（纯字体设计）

### 节奏
- `pace:slow`（长停留、情绪沉浸）
- `pace:medium`
- `pace:fast`（快切、信息密集）

### CTA 强度
- `cta:none` `cta:soft`（评论引导）`cta:hard`（转发/收藏/关注）

### 风格感
- `style:realistic`（实拍感）
- `style:illustration`（插画）
- `style:collage`（拼贴）
- `style:typographic`（字体主导）

---

## 完整示例

### 中秋节 · 独在异乡的年轻人
```yaml
l1: festival
l2: resonance_healing
l3:
  - palette:warm
  - text:minimal
  - subject:single_object    # 一碗汤、一块月饼
  - pace:slow
  - cta:soft
  - style:realistic
```

### 母亲节 · 子欲养而亲不待
```yaml
l1: festival
l2: regret_sting
l3:
  - palette:warm
  - text:medium
  - subject:scene            # 空椅子、老照片
  - pace:slow
  - cta:none
  - style:realistic
```

### 圣诞节 · 送礼攻略
```yaml
l1: festival
l2: utility_share
l3:
  - palette:high_contrast
  - text:heavy
  - subject:single_object    # 礼物摆拍
  - pace:fast
  - cta:hard
  - style:typographic
```

---

## 标注流程（Phase 0 必做）

1. 每个新话题/卡包由**两人独立打标**
2. L1 + L2 组合一致 → 直接入库
3. 不一致 → 当场讨论，更新本文件的边界定义（永远别留歧义）
4. 每月 review 一次标签分布，过稀疏的标签考虑合并

---

## 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-04-17 | v0.1 | 初版，L1/L2 定义完整，L3 枚举集合 |
