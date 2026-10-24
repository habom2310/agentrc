"""
Prompt block exporter for agentrc.
Generates standalone, copy-pasteable prompt blocks for web/desktop AI interfaces
such as ChatGPT Custom Instructions, Claude Web Projects, and Cursor rules.
"""

from pathlib import Path
from agentrc.detector import get_hub_dir

EXPORT_TARGETS = {
    "chatgpt": {
        "title": "ChatGPT Custom Instructions & Project System Prompt",
        "overrides_file": "overrides/codex.md",
        "default_filename": "chatgpt_custom_instructions.md",
    },
    "claude": {
        "title": "Claude Web Project System Instructions",
        "overrides_file": "overrides/claude.md",
        "default_filename": "claude_project_instructions.md",
    },
    "cursor": {
        "title": "Cursor .cursorrules Export",
        "overrides_file": "overrides/cursor.md",
        "default_filename": "cursor_rules_export.md",
    },
}


def export_prompt_block(
    platform: str,
    hub_dir: Path | None = None,
    output_path: Path | None = None,
) -> tuple[bool, str, Path | None]:
    """
    Exports a consolidated, standalone Markdown prompt block combining
    universal engineering heuristics and platform-specific overrides.
    """
    norm = platform.strip().lower()
    if norm not in EXPORT_TARGETS:
        return False, f"Unsupported export target '{platform}'. Choose from: {', '.join(EXPORT_TARGETS.keys())}", None

    cfg = EXPORT_TARGETS[norm]
    if hub_dir is None:
        hub_dir = get_hub_dir()

    rules_dir = hub_dir / "rules"
    if not rules_dir.is_dir():
        return False, f"Rules directory not found in {hub_dir}", None

    parts = [
        f"<!-- Exported by agentrc for {cfg['title']} -->\n"
        f"# Multi-Agent Guidelines & Operational Heuristics"
    ]

    for fname in ["common.md", "code-tools.md", "handoffs.md"]:
        fpath = rules_dir / fname
        if fpath.is_file():
            parts.append(fpath.read_text(encoding="utf-8").strip())

    override_path = rules_dir / cfg["overrides_file"]
    if override_path.is_file():
        parts.append(override_path.read_text(encoding="utf-8").strip())

    content = "\n\n".join(parts) + "\n"

    # Save to file
    if output_path is None:
        export_dir = hub_dir / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        final_dest = export_dir / cfg["default_filename"]
    else:
        final_dest = Path(output_path).resolve()
        final_dest.parent.mkdir(parents=True, exist_ok=True)

    final_dest.write_text(content, encoding="utf-8")
    return True, content, final_dest
