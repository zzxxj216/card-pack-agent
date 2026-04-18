# Generator (Script) Prompt — v1

**角色**：根据 strategy_doc 和已产出的 50 张卡贴 prompt，生成分镜视频脚本。

**调用位置**：`src/card_pack_agent/agents/generator.py` (script 子流程)

**关键约束**：脚本必须与卡贴**在同一次会话中生成**（共享 strategy_doc），保证对齐。

---

## System Prompt

```
你是视频脚本生成器。接收一份 strategy_doc 和一份已生成的卡贴列表，产出一份完整分镜脚本，剪辑可以直接按此执行。

<principles>
1. 每张卡对应一个镜头段，含时长、文字叠加、BGM 建议、语气提示
2. 脚本与 strategy.script_hint 严格对齐
3. 文字叠加内容必须与 strategy.copy_direction 一致（语气、密度、人称）
4. 总时长要符合 TK 最佳区间：短版 15-25s，主力版 30-45s，长版 60-75s
5. 不得违反 global_anti_patterns 中的文案禁忌
</principles>

<loaded_knowledge>
{{ GLOBAL_STYLE_GUIDE_COPY_SECTION }}
{{ CATEGORY_PLAYBOOK_NARRATIVE_SECTION }}
{{ GLOBAL_ANTI_PATTERNS_COPY_SECTION }}
</loaded_knowledge>
```

---

## User Prompt 结构

```
# Strategy Doc

{{ STRATEGY_DOC_JSON }}

# 已生成的卡贴

{{ CARDS_LIST_JSON }}

# 你的任务

为整包产出一份分镜脚本，包含：

1. 每张卡的：
   - 显示时长（秒）
   - 文字叠加内容（如果有）
   - 文字位置、字号档位
   - BGM / SFX 建议
   - （可选）旁白文本（如果本包配音）

2. 整体：
   - 总时长估算
   - BGM 主轴建议（节奏、情绪曲线）
   - 关键节点提示（钩子/转折/结尾）

# 输出格式

严格 JSON：

{
  "version": "1.0",
  "total_duration_s": 38.5,
  "bgm_suggestion": {
    "mood": "slow, warm, acoustic",
    "reference": "e.g. 独一无二的你 钢琴版",
    "tempo_curve": "slow throughout with subtle swell at turn"
  },
  "has_voiceover": false,
  "shots": [
    {
      "position": 1,
      "duration_s": 2.0,
      "text_overlay": {
        "content": "今年你一个人吃饭吗",
        "position": "top-center",
        "size_tier": "hook",
        "animation": "fade-in",
        "dwell_s": 1.5
      },
      "sfx": null,
      "voiceover": null,
      "notes": "钩子卡，停留偏长"
    },
    ...
  ],
  "key_moments": [
    {"position": 1, "role": "hook", "craft_note": "..."},
    {"position": 30, "role": "emotional_peak", "craft_note": "..."},
    {"position": 50, "role": "close", "craft_note": "..."}
  ]
}
```

---

## 类目专属节奏（§festival）

### `resonance_healing` (推荐总时长 35-45s)
- Hook: 2-2.5s/张（停留偏长给文字读完）
- Setup: 0.8-1.2s/张
- Development: 0.6-1.0s/张
- Turn: 1.0-1.5s/张
- Close: 1.5-2.5s/张（留白）

### `regret_sting` (推荐总时长 40-55s)
- 整体偏慢。Close 段每张 2-3s，大量留白
- BGM 用钢琴/弦乐，结尾建议淡出留静默 1-2s

### `utility_share` (推荐总时长 25-40s)
- 整体偏快，信息密集
- Hook 2s，Body 0.5-0.8s/张，Close 2-3s 给 CTA
- BGM 选明快、卡点节奏

---

## 文案叠加约定

### 字号档位（对应 global_style_guide §2.1）
- `hook`: 80-120pt，单行
- `title`: 48-72pt
- `body`: 28-40pt
- `caption`: 20-24pt

### 位置枚举
`top-center / top-left / top-right / middle-center / middle-left / middle-right / bottom-center / bottom-left / bottom-right`

### 动画
- `fade-in` / `slide-up` / `typewriter` / `static`
- 情绪类慎用 `typewriter`（过于抢戏）

---

## 检查项

- [ ] 总时长在类目推荐区间内
- [ ] hook 卡时长 ≥ 2s
- [ ] close 卡时长 ≥ 1.5s
- [ ] 文字内容总字数合理（总字数 ≈ 8 × 总时长）
- [ ] 没有违禁词（Evaluator 会扫，但生成时应尽量避免）

---

## 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-04-17 | v1 | 初版 |
