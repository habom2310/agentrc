"""
Token budget auditor for agentrc.
Monitors session boot footprint to guarantee ultra-lean startup context.
"""

from pathlib import Path
import re
from agentrc.detector import get_home_dir, get_hub_dir

ESTIMATED_CHARS_PER_TOKEN = 4.0
TARGET_BUDGET = 2000


def estimate_tokens(text_or_chars: str | int) -> int:
    if isinstance(text_or_chars, int):
        return int(text_or_chars / ESTIMATED_CHARS_PER_TOKEN)
    if not text_or_chars:
        return 0
    return int(len(text_or_chars.strip()) / ESTIMATED_CHARS_PER_TOKEN)


def audit_budget() -> dict:
    hub = get_hub_dir()
    rules_dir = hub / "rules"
    skills_dir = hub / "skills"

    breakdown = {}

    # 1. Core Rules (Universal rules loaded across all platforms)
    rules_chars = 0
    if rules_dir.is_dir():
        for f in ["common.md", "code-tools.md", "handoffs.md"]:
            p = rules_dir / f
            if p.is_file():
                rules_chars += len(p.read_text(encoding="utf-8", errors="replace"))

    breakdown["core_rules_tokens"] = estimate_tokens(rules_chars)

    # 2. Skills Registry (Progressive disclosure: YAML frontmatter name + description only)
    skill_desc_chars = 0
    skill_count = 0
    if skills_dir.is_dir():
        for s in skills_dir.iterdir():
            if s.is_dir():
                skill_md = s / "SKILL.md"
                if skill_md.is_file():
                    skill_count += 1
                    txt = skill_md.read_text(encoding="utf-8", errors="replace")
                    # Extract name and description lines only
                    if txt.startswith("---"):
                        parts = txt.split("---", 2)
                        if len(parts) >= 3:
                            for line in parts[1].splitlines():
                                sline = line.strip()
                                if sline.startswith(("name:", "description:")):
                                    skill_desc_chars += len(sline)
    breakdown["skills_count"] = skill_count
    breakdown["skills_registry_tokens"] = estimate_tokens(skill_desc_chars)

    total = breakdown["core_rules_tokens"] + breakdown["skills_registry_tokens"]
    breakdown["total_boot_tokens"] = total
    breakdown["budget"] = TARGET_BUDGET
    breakdown["status"] = "PASS (LEAN)" if total <= TARGET_BUDGET else "EXCEEDED"

    return breakdown
