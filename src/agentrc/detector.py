"""
Platform detector for agentrc.
Detects installed AI coding assistants and their configuration status.
"""

from pathlib import Path
import shutil
import json


def get_home_dir() -> Path:
    return Path.home()


def get_hub_dir() -> Path:
    return get_home_dir() / ".agentrc"


def detect_platforms() -> dict:
    home = get_home_dir()
    hub = get_hub_dir()

    report = {
        "hub": {
            "path": str(hub),
            "exists": hub.is_dir(),
            "manifest_exists": (hub / "agentrc.json").is_file(),
            "skills_count": len(list((hub / "skills").iterdir())) if (hub / "skills").is_dir() else 0,
            "rules_count": len(list((hub / "rules").glob("*.md"))) if (hub / "rules").is_dir() else 0,
        },
        "platforms": {}
    }

    # 1. Antigravity / Gemini
    gemini_dir = home / ".gemini"
    gemini_config = gemini_dir / "config"
    gemini_rules = gemini_dir / "GEMINI.md"
    gemini_skills_json = gemini_config / "skills.json"
    gemini_agents = gemini_config / "agents"
    gemini_hooks = gemini_config / "hooks.json"

    skills_mapped_to_hub = False
    if gemini_skills_json.is_file():
        try:
            data = json.loads(gemini_skills_json.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            for entry in entries:
                p = entry.get("path", "")
                if ".agentrc" in p or "agentrc" in p:
                    skills_mapped_to_hub = True
        except Exception:
            pass

    report["platforms"]["antigravity"] = {
        "name": "Google Antigravity (AGY)",
        "detected": gemini_dir.is_dir(),
        "path": str(gemini_dir),
        "rules_file": str(gemini_rules),
        "rules_exists": gemini_rules.is_file(),
        "skills_json": str(gemini_skills_json),
        "skills_json_exists": gemini_skills_json.is_file(),
        "skills_linked": skills_mapped_to_hub,
        "agents_dir": str(gemini_agents),
        "agents_count": len(list(gemini_agents.glob("*.md"))) if gemini_agents.is_dir() else 0,
        "hooks_file": str(gemini_hooks),
        "hooks_exists": gemini_hooks.is_file(),
    }

    # 2. Claude Code
    claude_dir = home / ".claude"
    claude_rules = claude_dir / "CLAUDE.md"
    claude_skills = claude_dir / "skills"
    claude_agents = claude_dir / "agents"
    claude_settings = claude_dir / "settings.json"

    skills_is_junction = False
    if claude_skills.is_dir():
        # Check if skills is a junction or symlink
        try:
            skills_is_junction = claude_skills.is_symlink() or (claude_skills.resolve() != claude_skills)
        except Exception:
            pass

    report["platforms"]["claude"] = {
        "name": "Claude Code",
        "detected": claude_dir.is_dir(),
        "path": str(claude_dir),
        "rules_file": str(claude_rules),
        "rules_exists": claude_rules.is_file(),
        "skills_dir": str(claude_skills),
        "skills_exists": claude_skills.is_dir(),
        "skills_is_junction": skills_is_junction,
        "agents_dir": str(claude_agents),
        "agents_count": len(list(claude_agents.glob("*.md"))) if claude_agents.is_dir() else 0,
        "settings_file": str(claude_settings),
        "settings_exists": claude_settings.is_file(),
    }

    # 3. Cursor
    cursor_dir = home / ".cursor"
    report["platforms"]["cursor"] = {
        "name": "Cursor",
        "detected": cursor_dir.is_dir(),
        "path": str(cursor_dir),
    }

    # 4. Copilot CLI
    copilot_path = shutil.which("copilot")
    report["platforms"]["copilot"] = {
        "name": "GitHub Copilot CLI",
        "detected": copilot_path is not None,
        "path": copilot_path or "",
    }

    return report
