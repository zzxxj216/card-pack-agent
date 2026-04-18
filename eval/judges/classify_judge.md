# Classification Judge Prompt

**用途**：当 A suite 遇到 gold label 不确定的边界案例，人工评审时对照此 rubric。

也可作为 Planner 的分类 cross-check（Phase 3+ 可选）。

---

## 判定流程

1. 读取话题
2. 按 `knowledge/taxonomy.md` §L1 的 7 个桶逐一判定"主导叙事动机"
3. 如果 2 个以上 L1 都可能 → 看"时间锚点"是否是核心（是 → `festival`）
4. 确定 L1 后，按 `taxonomy.md` §L2 的 7 个机制判定"传播路径"
5. 记录 reasoning（一句话即可）

---

## 常见边界案例

| 话题 | 直觉 L1 | 正确 L1 | 理由 |
|---|---|---|---|
| "春节催婚话术" | festival | knowledge | 工具/方法论主导，节日只是背景 |
| "七夕热搜第一那个瓜" | festival | trending_event | 事件驱动，节日只是时间标 |
| "母亲节给妈妈打电话" (故事) | festival | festival | 节日是叙事核心 |
| "清明节扫墓的十个注意事项" | festival | knowledge | utility 主导 |
| "中秋月亮为什么特别圆" | festival | knowledge | 科普主导 |

---

## L2 判定小指南

| 关键词出现 | 强烈倾向 L2 |
|---|---|
| "后悔""当时""来不及""再也" | `regret_sting` |
| "你是不是也" "原来不止我" | `resonance_healing` |
| "清单""指南""十个""必看" | `utility_share` |
| "愿你""祝" + 温和语气 | `blessing_ritual` |
| "别人...而我..." | `conflict_tension` |
| "以为是A其实是B" | `contrast_twist` |
| 格言/箴言/结论式 | `aphorism_lesson` |

关键词只是信号，最终判定看整体叙事动机。

---

## 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-04-17 | v1 | 初版 |
