"""
SessionStart lifecycle hook for agentrc.
Fast (<10ms), headless, non-blocking drift synchronization.
"""

from pathlib import Path
import sys
from agentrc.detector import get_home_dir, get_hub_dir
from agentrc.projector import project_gemini_rules, project_claude_rules, project_subagents


def run_session_start_hook() -> int:
    """
    Executes at AI session startup.
    Non-blocking, non-interactive fail-safe.
    """
    hub = get_hub_dir()
    if not (hub / "agentrc.json").is_file():
        # Not configured yet, exit silently
        return 0

    try:
        # Check if rules directory has changed newer than projected files
        rules_dir = hub / "rules"
        if rules_dir.is_dir():
            latest_rule_mtime = max(f.stat().st_mtime for f in rules_dir.rglob("*.md"))
            gemini_md = get_home_dir() / ".gemini" / "GEMINI.md"

            if gemini_md.is_file():
                if latest_rule_mtime > gemini_md.stat().st_mtime:
                    # Hub rules were updated, reproject deterministically
                    project_gemini_rules()
                    project_claude_rules()
                    project_subagents()
    except Exception as e:
        # Never crash the host AI startup session
        print(f"[agentrc] sync notice: {e}", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(run_session_start_hook())
