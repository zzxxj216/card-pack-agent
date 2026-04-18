"""加载 knowledge/ 下的 .md 文档。

使用模式：
    knowledge.global_context()         → 拼好的全局 system prompt 片段
    knowledge.for_category("festival") → 加载对应 category playbook
    knowledge.prompt_template("planner", version=1)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..config import settings


class KnowledgeLoader:
    """读 .md 文件。所有路径都从 settings.knowledge_path 算起。"""

    def __init__(self, base: Path | None = None) -> None:
        self.base = base or settings.knowledge_path

    # --- Low-level ---

    def _read(self, rel: str) -> str:
        path = self.base / rel
        if not path.exists():
            raise FileNotFoundError(f"knowledge file missing: {path}")
        return path.read_text(encoding="utf-8")

    # --- Global chunks (all agents load these) ---

    @lru_cache(maxsize=1)
    def taxonomy(self) -> str:
        return self._read("taxonomy.md")

    @lru_cache(maxsize=1)
    def global_style_guide(self) -> str:
        return self._read("global_style_guide.md")

    @lru_cache(maxsize=1)
    def global_anti_patterns(self) -> str:
        return self._read("global_anti_patterns.md")

    @lru_cache(maxsize=1)
    def metrics_calibration(self) -> str:
        return self._read("metrics_calibration.md")

    @lru_cache(maxsize=1)
    def failure_library(self) -> str:
        return self._read("failure_library.md")

    def global_context(self) -> str:
        """拼成一段给 system prompt 用。注意 token 预算，建议总量 < 5k token。"""
        return "\n\n---\n\n".join([
            "# TAXONOMY\n\n" + self.taxonomy(),
            "# GLOBAL STYLE GUIDE\n\n" + self.global_style_guide(),
            "# GLOBAL ANTI-PATTERNS\n\n" + self.global_anti_patterns(),
        ])

    # --- Category-specific (loaded on demand based on classification) ---

    def for_category(self, l1: str) -> str:
        """加载对应类目的 playbook。Planner 分类后调用。"""
        try:
            return self._read(f"categories/{l1}.md")
        except FileNotFoundError:
            # Graceful: some L1 may not have a playbook yet
            return f"# Category {l1} (playbook not yet written)"

    # --- Prompt templates ---

    def prompt_template(self, name: str, version: int = 1) -> str:
        return self._read(f"prompt_templates/{name}.v{version}.md")

    # --- Experience log (append-only) ---

    def list_experience_logs(self) -> list[Path]:
        log_dir = self.base / "experience_log"
        if not log_dir.exists():
            return []
        return sorted(log_dir.glob("*.md"))

    def recent_experiences_summary(self, max_files: int = 3) -> str:
        """返回最近 N 份 experience_log 的拼接（用于 Planner context）。

        注意：大概率内容很多，调用方应自行决定是否截断或摘要。
        """
        logs = self.list_experience_logs()[-max_files:]
        if not logs:
            return "(暂无已合并的经验记录)"
        return "\n\n---\n\n".join(p.read_text(encoding="utf-8") for p in logs)

    # --- Write (only to experience_log/) ---

    def write_experience_log(self, filename: str, content: str) -> Path:
        """Reviewer 产出写入点。只允许写到 experience_log/。"""
        if "/" in filename or ".." in filename:
            raise ValueError(f"invalid filename: {filename}")
        target = self.base / "experience_log" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target


# Module-level singleton
knowledge = KnowledgeLoader()
