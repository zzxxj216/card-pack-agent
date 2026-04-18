# Metrics Calibration — Tier 定义与校准

---

## Tier 定义

卡包表现分 4 档，基于**账号自身历史分布的分位数**，不是绝对阈值。

| Tier | 含义 | 推荐阈值（P90/P60/P30 起步） |
|---|---|---|
| `viral` | 爆款，远超账号均值 | ≥ P90 |
| `good` | 表现良好，贡献主力流量 | P60 ~ P90 |
| `mid` | 平均水平 | P30 ~ P60 |
| `bad` | 低于预期，需归因 | < P30 |

**关键**：这是**相对**档位。不要跨账号比较，也不要用绝对数字（比如"10万播放就是 good"）。

---

## 校准节奏

### 初始期（< 50 个样本）
- 档位使用 **合成 baseline**：基于同领域公开可见的头部账号水平 + 账号自身目标
- 每新增 10 个包手动 review 一次档位是否需要调整

### 成熟期（≥ 50 个样本）
- 每 50 个新样本自动重算 P90/P60/P30
- 脚本 `scripts/recalibrate_tiers.py` 输出建议新阈值
- 人工确认后写入本文档，更新数据库

---

## 输入指标

从 TK 收集（前期手填，后期 API）：

| 指标 | 字段名 | 说明 |
|---|---|---|
| 播放量 | `views` | 24h 内 + 7d 累计 |
| 完播率 | `completion_rate` | 完整播放次数 / 播放量 |
| 点赞率 | `like_rate` | 点赞 / 播放量 |
| 分享率 | `share_rate` | 分享 / 播放量 |
| 评论率 | `comment_rate` | 评论 / 播放量 |
| 收藏率 | `save_rate` | 收藏 / 播放量 |

另含**人工信号**（降低归因难度）：
- `most_memorable_cards`: 运营填写印象最深的前 3 张（position）
- `dominant_comment_sentiment`: positive / negative / mixed
- `comment_mentions`: 评论中频繁被提到的卡 position 或关键词

---

## 综合评分公式（v0.1）

先手写一个朴素加权分，后期根据 correlation eval 调整：

```
score = 0.35 * zscore(completion_rate)
      + 0.20 * zscore(share_rate)
      + 0.15 * zscore(save_rate)
      + 0.15 * zscore(like_rate)
      + 0.10 * zscore(comment_rate)
      + 0.05 * zscore(views)
```

**为什么 completion 权重最高**：TK 推荐系统的核心信号。
**为什么 views 权重最低**：views 是果不是因，会被推荐信号放大造成反馈循环。

tier 按 `score` 的分位数打，不是按单一指标。

---

## 当前阈值（账号特定，待填）

> 初始化时以下都是占位，跑完前 30 个包后 recalibrate

```yaml
tier_thresholds:
  viral: null   # P90
  good:  null   # P60
  mid:   null   # P30
last_calibrated_at: null
sample_size: 0
```

---

## 归因规则（单卡级别）

爆款里也有拖后腿的卡，差包里也可能有好卡。不做单卡归因的话，坏模式会被当成功模式学进去。

归因信号优先级：
1. `most_memorable_cards`（人工填）→ 最强信号
2. 评论中被提到的 position → 次强
3. 同话题 top/bottom 包的位置对比 → 兜底

`single_card_tier` 不等于 `pack_tier`。Reviewer 要分开记录。

---

## Correlation Eval（季度任务）

每季度随机抽 30 个真实发布的包：
1. Evaluator 给 offline 分数
2. 真实数据给 tier
3. 计算相关系数

```
if correlation < 0.5:
    raise Alert("Offline scoring has drifted, recalibrate judges")
```

结果记入 `experience_log/correlation_YYYY_QN.md`。

---

## 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-04-17 | v0.1 | 初版 |
