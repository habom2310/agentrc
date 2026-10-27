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
            if link_path.is_symlink() or os.path.lexists(link_path):
                link_path.unlink()
            link_path.symlink_to(target_path, target_is_directory=True)
            return True, f"Symlink created: {link_path} -> {target_path}"
        except Exception as e:
            return False, f"Failed symlink: {e}"

    link_str = str(link_path)
    target_str = str(target_path)

    # Check if link entry already exists on disk
    if os.path.lexists(link_path):
        try:
            if link_path.resolve() == target_path.resolve():
                return True, f"Junction already intact: {link_str}"
        except Exception:
            pass

        # If it's a reparse point (junction or symlink) pointing to wrong/missing target, remove it
        if link_path.is_symlink() or (hasattr(link_path, "is_junction") and link_path.is_junction()):
            try:
                os.rmdir(link_path)
            except OSError:
                link_path.unlink(missing_ok=True)
        elif link_path.is_dir():
            return False, f"Destination {link_str} already exists and is a directory not pointing to {target_str}"
        else:
            return False, f"Destination {link_str} already exists as a regular file"

    # Use cmd.exe /c mklink /J with quoted paths
    cmd = f'cmd.exe /c mklink /J "{link_str}" "{target_str}"'
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        else:
            return False, proc.stderr.strip() or proc.stdout.strip()
    except Exception as e:
        return False, str(e)


def _migrate_skill_entry(item: Path, target_item: Path) -> None:
    """
    Moves one existing skill entry into the hub. Symlinks are recreated as symlinks
    to the same target so the skill keeps tracking its real source.
    """
    if item.is_symlink():
        link_text = os.readlink(item)
        if not os.path.isabs(link_text):
            # Relative targets are relative to the original link's directory, not the hub
            link_text = os.path.normpath(os.path.join(str(item.parent), link_text))
        try:
            os.symlink(link_text, target_item)
        except OSError:
            # e.g. Windows without symlink privilege: fall back to copying the resolved target
            resolved = item.resolve()
            if resolved.is_dir():
                shutil.copytree(resolved, target_item)
            else:
                shutil.copy2(resolved, target_item)
    elif item.is_dir():
        shutil.copytree(item, target_item)
    else:
        shutil.copy2(item, target_item)


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
            if not os.path.lexists(target_item):
                _migrate_skill_entry(item, target_item)
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
            if not os.path.lexists(target_item):
                _migrate_skill_entry(item, target_item)
        # Backup old skills dir
        old_backup = codex_skills.parent / "skills.old"
        if old_backup.exists():
            shutil.rmtree(old_backup, ignore_errors=True)
        try:
            codex_skills.rename(old_backup)
        except Exception:
            shutil.move(str(codex_skills), str(old_backup))

    res, msg = create_junction(codex_skills, hub_skills)
    if res:
        project_codex_skill_manifests(hub)
    return res, msg


def _parse_skill_frontmatter(skill_md_path: Path) -> dict:
    """
    Parses SKILL.md frontmatter including YAML multiline block scalars (description: >).
    Returns dict with 'name' and 'description' keys.
    """
    text = skill_md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    meta = {}
    current_key = None
    current_val_lines = []

    for line in parts[1].strip().splitlines():
        stripped = line.strip()
        if ":" in line and not line[0].isspace():
            # Save previous key
            if current_key:
                meta[current_key] = " ".join(current_val_lines).strip()
            k, v = line.split(":", 1)
            current_key = k.strip()
            v = v.strip()
            current_val_lines = []
            if v and v not in (">", "|", ">-", "|-"):
                current_val_lines.append(v.strip('"').strip("'"))
        elif current_key and line[0:1].isspace():
            current_val_lines.append(stripped)

    if current_key:
        meta[current_key] = " ".join(current_val_lines).strip()

    return meta


def _to_title_case(slug: str) -> str:
    """Converts a kebab-case slug to Title Case."""
    return " ".join(w.capitalize() for w in slug.split("-"))


def _first_sentence(text: str, max_len: int = 80) -> str:
    """Extracts the first sentence, truncated to max_len."""
    # Split on '. ' to avoid breaking on abbreviations
    if ". " in text:
        first = text.split(". ")[0].strip() + "."
    elif "." in text:
        first = text.split(".")[0].strip() + "."
    else:
        first = text.strip()
    if len(first) > max_len:
        first = first[:max_len - 3].rsplit(" ", 1)[0] + "..."
    return first


def project_codex_skill_manifests(hub_dir: Path | None = None) -> tuple[bool, str]:
    """
    Generates agents/openai.yaml for skills that are missing it.
    Codex CLI requires this manifest to register skills in the session catalog.
    """
    if hub_dir is None:
        hub_dir = get_hub_dir()

    skills_dir = hub_dir / "skills"
    if not skills_dir.is_dir():
        return False, "Skills directory not found"

    generated = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        manifest = skill_dir / "agents" / "openai.yaml"
        if not skill_md.is_file() or manifest.is_file():
            continue

        fm = _parse_skill_frontmatter(skill_md)
        name = fm.get("name", skill_dir.name)
        desc = fm.get("description", "")

        display_name = _to_title_case(name)
        short_desc = _first_sentence(desc) if desc else f"{display_name} skill"

        # Escape double quotes in YAML values
        display_name_escaped = display_name.replace('"', '\\"')
        short_desc_escaped = short_desc.replace('"', '\\"')

        yaml_content = (
            f'interface:\n'
            f'  display_name: "{display_name_escaped}"\n'
            f'  short_description: "{short_desc_escaped}"\n'
            f'  default_prompt: "Use ${name} skill for this task."\n'
        )

        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(yaml_content, encoding="utf-8")
        generated.append(name)

    if not generated:
        return True, "All skills already have Codex manifests"
    return True, f"Generated openai.yaml for {len(generated)} skill(s): {', '.join(generated)}"

