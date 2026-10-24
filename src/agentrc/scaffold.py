"""
Scaffold and migration initializer for agentrc hub.
Creates ~/.agentrc directory hierarchy, populates starter templates,
and performs safe whitelist backups.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
from agentrc.detector import get_home_dir, get_hub_dir


def backup_existing_configs(backup_dir: Path) -> list[str]:
    """
    Performs a safe whitelist backup of targeted configuration files
    from ~/.claude and ~/.gemini to prevent data loss.
    Avoids backing up multi-gigabyte brain/ logs or SQLite databases.
    """
    home = get_home_dir()
    backed_up = []
    backup_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        home / ".gemini" / "GEMINI.md",
        home / ".gemini" / "config" / "GEMINI.md",
        home / ".gemini" / "config" / "skills.json",
        home / ".gemini" / "config" / "hooks.json",
        home / ".claude" / "CLAUDE.md",
        home / ".claude" / "settings.json",
        home / ".codex" / "AGENTS.md",
        home / ".codex" / "config.toml",
    ]

    for t in targets:
        if t.is_file():
            rel = t.relative_to(home)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(t, dest)
            backed_up.append(str(rel))

    # Whitelist backup for subagents
    for ag_dir in [home / ".gemini" / "config" / "agents", home / ".claude" / "agents"]:
        if ag_dir.is_dir():
            for f in ag_dir.glob("*.md"):
                rel = f.relative_to(home)
                dest = backup_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                backed_up.append(str(rel))

    return backed_up


def init_hub(template_dir: Path | None = None, force: bool = False) -> dict:
    """
    Scaffolds ~/.agentrc directory structure and populates initial files.
    """
    hub = get_hub_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")

    # 1. Perform Whitelist Backup
    backup_path = hub / "backups" / f"pre-agentrc-{timestamp}"
    backed_up_files = backup_existing_configs(backup_path)

    # 2. Create Directory Scaffold
    subdirs = [
        hub / "rules" / "overrides",
        hub / "skills",
        hub / "agents",
        hub / "mcp",
        hub / "backups",
        hub / "bin",
    ]
    for d in subdirs:
        d.mkdir(parents=True, exist_ok=True)

    # 3. Copy Templates if provided
    copied_templates = []
    if template_dir and template_dir.is_dir():
        for root, dirs, files in template_dir.walk() if hasattr(template_dir, "walk") else list(template_dir.rglob("*")):
            # standard rglob fallback
            pass

        # Copy rules
        rules_src = template_dir / "rules"
        if rules_src.is_dir():
            for f in rules_src.glob("*.md"):
                dest = hub / "rules" / f.name
                if not dest.exists() or force:
                    shutil.copy2(f, dest)
                    copied_templates.append(f"rules/{f.name}")
            for f in (rules_src / "overrides").glob("*.md"):
                dest = hub / "rules" / "overrides" / f.name
                if not dest.exists() or force:
                    shutil.copy2(f, dest)
                    copied_templates.append(f"rules/overrides/{f.name}")

        # Copy agents
        agents_src = template_dir / "agents"
        if agents_src.is_dir():
            for f in agents_src.glob("*.md"):
                dest = hub / "agents" / f.name
                if not dest.exists() or force:
                    shutil.copy2(f, dest)
                    copied_templates.append(f"agents/{f.name}")

        # Copy mcp
        mcp_src = template_dir / "mcp"
        if mcp_src.is_dir():
            for f in mcp_src.glob("*.json"):
                dest = hub / "mcp" / f.name
                if not dest.exists() or force:
                    shutil.copy2(f, dest)
                    copied_templates.append(f"mcp/{f.name}")

    # 4. Write manifest
    manifest_file = hub / "agentrc.json"
    manifest_data = {
        "version": "0.1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platforms": {
            "claude": {"enabled": True},
            "antigravity": {"enabled": True},
            "cursor": {"enabled": False},
        },
        "links": {
            "skills": str(hub / "skills"),
        }
    }
    if not manifest_file.exists() or force:
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return {
        "hub_dir": str(hub),
        "backed_up_files": backed_up_files,
        "copied_templates": copied_templates,
        "manifest": str(manifest_file),
    }
