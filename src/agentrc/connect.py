"""
Platform connection engine for agentrc.
Connects new AI coding assistants (Cursor, Windsurf, Codex, etc.) to the central hub.
"""

from pathlib import Path
import json
import shutil
from datetime import datetime, timezone

from agentrc.detector import get_home_dir, get_hub_dir
from agentrc.linker import create_junction, link_skills_for_claude, link_skills_for_gemini, link_skills_for_codex
from agentrc.projector import (
    project_gemini_rules,
    project_claude_rules,
    project_codex_rules,
    project_cursor_rules,
    project_windsurf_rules,
    project_subagents,
)


def _update_hub_manifest(platform_name: str, info: dict, hub_dir: Path) -> None:
    manifest_file = hub_dir / "agentrc.json"
    if not manifest_file.is_file():
        return
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        if "platforms" not in data:
            data["platforms"] = {}
        data["platforms"][platform_name] = info
        manifest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def connect_cursor(target_dir: Path | None = None) -> tuple[bool, str]:
    """
    Connects Cursor to ~/.agentrc hub:
    1. Creates junction from ~/.cursor/skills to ~/.agentrc/skills.
    2. Projects rules into ~/.cursor/rules/agentrc.mdc and ~/.cursorrules.
    3. Updates ~/.agentrc/agentrc.json connected platforms.
    """
    home = get_home_dir()
    hub = get_hub_dir()
    cursor_dir = target_dir or (home / ".cursor")
    hub_skills = hub / "skills"
    hub_skills.mkdir(parents=True, exist_ok=True)

    cursor_dir.mkdir(parents=True, exist_ok=True)
    cursor_skills = cursor_dir / "skills"

    # Migrate any existing skills from cursor_skills to hub
    if cursor_skills.is_dir() and not cursor_skills.is_symlink() and cursor_skills.resolve() != hub_skills.resolve():
        for item in cursor_skills.iterdir():
            target_item = hub_skills / item.name
            if not target_item.exists():
                if item.is_dir():
                    shutil.copytree(item, target_item)
                else:
                    shutil.copy2(item, target_item)
        old_backup = cursor_skills.parent / "skills.old"
        if old_backup.exists():
            shutil.rmtree(old_backup, ignore_errors=True)
        try:
            cursor_skills.rename(old_backup)
        except Exception:
            shutil.move(str(cursor_skills), str(old_backup))

    ok_junc, msg_junc = create_junction(cursor_skills, hub_skills)
    if not ok_junc:
        return False, f"Failed to link Cursor skills: {msg_junc}"

    # Project rules
    ok_p, msg_p = project_cursor_rules(cursor_dir)
    if not ok_p:
        return False, f"Failed to project Cursor rules: {msg_p}"

    _update_hub_manifest(
        "cursor",
        {
            "enabled": True,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "path": str(cursor_dir),
            "rules_file": str(cursor_dir / "rules" / "agentrc.mdc"),
        },
        hub,
    )

    return True, f"Connected Cursor: linked skills junction and projected rules to {cursor_dir}"


def connect_windsurf(target_dir: Path | None = None) -> tuple[bool, str]:
    """
    Connects Windsurf to ~/.agentrc hub:
    1. Creates junction from ~/.codeium/windsurf/skills to ~/.agentrc/skills.
    2. Projects rules into ~/.codeium/windsurf/memories/global_rules.md and ~/.windsurfrules.
    3. Updates ~/.agentrc/agentrc.json connected platforms.
    """
    home = get_home_dir()
    hub = get_hub_dir()
    windsurf_dir = target_dir or (home / ".codeium" / "windsurf")
    hub_skills = hub / "skills"
    hub_skills.mkdir(parents=True, exist_ok=True)

    windsurf_dir.mkdir(parents=True, exist_ok=True)
    windsurf_skills = windsurf_dir / "skills"

    # Migrate any existing skills from windsurf_skills to hub
    if windsurf_skills.is_dir() and not windsurf_skills.is_symlink() and windsurf_skills.resolve() != hub_skills.resolve():
        for item in windsurf_skills.iterdir():
            target_item = hub_skills / item.name
            if not target_item.exists():
                if item.is_dir():
                    shutil.copytree(item, target_item)
                else:
                    shutil.copy2(item, target_item)
        old_backup = windsurf_skills.parent / "skills.old"
        if old_backup.exists():
            shutil.rmtree(old_backup, ignore_errors=True)
        try:
            windsurf_skills.rename(old_backup)
        except Exception:
            shutil.move(str(windsurf_skills), str(old_backup))

    ok_junc, msg_junc = create_junction(windsurf_skills, hub_skills)
    if not ok_junc:
        return False, f"Failed to link Windsurf skills: {msg_junc}"

    ok_p, msg_p = project_windsurf_rules(windsurf_dir)
    if not ok_p:
        return False, f"Failed to project Windsurf rules: {msg_p}"

    _update_hub_manifest(
        "windsurf",
        {
            "enabled": True,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "path": str(windsurf_dir),
            "rules_file": str(windsurf_dir / "memories" / "global_rules.md"),
        },
        hub,
    )

    return True, f"Connected Windsurf: linked skills junction and projected rules to {windsurf_dir}"


def connect_platform(platform_name: str, target_dir: Path | None = None) -> tuple[bool, str]:
    """
    Connects an assistant platform to ~/.agentrc hub.
    Supported: cursor, windsurf, codex, claude, gemini / agy.
    """
    norm = platform_name.strip().lower()
    if target_dir is not None and norm not in ("cursor", "windsurf", "codeium"):
        return False, f"Custom --target-dir is not supported for '{platform_name}'. It is only supported for 'cursor' and 'windsurf'."

    if norm in ("cursor",):
        return connect_cursor(target_dir)
    elif norm in ("windsurf", "codeium"):
        return connect_windsurf(target_dir)
    elif norm in ("codex", "chatgpt"):
        ok_l, msg_l = link_skills_for_codex()
        ok_p, msg_p = project_codex_rules()
        return (ok_l and ok_p), f"{msg_l}; {msg_p}"
    elif norm in ("claude", "claudecode"):
        ok_l, msg_l = link_skills_for_claude()
        ok_p, msg_p = project_claude_rules()
        return (ok_l and ok_p), f"{msg_l}; {msg_p}"
    elif norm in ("gemini", "agy", "antigravity"):
        ok_l, msg_l = link_skills_for_gemini()
        ok_p, msg_p = project_gemini_rules()
        return (ok_l and ok_p), f"{msg_l}; {msg_p}"
    else:
        return False, f"Unsupported platform '{platform_name}'. Supported: cursor, windsurf, codex, claude, gemini"
