"""
Linker for agentrc.
Manages NTFS directory junctions on Windows and host-specific discovery manifests (skills.json).
"""

from pathlib import Path
import subprocess
import os
import sys
import json
import shutil
from agentrc.detector import get_home_dir, get_hub_dir


def create_junction(link_path: Path, target_path: Path) -> tuple[bool, str]:
    """
    Creates an NTFS directory junction on Windows without requiring admin rights.
    """
    if sys.platform != "win32":
        # Unix symlink
        try:
            if link_path.is_symlink() or link_path.exists():
                link_path.unlink()
            link_path.symlink_to(target_path, target_is_directory=True)
            return True, f"Symlink created: {link_path} -> {target_path}"
        except Exception as e:
            return False, f"Failed symlink: {e}"

    link_str = str(link_path)
    target_str = str(target_path)

    # If link already exists, check if it points to target
    if link_path.exists():
        if link_path.is_symlink() or (link_path.resolve() == target_path.resolve()):
            return True, f"Junction already intact: {link_str}"
        # If it's a real directory, raise warning or migrate
        return False, f"Destination {link_str} already exists and is not pointing to {target_str}"

    # Use cmd.exe /c mklink /J
    cmd = ["cmd.exe", "/c", "mklink", "/J", link_str, target_str]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        else:
            return False, proc.stderr.strip() or proc.stdout.strip()
    except Exception as e:
        return False, str(e)


def link_skills_for_claude() -> tuple[bool, str]:
    """
    Links ~/.claude/skills to ~/.agentrc/skills using an NTFS directory junction.
    If ~/.claude/skills contains existing skills, moves them to ~/.agentrc/skills first.
    """
    home = get_home_dir()
    hub = get_hub_dir()
    claude_skills = home / ".claude" / "skills"
    hub_skills = hub / "skills"

    hub_skills.mkdir(parents=True, exist_ok=True)

    if claude_skills.is_dir() and not claude_skills.is_symlink() and claude_skills.resolve() != hub_skills.resolve():
        # Migrate contents
        for item in claude_skills.iterdir():
            target_item = hub_skills / item.name
            if not target_item.exists():
                if item.is_dir():
                    shutil.copytree(item, target_item)
                else:
                    shutil.copy2(item, target_item)
        # Rename old directory to backup
        old_backup = claude_skills.parent / "skills.old"
        if old_backup.exists():
            shutil.rmtree(old_backup, ignore_errors=True)
        try:
            claude_skills.rename(old_backup)
        except Exception:
            shutil.move(str(claude_skills), str(old_backup))

    return create_junction(claude_skills, hub_skills)


def link_skills_for_gemini() -> tuple[bool, str]:
    """
    Updates ~/.gemini/config/skills.json to point to ~/.agentrc/skills.
    """
    home = get_home_dir()
    hub = get_hub_dir()
    gemini_config = home / ".gemini" / "config"
    gemini_config.mkdir(parents=True, exist_ok=True)
    skills_json = gemini_config / "skills.json"
    hub_skills = (hub / "skills").resolve()

    resolved_path_str = str(hub_skills).replace("\\", "/")

    current_data = {"entries": []}
    if skills_json.is_file():
        try:
            current_data = json.loads(skills_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    entries = current_data.get("entries", [])
    # Update or add entry
    updated = False
    for entry in entries:
        if "agentrc" in entry.get("path", "") or ".claude" in entry.get("path", ""):
            entry["path"] = resolved_path_str
            updated = True
            break

    if not updated:
        entries.append({"path": resolved_path_str})
    current_data["entries"] = entries

    skills_json.write_text(json.dumps(current_data, indent=2), encoding="utf-8")
    return True, f"Updated {skills_json} with path {resolved_path_str}"


def link_skills_for_codex() -> tuple[bool, str]:
    """
    Links ~/.codex/skills to ~/.agentrc/skills using an NTFS directory junction,
    preserving existing Codex-native skills by copying them to hub first.
    """
    home = get_home_dir()
    hub = get_hub_dir()
    codex_skills = home / ".codex" / "skills"
    hub_skills = hub / "skills"

    if not (home / ".codex").is_dir():
        return False, "~/.codex directory does not exist"

    hub_skills.mkdir(parents=True, exist_ok=True)

    if codex_skills.is_dir() and not codex_skills.is_symlink() and codex_skills.resolve() != hub_skills.resolve():
        # Migrate existing unique skills to hub
        for item in codex_skills.iterdir():
            target_item = hub_skills / item.name
            if not target_item.exists():
                if item.is_dir():
                    shutil.copytree(item, target_item)
                else:
                    shutil.copy2(item, target_item)
        # Backup old skills dir
        old_backup = codex_skills.parent / "skills.old"
        if old_backup.exists():
            shutil.rmtree(old_backup, ignore_errors=True)
        try:
            codex_skills.rename(old_backup)
        except Exception:
            shutil.move(str(codex_skills), str(old_backup))

    return create_junction(codex_skills, hub_skills)

