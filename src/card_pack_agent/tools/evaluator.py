"""Evaluator — 发布前守门员。

**这不是 agent**。它是一组 rule check + 一次 LLM-as-judge 调用，返回 PASS/WARN/FAIL。
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import structlog

from ..config import settings
from ..llm import LLMRole, llm
from ..memory.knowledge_loader import knowledge
from ..schemas import (
    CardPrompt,
    EvaluatorIssue,
    EvaluatorReport,
    EvaluatorVerdict,
    Pack,
)

log = structlog.get_logger()


# --- Rule-based checks ---

# Placeholder banned words. Production list lives in knowledge/_lexicon/banned_words.txt.
_DEFAULT_BANNED_WORDS = [
    "自杀", "自残", "割腕", "跳楼", "上吊",
    # ... extend via lexicon file
]

_STALE_MEMES = ["yyds", "绝绝子", "我哭死", "破防了"]  # time-sensitive, review quarterly


def _load_banned_words() -> list[str]:
    lex = settings.knowledge_path / "_lexicon" / "banned_words.txt"
    if lex.exists():
        return [w.strip() for w in lex.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
    return _DEFAULT_BANNED_WORDS


def check_banned_words(pack: Pack) -> list[EvaluatorIssue]:
    """扫卡贴 text_overlay_hint 和 script shots 的 text_overlay.content。"""
    banned = _load_banned_words()
    issues: list[EvaluatorIssue] = []

    for card in pack.cards:
        if card.text_overlay_hint:
            content = card.text_overlay_hint.content_suggestion
            for w in banned:
                if w in content:
                    issues.append(EvaluatorIssue(
                        code="banned_word_detected",
                        severity=EvaluatorVerdict.FAIL,
                        message=f"banned word '{w}' in card overlay",
                        location=f"card:{card.position}",
                    ))

    for shot in pack.script.shots:
        if shot.text_overlay:
            for w in banned:
                if w in shot.text_overlay.content:
                    issues.append(EvaluatorIssue(
                        code="banned_word_detected",
                        severity=EvaluatorVerdict.FAIL,
                        message=f"banned word '{w}' in shot text",
                        location=f"shot:{shot.position}",
                    ))
    return issues


def check_structure(pack: Pack) -> list[EvaluatorIssue]:
    """50 张结构完整性检查。"""
    issues: list[EvaluatorIssue] = []
    expected = pack.strategy.structure.total_cards
    actual = len(pack.cards)
    if actual != expected:
        issues.append(EvaluatorIssue(
            code="card_count_mismatch",
            severity=EvaluatorVerdict.FAIL,
            message=f"expected {expected} cards, got {actual}",
        ))
    positions = [c.position for c in pack.cards]
    if positions != list(range(1, len(pack.cards) + 1)):
        issues.append(EvaluatorIssue(
            code="card_position_not_sequential",
            severity=EvaluatorVerdict.FAIL,
            message="card positions must be 1..N sequential",
        ))
    if len(pack.script.shots) != actual:
        issues.append(EvaluatorIssue(
            code="script_shot_count_mismatch",
            severity=EvaluatorVerdict.FAIL,
            message=f"script has {len(pack.script.shots)} shots, expected {actual}",
        ))
    return issues


def check_visual_duplication(pack: Pack, max_near_duplicates: int = 3) -> list[EvaluatorIssue]:
    """朴素检查：卡贴 prompt 完全相同或高度相似。

    真实版本应用向量相似度；这里先 naive 基于 token overlap。
    """
    issues: list[EvaluatorIssue] = []

    def normalize(p: str) -> frozenset[str]:
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", p.lower())
        return frozenset(tokens)

    signatures = [(c.position, normalize(c.prompt)) for c in pack.cards]
    dup_counter: Counter[frozenset[str]] = Counter(s for _, s in signatures)
    for sig, count in dup_counter.items():
        if count > max_near_duplicates:
            positions = [p for p, s in signatures if s == sig]
            issues.append(EvaluatorIssue(
                code="card_visual_duplication",
                severity=EvaluatorVerdict.FAIL,
                message=f"{count} cards with near-identical prompts",
                location=f"cards:{positions}",
            ))
    return issues


def check_stale_memes(pack: Pack) -> list[EvaluatorIssue]:
    issues = []
    for shot in pack.script.shots:
        if shot.text_overlay:
            for meme in _STALE_MEMES:
                if meme in shot.text_overlay.content:
                    issues.append(EvaluatorIssue(
                        code="stale_meme_detected",
                        severity=EvaluatorVerdict.WARN,
                        message=f"stale meme '{meme}'",
                        location=f"shot:{shot.position}",
                    ))
    return issues


def check_emotional_keyword_saturation(pack: Pack, window: int = 3) -> list[EvaluatorIssue]:
    """连续 window 张出现"哭/泪/破防"类词 → warn."""
    emo_words = ["哭", "泪", "破防", "狠狠", "心痛"]
    hit_positions: list[int] = []
    for card in pack.cards:
        if card.text_overlay_hint:
            if any(w in card.text_overlay_hint.content_suggestion for w in emo_words):
                hit_positions.append(card.position)
    # detect runs of length >= window
    issues = []
    runs = _consecutive_runs(hit_positions)
    for run in runs:
        if len(run) >= window:
            issues.append(EvaluatorIssue(
                code="excessive_emotional_keywords",
                severity=EvaluatorVerdict.WARN,
                message=f"{len(run)} consecutive emotional keywords",
                location=f"cards:{run}",
            ))
    return issues


def _consecutive_runs(positions: list[int]) -> list[list[int]]:
    if not positions:
        return []
    positions = sorted(set(positions))
    runs, cur = [], [positions[0]]
    for p in positions[1:]:
        if p == cur[-1] + 1:
            cur.append(p)
        else:
            runs.append(cur)
            cur = [p]
    runs.append(cur)
    return runs


# --- LLM judge ---

JUDGE_SYSTEM = """你是卡贴包质量评判 Agent。接收一个生成完的 pack（strategy + cards + script），给出 1-5 打分。

评分维度（每项 1-5）：
- style_consistency: 50 张视觉风格是否一致
- structural_integrity: 是否遵守 strategy 的 segment 结构
- rule_adherence: 是否遵守 category playbook
- anti_pattern_clean: 是否规避 anti_patterns
- internal_dedup: 视觉/文案是否过度重复

必须输出严格 JSON：
{
  "overall_score": <float>,
  "dimensions": {"style_consistency": <float>, ...},
  "comments": "<一句话总结>"
}
"""


def judge_with_llm(pack: Pack) -> dict[str, float]:
    """调用 LLM-as-judge 打分。"""
    user = f"""# Strategy
{pack.strategy.model_dump_json()}

# Cards (first 5 and last 5 for brevity)
{[c.model_dump() for c in pack.cards[:5]]}
...
{[c.model_dump() for c in pack.cards[-5:]]}

# Script (first 3 shots)
{[s.model_dump() for s in pack.script.shots[:3]]}
"""
    resp = llm.complete_json(role=LLMRole.JUDGE, system=JUDGE_SYSTEM, user=user)
    return resp.get("dimensions", {}) | {"overall_score": resp.get("overall_score", 0.0)}


# --- Orchestration ---

def evaluate(pack: Pack, *, run_judge: bool = True) -> EvaluatorReport:
    """Run all checks and return combined report."""
    all_issues: list[EvaluatorIssue] = []
    all_issues.extend(check_banned_words(pack))
    all_issues.extend(check_structure(pack))
    all_issues.extend(check_visual_duplication(pack))
    all_issues.extend(check_stale_memes(pack))
    all_issues.extend(check_emotional_keyword_saturation(pack))

    judge_scores: dict[str, float] = {}
    if run_judge:
        try:
            judge_scores = judge_with_llm(pack)
            # Treat judge score < 2.5 as FAIL, 2.5-3.5 as WARN
            overall = judge_scores.get("overall_score", 5.0)
            if overall < 2.5:
                all_issues.append(EvaluatorIssue(
                    code="judge_low_score",
                    severity=EvaluatorVerdict.FAIL,
                    message=f"judge overall_score={overall}",
                ))
            elif overall < 3.5:
                all_issues.append(EvaluatorIssue(
                    code="judge_mediocre_score",
                    severity=EvaluatorVerdict.WARN,
                    message=f"judge overall_score={overall}",
                ))
        except Exception as e:
            log.warning("evaluator.judge_failed", error=str(e))

    # Determine verdict
    has_fail = any(i.severity == EvaluatorVerdict.FAIL for i in all_issues)
    has_warn = any(i.severity == EvaluatorVerdict.WARN for i in all_issues)
    verdict = (
        EvaluatorVerdict.FAIL if has_fail
        else EvaluatorVerdict.WARN if has_warn
        else EvaluatorVerdict.PASS
    )

    return EvaluatorReport(verdict=verdict, issues=all_issues, judge_scores=judge_scores)
