"""校验 knowledge/ 目录结构和 .md 文件完整性。CI 会跑这个。

检查项：
- 必需的顶层文件都存在
- 每份 category playbook 结构符合模板
- prompt_templates 有版本号
- experience_log 目录存在
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "knowledge"

REQUIRED_FILES = [
    "taxonomy.md",
    "global_style_guide.md",
    "global_anti_patterns.md",
    "metrics_calibration.md",
    "failure_library.md",
]

REQUIRED_DIRS = [
    "categories",
    "prompt_templates",
    "experience_log",
]

REQUIRED_PROMPT_TEMPLATES = [
    r"^planner\.v\d+\.md$",
    r"^generator_cards\.v\d+\.md$",
    r"^generator_script\.v\d+\.md$",
    r"^reviewer\.v\d+\.md$",
]

# Section titles are matched as substrings (after the leading "## N. "), so
# playbooks may number sections however they like as long as the headings
# are present.
CATEGORY_REQUIRED_SECTION_TITLES = [
    "Scope",
    "Success patterns",
]

CATEGORY_TABOO_MARKERS = [
    "-specific taboos",
    "Mechanisms to avoid",
    "taboos",
]


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_required_files() -> list[str]:
    errors = []
    for f in REQUIRED_FILES:
        p = KNOWLEDGE / f
        if not p.exists():
            errors.append(f"missing required file: knowledge/{f}")
        elif p.stat().st_size == 0:
            errors.append(f"required file is empty: knowledge/{f}")
    return errors


def check_required_dirs() -> list[str]:
    errors = []
    for d in REQUIRED_DIRS:
        p = KNOWLEDGE / d
        if not p.is_dir():
            errors.append(f"missing required directory: knowledge/{d}/")
    return errors


def check_prompt_templates() -> list[str]:
    errors = []
    tmpl_dir = KNOWLEDGE / "prompt_templates"
    if not tmpl_dir.is_dir():
        return ["prompt_templates/ directory missing"]

    names = [p.name for p in tmpl_dir.glob("*.md")]
    for pattern in REQUIRED_PROMPT_TEMPLATES:
        if not any(re.match(pattern, n) for n in names):
            errors.append(f"no template matching {pattern} in prompt_templates/")
    return errors


def check_categories() -> list[str]:
    errors = []
    cat_dir = KNOWLEDGE / "categories"
    if not cat_dir.is_dir():
        return ["categories/ directory missing"]

    categories = list(cat_dir.glob("*.md"))
    if not categories:
        errors.append("no category playbook found")
        return errors

    heading_re = re.compile(r"^##\s+[\w\.]+\s+(.+?)\s*$", re.MULTILINE)
    for cat_file in categories:
        content = cat_file.read_text(encoding="utf-8")
        headings = heading_re.findall(content)
        missing = [
            title for title in CATEGORY_REQUIRED_SECTION_TITLES
            if not any(title in h for h in headings)
        ]
        if missing:
            errors.append(f"{cat_file.name} missing sections: {missing}")
        # Each playbook must contain some taboo / anti-pattern section
        if not any(marker in content for marker in CATEGORY_TABOO_MARKERS):
            errors.append(
                f"{cat_file.name} missing a taboos / anti-patterns section"
            )
    return errors


def main() -> int:
    print(f"validating {KNOWLEDGE}...")

    all_errors: list[str] = []
    all_errors.extend(check_required_files())
    all_errors.extend(check_required_dirs())
    all_errors.extend(check_prompt_templates())
    all_errors.extend(check_categories())

    if all_errors:
        print()
        for e in all_errors:
            _fail(e)
        print(f"\n{len(all_errors)} error(s)")
        return 1

    print("knowledge base: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
