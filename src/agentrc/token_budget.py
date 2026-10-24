"""
Token budget auditor for agentrc.
Monitors session boot footprint to guarantee ultra-lean startup context.
"""

from pathlib import Path
import re
from agentrc.detector import get_home_dir, get_hub_dir

ESTIMATED_CHARS_PER_TOKEN = 4.0
TARGET_BUDGET = 2000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return int(len(text.strip()) / ESTIMATED_CHARS_PER_TOKEN)


def audit_budget() -> dict:
    hub = get_hub_dir()
    rules_dir = hub / "rules"
    skills_dir = hub / "skills"

    breakdown = {}

    # 1. Rules
    rules_chars = 0
    if rules_dir.is_dir():
        for f in rules_dir.glob("*.md"):
            rules_chars += len(f.read_text(encoding="utf-8", errors="replace"))
        for f in (rules_dir / "overrides").glob("*.md"):
            rules_chars += len(f.read_text(encoding="utf-8", errors="replace"))
    breakdown["core_rules_tokens"] = estimate_tokens(" " * rules_chars)

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
                    # Extract frontmatter only
                    if txt.startswith("---"):
                        parts = txt.split("---", 2)
                        if len(parts) >= 3:
                            skill_desc_chars += len(parts[1])
    breakdown["skills_count"] = skill_count
    breakdown["skills_registry_tokens"] = estimate_tokens(" " * skill_desc_chars)

    total = breakdown["core_rules_tokens"] + breakdown["skills_registry_tokens"]
    breakdown["total_boot_tokens"] = total
    breakdown["budget"] = TARGET_BUDGET
    breakdown["status"] = "PASS (LEAN)" if total <= TARGET_BUDGET else "EXCEEDED"

    return breakdown
