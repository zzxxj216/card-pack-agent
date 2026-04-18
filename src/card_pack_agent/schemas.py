"""系统内流转的所有数据模型。与 knowledge/prompt_templates/*.md 的 schema 对齐。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


# --- Taxonomy enums (mirrors knowledge/taxonomy.md) ---

class L1(str, Enum):
    FESTIVAL = "festival"
    TRENDING_EVENT = "trending_event"
    EMOTIONAL = "emotional"
    KNOWLEDGE = "knowledge"
    CHARACTER = "character"
    RELATIONSHIP = "relationship"
    GROWTH = "growth"


class L2(str, Enum):
    RESONANCE_HEALING = "resonance_healing"
    REGRET_STING = "regret_sting"
    CONTRAST_TWIST = "contrast_twist"
    BLESSING_RITUAL = "blessing_ritual"
    UTILITY_SHARE = "utility_share"
    APHORISM_LESSON = "aphorism_lesson"
    CONFLICT_TENSION = "conflict_tension"


class Tier(str, Enum):
    VIRAL = "viral"
    GOOD = "good"
    MID = "mid"
    BAD = "bad"


class SegmentRole(str, Enum):
    HOOK = "hook"
    SETUP = "setup"
    DEVELOPMENT = "development"
    TURN = "turn"
    CLOSE = "close"


# --- Input ---

class TopicInput(BaseModel):
    """Planner 的原始输入。"""

    raw_topic: str
    input_type: str = "topic"  # topic | material | url | keyword
    extra_context: str | None = None


# --- Strategy doc (Planner → Generator) ---

class Classification(BaseModel):
    l1: L1
    l2: L2
    l3: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ReferencedCase(BaseModel):
    case_id: str
    relevance: str
    borrow: str


class Segment(BaseModel):
    range: tuple[int, int]
    role: SegmentRole
    notes: str = ""


class PackStructure(BaseModel):
    total_cards: int = 50
    segments: list[Segment]


class VisualDirection(BaseModel):
    palette: list[str]
    main_subject: str
    composition_note: str = ""
    style_anchor: str


class CTA(BaseModel):
    intensity: str  # none | soft | hard
    example: str = ""


class CopyDirection(BaseModel):
    tone: str
    text_density: str  # minimal | medium | heavy
    pronoun: str = "你"
    hook_type: str
    cta: CTA


class ScriptHint(BaseModel):
    narrative_arc: str
    pacing_note: str


class StrategyDoc(BaseModel):
    """Planner 的结构化输出。下游 Generator 的唯一输入契约。"""

    model_config = ConfigDict(use_enum_values=True)

    version: str = "1.0"
    topic: str
    classification: Classification
    referenced_cases: list[ReferencedCase] = Field(default_factory=list)
    structure: PackStructure
    visual_direction: VisualDirection
    copy_direction: CopyDirection
    avoid: list[str] = Field(default_factory=list)
    script_hint: ScriptHint


class ClarificationRequest(BaseModel):
    """Planner 判定无法继续时的输出。"""

    clarification_needed: bool = True
    questions: list[str]


# --- Cards (Generator → Evaluator / downstream) ---

class TextOverlayHint(BaseModel):
    content_suggestion: str
    position: str  # top-center, bottom-center, ...
    size_tier: str  # hook | title | body | caption


class CardPrompt(BaseModel):
    position: int  # 1-indexed
    segment: SegmentRole
    prompt: str
    negative_prompt: str
    composition_note: str = ""
    text_overlay_hint: TextOverlayHint | None = None


# --- Script (Generator → downstream) ---

class TextOverlay(BaseModel):
    content: str
    position: str
    size_tier: str
    animation: str = "fade-in"
    dwell_s: float = 1.5


class BGMSuggestion(BaseModel):
    mood: str
    reference: str = ""
    tempo_curve: str = ""


class KeyMoment(BaseModel):
    position: int
    role: str
    craft_note: str


class Shot(BaseModel):
    position: int
    duration_s: float
    text_overlay: TextOverlay | None = None
    sfx: str | None = None
    voiceover: str | None = None
    notes: str = ""


class Script(BaseModel):
    version: str = "1.0"
    total_duration_s: float
    bgm_suggestion: BGMSuggestion
    has_voiceover: bool = False
    shots: list[Shot]
    key_moments: list[KeyMoment] = Field(default_factory=list)


# --- Pack (aggregated, Generator's full output) ---

class Pack(BaseModel):
    """一次完整生成的产物。"""

    pack_id: UUID = Field(default_factory=uuid4)
    topic: str
    strategy: StrategyDoc
    cards: list[CardPrompt]
    script: Script
    # Populated later in the pipeline:
    card_image_urls: dict[int, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- Evaluator ---

class EvaluatorVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class EvaluatorIssue(BaseModel):
    code: str  # e.g. "banned_word_detected"
    severity: EvaluatorVerdict
    message: str
    location: str | None = None  # e.g. "card:7" or "script:shot:12"


class EvaluatorReport(BaseModel):
    verdict: EvaluatorVerdict
    issues: list[EvaluatorIssue] = Field(default_factory=list)
    judge_scores: dict[str, float] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict != EvaluatorVerdict.FAIL


# --- Metrics (TK results) ---

class Metrics(BaseModel):
    views: int = 0
    completion_rate: float = 0.0
    like_rate: float = 0.0
    share_rate: float = 0.0
    comment_rate: float = 0.0
    save_rate: float = 0.0
    # Human-tagged signals
    most_memorable_positions: list[int] = Field(default_factory=list)
    dominant_comment_sentiment: str | None = None
    comment_mentions: list[str] = Field(default_factory=list)


class CaseRecord(BaseModel):
    """Postgres 里一行完整记录。"""

    pack_id: UUID
    topic: str
    topic_l1: L1
    topic_l2: L2
    topic_l3: list[str]
    strategy_doc: StrategyDoc
    cards: list[CardPrompt]
    script: Script
    metrics: Metrics | None = None
    tier: Tier | None = None
    extracted_patterns: list[dict[str, Any]] = Field(default_factory=list)
    is_exploration: bool = False
    is_synthetic: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- Reviewer output ---

class ExtractedRule(BaseModel):
    id: str
    polarity: str  # positive | negative
    rule: str
    evidence_strength: str  # strong | weak
    evidence_packs: list[str]
    scope: str
    target_file: str


class ReviewReport(BaseModel):
    window: dict[str, str]
    sample_size: dict[str, int]
    per_pack_attribution: list[dict[str, Any]]
    cross_pack_contrast: dict[str, list[dict[str, Any]]]
    extracted_rules: list[ExtractedRule]
    open_questions: list[str]
    summary_for_humans: str
