"""
Platform detector for agentrc.
Detects installed AI coding assistants and their configuration status.
"""

import os
from pathlib import Path
import shutil
import json

_HOME_OVERRIDE: Path | None = None
_HUB_OVERRIDE: Path | None = None


def set_custom_home(home_path: Path | None, hub_path: Path | None = None):
    global _HOME_OVERRIDE, _HUB_OVERRIDE
    _HOME_OVERRIDE = home_path
    _HUB_OVERRIDE = hub_path


def get_home_dir() -> Path:
    if _HOME_OVERRIDE:
        return _HOME_OVERRIDE
    env = os.environ.get("AGENTRC_HOME")
    if env:
        return Path(env)
    return Path.home()


def get_hub_dir() -> Path:
    if _HUB_OVERRIDE:
        return _HUB_OVERRIDE
    env = os.environ.get("AGENTRC_HUB")
    if env:
        return Path(env)
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

    # 3. OpenAI Codex & ChatGPT
    codex_dir = home / ".codex"
    codex_rules = codex_dir / "AGENTS.md"
    codex_skills = codex_dir / "skills"
    codex_config = codex_dir / "config.toml"
    codex_bin = shutil.which("codex")

    skills_in_codex_linked = False
    if codex_skills.is_dir():
        try:
            skills_in_codex_linked = codex_skills.is_symlink() or (codex_skills.resolve() != codex_skills)
        except Exception:
            pass

    report["platforms"]["codex"] = {
        "name": "OpenAI Codex CLI & ChatGPT",
        "detected": codex_dir.is_dir() or (codex_bin is not None),
        "path": str(codex_dir),
        "bin_path": codex_bin or "",
        "rules_file": str(codex_rules),
        "rules_exists": codex_rules.is_file(),
        "skills_dir": str(codex_skills),
        "skills_exists": codex_skills.is_dir(),
        "skills_linked": skills_in_codex_linked,
        "config_file": str(codex_config),
        "config_exists": codex_config.is_file(),
    }

    # 4. Cursor
    cursor_dir = home / ".cursor"
    cursor_skills = cursor_dir / "skills"
    cursor_rules_mdc = cursor_dir / "rules" / "agentrc.mdc"
    cursor_rules_legacy = home / ".cursorrules"
    skills_linked = False
    if cursor_skills.is_dir():
        try:
            skills_linked = cursor_skills.is_symlink() or (cursor_skills.resolve() != cursor_skills)
        except Exception:
            pass

    report["platforms"]["cursor"] = {
        "name": "Cursor",
        "detected": cursor_dir.is_dir(),
        "path": str(cursor_dir),
        "rules_exists": cursor_rules_mdc.is_file() or cursor_rules_legacy.is_file(),
        "skills_linked": skills_linked,
    }

    # 5. Windsurf
    windsurf_dir = home / ".codeium" / "windsurf"
    if not windsurf_dir.is_dir():
        windsurf_dir = home / ".windsurf"
    windsurf_skills = windsurf_dir / "skills"
    windsurf_rules = windsurf_dir / "memories" / "global_rules.md"
    windsurf_rules_legacy = home / ".windsurfrules"
    ws_linked = False
    if windsurf_skills.is_dir():
        try:
            ws_linked = windsurf_skills.is_symlink() or (windsurf_skills.resolve() != windsurf_skills)
        except Exception:
            pass

    report["platforms"]["windsurf"] = {
        "name": "Windsurf",
        "detected": windsurf_dir.is_dir(),
        "path": str(windsurf_dir),
        "rules_exists": windsurf_rules.is_file() or windsurf_rules_legacy.is_file(),
        "skills_linked": ws_linked,
    }

    # 6. Copilot CLI
    copilot_path = shutil.which("copilot")
    report["platforms"]["copilot"] = {
        "name": "GitHub Copilot CLI",
        "detected": copilot_path is not None,
        "path": copilot_path or "",
    }

    return report
