"""
Bidirectional MCP registry and synchronization engine for agentrc.
Synchronizes MCP servers across ~/.agentrc/mcp/servers.json, Claude Code (~/.claude.json),
and Google Antigravity (~/.gemini/config/mcp_config.json and ~/.gemini/settings.json).
"""

from pathlib import Path
import json
import shutil
import tempfile
from agentrc.detector import get_home_dir, get_hub_dir


def _read_json_safely(path: Path) -> tuple[dict, bool]:
    """
    Reads a JSON file safely.
    Returns (data, success).
    If file doesn't exist, returns ({}, True).
    If file exists but fails to read or parse, returns ({}, False) to prevent accidental data erasure.
    """
    if not path.is_file():
        return {}, True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}, False
        return data, True
    except Exception:
        return {}, False


def _write_json_safely(path: Path, data: dict):
    """Safely writes JSON data to file using unique temporary file to avoid collisions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8") as tf:
        temp_path = Path(tf.name)
        tf.write(text)
    shutil.move(str(temp_path), str(path))


def normalize_server_for_hub(name: str, config: dict) -> dict:
    """Normalizes an MCP server configuration for universal storage in the hub."""
    clean = dict(config)
    # Strip Claude-specific session/cache keys if present
    clean.pop("alwaysLoad", None)
    return clean


def adapt_server_for_claude(name: str, config: dict) -> dict:
    """Adapts a universal server config for Claude Code (~/.claude.json)."""
    adapted = dict(config)
    if "url" in adapted and "type" not in adapted:
        adapted["type"] = "http"
    elif "command" in adapted and "type" not in adapted:
        adapted["type"] = "stdio"
    return adapted


def adapt_server_for_gemini(name: str, config: dict) -> dict:
    """Adapts a universal server config for Google Antigravity (mcp_config.json / settings.json)."""
    adapted = dict(config)
    if "url" in adapted and "type" not in adapted:
        adapted["type"] = "http"
    elif "command" in adapted and "type" not in adapted:
        adapted["type"] = "stdio"
    return adapted


def get_mcp_status(home_dir: Path | None = None, hub_dir: Path | None = None) -> dict:
    """Audits MCP server configuration status and drift across hub, Claude, and Antigravity."""
    if home_dir is None:
        home_dir = get_home_dir()
    if hub_dir is None:
        hub_dir = get_hub_dir()

    hub_mcp_file = hub_dir / "mcp" / "servers.json"
    claude_file = home_dir / ".claude.json"
    gemini_mcp_file = home_dir / ".gemini" / "config" / "mcp_config.json"
    gemini_settings_file = home_dir / ".gemini" / "settings.json"

    hub_data, hub_ok = _read_json_safely(hub_mcp_file)
    hub_servers = hub_data.get("mcpServers", {})

    claude_data, claude_ok = _read_json_safely(claude_file)
    claude_servers = claude_data.get("mcpServers", {})

    gemini_mcp_data, gmcp_ok = _read_json_safely(gemini_mcp_file)
    gemini_mcp_servers = gemini_mcp_data.get("mcpServers", {})

    gemini_settings_data, gset_ok = _read_json_safely(gemini_settings_file)
    gemini_settings_servers = gemini_settings_data.get("mcpServers", {})

    # Combine Gemini servers
    gemini_servers = dict(gemini_settings_servers)
    gemini_servers.update(gemini_mcp_servers)

    claude_installed = claude_file.is_file() or (home_dir / ".claude").is_dir()
    gemini_installed = (home_dir / ".gemini").is_dir() or gemini_mcp_file.is_file() or gemini_settings_file.is_file()

    missing_in_claude = [s for s in hub_servers if s not in claude_servers] if claude_installed else []
    missing_in_gemini = [s for s in hub_servers if s not in gemini_servers] if gemini_installed else []
    untracked_in_claude = [s for s in claude_servers if s not in hub_servers]
    untracked_in_gemini = [s for s in gemini_servers if s not in hub_servers]

    # Detect configuration drift for existing servers
    # alwaysLoad is Claude-only and kept on the Claude side, so ignore it when comparing.
    drifted_in_claude = [
        s for s in hub_servers
        if s in claude_servers
        and {k: v for k, v in claude_servers[s].items() if k != "alwaysLoad"}
        != adapt_server_for_claude(s, hub_servers[s])
    ]
    drifted_in_gemini = [
        s for s in hub_servers
        if s in gemini_servers and gemini_servers[s] != adapt_server_for_gemini(s, hub_servers[s])
    ]

    in_sync = not (
        missing_in_claude
        or missing_in_gemini
        or untracked_in_claude
        or untracked_in_gemini
        or drifted_in_claude
        or drifted_in_gemini
    )

    return {
        "hub": {
            "path": str(hub_mcp_file),
            "exists": hub_mcp_file.is_file(),
            "valid": hub_ok,
            "servers": hub_servers,
        },
        "claude": {
            "path": str(claude_file),
            "exists": claude_file.is_file(),
            "valid": claude_ok,
            "servers": claude_servers,
        },
        "gemini": {
            "path": str(gemini_mcp_file),
            "exists": gemini_mcp_file.is_file() or gemini_settings_file.is_file(),
            "valid": gmcp_ok and gset_ok,
            "servers": gemini_servers,
        },
        "in_sync": in_sync,
        "missing_in_claude": missing_in_claude,
        "missing_in_gemini": missing_in_gemini,
        "untracked_in_claude": untracked_in_claude,
        "untracked_in_gemini": untracked_in_gemini,
        "drifted_in_claude": drifted_in_claude,
        "drifted_in_gemini": drifted_in_gemini,
    }


def sync_mcp_servers(home_dir: Path | None = None, hub_dir: Path | None = None) -> tuple[bool, list[str]]:
    """
    Performs bidirectional MCP server synchronization:
    1. Ingests any untracked or updated servers from Claude or Gemini into hub servers.json.
    2. Projects the union of servers into Claude (~/.claude.json) and Gemini (~/.gemini/config/mcp_config.json & settings.json),
       strictly preserving all other non-MCP configuration keys.
    """
    if home_dir is None:
        home_dir = get_home_dir()
    if hub_dir is None:
        hub_dir = get_hub_dir()

    actions = []

    hub_mcp_file = hub_dir / "mcp" / "servers.json"
    claude_file = home_dir / ".claude.json"
    gemini_mcp_file = home_dir / ".gemini" / "config" / "mcp_config.json"
    gemini_settings_file = home_dir / ".gemini" / "settings.json"

    hub_data, hub_ok = _read_json_safely(hub_mcp_file)
    if not hub_ok:
        return False, [f"Aborting MCP sync: {hub_mcp_file.name} is corrupt or unparseable"]

    hub_servers = dict(hub_data.get("mcpServers", {}))

    claude_data, claude_ok = _read_json_safely(claude_file)
    claude_servers = dict(claude_data.get("mcpServers", {}))

    gemini_mcp_data, gmcp_ok = _read_json_safely(gemini_mcp_file)
    gemini_mcp_servers = dict(gemini_mcp_data.get("mcpServers", {}))

    gemini_settings_data, gset_ok = _read_json_safely(gemini_settings_file)
    gemini_settings_servers = dict(gemini_settings_data.get("mcpServers", {}))

    # 1. Ingest from Claude into hub
    if claude_ok:
        for name, cfg in claude_servers.items():
            if name not in hub_servers:
                hub_servers[name] = normalize_server_for_hub(name, cfg)
                actions.append(f"Ingested '{name}' from Claude Code into hub")

    # 2. Ingest from Gemini into hub
    if gmcp_ok and gset_ok:
        combined_gemini = {**gemini_settings_servers, **gemini_mcp_servers}
        for name, cfg in combined_gemini.items():
            if name not in hub_servers:
                hub_servers[name] = normalize_server_for_hub(name, cfg)
                actions.append(f"Ingested '{name}' from Antigravity into hub")

    # Save updated hub manifest
    hub_data["mcpServers"] = hub_servers
    _write_json_safely(hub_mcp_file, hub_data)

    # 3. Mirror into Claude (~/.claude.json)
    if claude_file.is_file() or (home_dir / ".claude").is_dir():
        if not claude_ok:
            actions.append(f"[SKIP] Refusing to overwrite {claude_file.name}: file is corrupt or unparseable")
        else:
            claude_target = dict(claude_data)
            updated_claude_servers = dict(claude_servers)
            changed_claude = False
            for name, cfg in hub_servers.items():
                adapted = adapt_server_for_claude(name, cfg)
                existing = updated_claude_servers.get(name, {})
                if "alwaysLoad" in existing:
                    # alwaysLoad is stripped from the hub copy, so keep Claude's value.
                    adapted["alwaysLoad"] = existing["alwaysLoad"]
                if updated_claude_servers.get(name) != adapted:
                    updated_claude_servers[name] = adapted
                    changed_claude = True
            if changed_claude or "mcpServers" not in claude_target:
                claude_target["mcpServers"] = updated_claude_servers
                _write_json_safely(claude_file, claude_target)
                actions.append(f"Updated Claude Code ({claude_file.name}) with {len(updated_claude_servers)} server(s)")

    # 4. Mirror into Gemini (mcp_config.json & settings.json)
    if (home_dir / ".gemini").is_dir():
        # mcp_config.json
        if not gmcp_ok:
            actions.append(f"[SKIP] Refusing to overwrite {gemini_mcp_file.name}: file is corrupt or unparseable")
        else:
            gemini_mcp_target = dict(gemini_mcp_data)
            updated_gmcp_servers = dict(gemini_mcp_servers)
            changed_gmcp = False
            for name, cfg in hub_servers.items():
                adapted = adapt_server_for_gemini(name, cfg)
                if updated_gmcp_servers.get(name) != adapted:
                    updated_gmcp_servers[name] = adapted
                    changed_gmcp = True
            if changed_gmcp or "mcpServers" not in gemini_mcp_target:
                gemini_mcp_target["mcpServers"] = updated_gmcp_servers
                _write_json_safely(gemini_mcp_file, gemini_mcp_target)
                actions.append(f"Updated Antigravity ({gemini_mcp_file.name}) with {len(updated_gmcp_servers)} server(s)")

        # settings.json
        if not gset_ok:
            actions.append(f"[SKIP] Refusing to overwrite {gemini_settings_file.name}: file is corrupt or unparseable")
        else:
            gemini_settings_target = dict(gemini_settings_data)
            updated_gset_servers = dict(gemini_settings_servers)
            changed_gset = False
            for name, cfg in hub_servers.items():
                adapted = adapt_server_for_gemini(name, cfg)
                if updated_gset_servers.get(name) != adapted:
                    updated_gset_servers[name] = adapted
                    changed_gset = True
            if changed_gset or "mcpServers" not in gemini_settings_target:
                gemini_settings_target["mcpServers"] = updated_gset_servers
                _write_json_safely(gemini_settings_file, gemini_settings_target)
                actions.append(f"Updated Antigravity ({gemini_settings_file.name}) with {len(updated_gset_servers)} server(s)")

    if not actions:
        actions.append("All MCP configurations are already synchronized.")

    return True, actions
