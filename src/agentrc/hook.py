"""
SessionStart lifecycle hook for agentrc.
Fast (<10ms), headless, non-blocking drift synchronization.
"""

from pathlib import Path
import sys
from agentrc.detector import get_home_dir, get_hub_dir
from agentrc.projector import (
    project_gemini_rules,
    project_claude_rules,
    project_codex_rules,
    project_subagents,
)


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
        # Check source mtime across rules and agents
        rules_dir = hub / "rules"
        agents_dir = hub / "agents"
        sources = []
        if rules_dir.is_dir():
            sources.extend(rules_dir.rglob("*.md"))
        if agents_dir.is_dir():
            sources.extend(agents_dir.glob("*.md"))

        if not sources:
            return 0

        latest_src_mtime = max(f.stat().st_mtime for f in sources)
        home = get_home_dir()

        # Check target projection files independently
        targets = [
            home / ".gemini" / "GEMINI.md",
            home / ".claude" / "CLAUDE.md",
            home / ".codex" / "AGENTS.md",
        ]

        needs_reproject = False
        for t in targets:
            if t.is_file() and latest_src_mtime > t.stat().st_mtime:
                needs_reproject = True
                break

        if needs_reproject:
            project_gemini_rules()
            project_claude_rules()
            project_codex_rules()
            project_subagents()

        # Check MCP sync drift
        hub_mcp = hub / "mcp" / "servers.json"
        if hub_mcp.is_file():
            claude_json = home / ".claude.json"
            gemini_mcp = home / ".gemini" / "config" / "mcp_config.json"
            gemini_settings = home / ".gemini" / "settings.json"
            hub_mtime = hub_mcp.stat().st_mtime

            for p in [claude_json, gemini_mcp, gemini_settings]:
                if p.is_file() and abs(p.stat().st_mtime - hub_mtime) > 1.0:
                    from agentrc.mcp_sync import get_mcp_status, sync_mcp_servers
                    st = get_mcp_status(home, hub)
                    if not st["in_sync"]:
                        sync_mcp_servers(home, hub)
                    break
    except Exception as e:
        # Never crash the host AI startup session
        print(f"[agentrc] sync notice: {e}", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(run_session_start_hook())
