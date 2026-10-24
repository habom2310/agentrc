"""
CLI entry point for agentrc.
"""

import argparse
import sys
import json
from pathlib import Path

from agentrc.detector import detect_platforms, set_custom_home
from agentrc.scaffold import init_hub
from agentrc.linker import link_skills_for_claude, link_skills_for_gemini, link_skills_for_codex, project_codex_skill_manifests
from agentrc.projector import project_gemini_rules, project_claude_rules, project_codex_rules, project_subagents
from agentrc.doctor import run_doctor
from agentrc.token_budget import audit_budget
from agentrc.hook import run_session_start_hook


def main():
    parser = argparse.ArgumentParser(
        prog="agentrc",
        description="agentrc: Centralized Multi-AI Configuration & Skill Management Hub"
    )
    parser.add_argument(
        "--home", "-H",
        type=str,
        default=None,
        help="Sandbox root directory (overrides user home for safe, isolated testing)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # detect
    subparsers.add_parser("detect", help="Detect installed AI tools and config paths")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize ~/.agentrc hub and perform backup")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing templates")
    init_parser.add_argument("--templates", type=str, default=None, help="Custom templates directory")

    # link
    subparsers.add_parser("link", help="Create NTFS junctions and configure skills manifests")

    # project
    subparsers.add_parser("project", help="Deterministically compile rules and subagents")

    # doctor
    doc_parser = subparsers.add_parser("doctor", help="Check health and drift across all tools")
    doc_parser.add_argument("--fix", action="store_true", help="Automatically repair detected issues")

    # budget
    subparsers.add_parser("budget", help="Audit session boot token footprint")

    # hook
    hook_parser = subparsers.add_parser("hook", help="Run lifecycle hooks")
    hook_parser.add_argument("event", choices=["session-start"], help="Hook event name")

    # diff
    diff_parser = subparsers.add_parser("diff", help="Check for unpromoted downstream changes or rule drift")
    diff_parser.add_argument(
        "--platform",
        choices=["all", "gemini", "claude", "codex"],
        default="all",
        help="Platform to check drift for (default: all)"
    )

    # promote
    promote_parser = subparsers.add_parser("promote", help="Promote drifted rules to hub and reproject")
    promote_parser.add_argument(
        "--from-platform",
        choices=["gemini", "claude", "codex"],
        default="gemini",
        help="Platform to promote rule from (default: gemini)"
    )
    promote_parser.add_argument(
        "--target",
        default="common.md",
        help="Target rule file in hub/rules/ (default: common.md)"
    )
    promote_parser.add_argument(
        "--header",
        default=None,
        help="Optional heading string to promote specific section"
    )

    # mcp
    mcp_parser = subparsers.add_parser("mcp", help="Audit and synchronize MCP server registries")
    mcp_parser.add_argument(
        "action",
        nargs="?",
        choices=["status", "sync"],
        default="status",
        help="MCP action to perform (default: status)"
    )

    # push
    push_parser = subparsers.add_parser("push", help="Commit and push ~/.agentrc hub changes to remote")
    push_parser.add_argument("-m", "--message", default=None, help="Commit message")
    push_parser.add_argument("--remote", default="origin", help="Git remote name (default: origin)")

    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull latest ~/.agentrc hub changes from remote and reproject")
    pull_parser.add_argument("--remote", default="origin", help="Git remote name (default: origin)")
    pull_parser.add_argument("--no-reproject", action="store_true", help="Skip automatic reprojection after pull")

    # git
    git_parser = subparsers.add_parser("git", help="Manage git repository for ~/.agentrc hub")
    git_parser.add_argument("action", choices=["status", "init"], default="status", nargs="?", help="Git action to perform (default: status)")
    git_parser.add_argument("--remote-url", default=None, help="Remote repository URL for init")

    # connect
    connect_parser = subparsers.add_parser("connect", help="Connect an AI coding assistant (Cursor, Windsurf, Codex, etc.)")
    connect_parser.add_argument("platform", choices=["cursor", "windsurf", "codex", "claude", "gemini"], help="AI platform to connect")
    connect_parser.add_argument("--target-dir", default=None, help="Custom target directory for the assistant")

    # export
    export_parser = subparsers.add_parser("export", help="Generate consolidated prompt block for web/desktop AI interfaces")
    export_parser.add_argument("target", choices=["chatgpt", "claude", "cursor"], help="Target AI platform export format")
    export_parser.add_argument("-o", "--output", default=None, help="Output file path (default: ~/.agentrc/export/<target>_custom_instructions.md)")
    export_parser.add_argument("--stdout", action="store_true", help="Print prompt block directly to stdout")

    args = parser.parse_args()

    if args.home:
        custom_p = Path(args.home).resolve()
        set_custom_home(custom_p)
        print(f"[agentrc sandbox] Operating isolated in: {custom_p}")

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "detect":
        res = detect_platforms()
        print("=== agentrc Platform Detection ===")
        print(f"Hub Status: {'Initialized' if res['hub']['exists'] else 'Not initialized'}")
        print(f"Hub Path:   {res['hub']['path']}")
        print(f"Skills:     {res['hub']['skills_count']} skills registered")
        print("\n=== Detected AI Platforms ===")
        for key, p in res["platforms"].items():
            status = "FOUND" if p["detected"] else "NOT FOUND"
            print(f"- {p['name']}: [{status}] ({p['path']})")
            if key == "antigravity" and p["detected"]:
                print(f"    Rules: {'OK' if p['rules_exists'] else 'Missing'} | Skills Linked: {p['skills_linked']}")
            elif key == "claude" and p["detected"]:
                print(f"    Rules: {'OK' if p['rules_exists'] else 'Missing'} | Junction: {p['skills_is_junction']}")
            elif key == "codex" and p["detected"]:
                print(f"    Rules: {'OK' if p['rules_exists'] else 'Missing'} | Skills Linked: {p['skills_linked']}")
            elif key == "cursor" and p["detected"]:
                print(f"    Rules: {'OK' if p.get('rules_exists') else 'Missing'} | Skills Linked: {p.get('skills_linked')}")
            elif key == "windsurf" and p["detected"]:
                print(f"    Rules: {'OK' if p.get('rules_exists') else 'Missing'} | Skills Linked: {p.get('skills_linked')}")

    elif args.command == "init":
        templates_path = Path(args.templates) if args.templates else None
        if not templates_path:
            # Check default templates bundled with package
            repo_templates = Path(__file__).resolve().parent.parent.parent / "templates"
            if repo_templates.is_dir():
                templates_path = repo_templates

        res = init_hub(template_dir=templates_path, force=args.force)
        print("=== agentrc Initialized ===")
        print(f"Hub Path: {res['hub_dir']}")
        print(f"Backed up files: {len(res['backed_up_files'])}")
        for f in res["backed_up_files"]:
            print(f"  + {f}")
        print(f"Templates populated: {len(res['copied_templates'])}")

    elif args.command == "link":
        print("=== Linking Skills across Platforms ===")
        ok_claude, msg_claude = link_skills_for_claude()
        print(f"Claude Code: {'[OK]' if ok_claude else '[WARN]'} {msg_claude}")

        ok_gemini, msg_gemini = link_skills_for_gemini()
        print(f"Antigravity: {'[OK]' if ok_gemini else '[WARN]'} {msg_gemini}")

        ok_codex, msg_codex = link_skills_for_codex()
        print(f"Codex / ChatGPT: {'[OK]' if ok_codex else '[WARN]'} {msg_codex}")

        ok_m, msg_m = project_codex_skill_manifests()
        print(f"Codex Manifests: {'[OK]' if ok_m else '[WARN]'} {msg_m}")

    elif args.command == "project":
        print("=== Projecting Rules and Subagents ===")
        ok_g, msg_g = project_gemini_rules()
        print(f"Antigravity GEMINI.md: {'[OK]' if ok_g else '[FAIL]'} {msg_g}")

        ok_c, msg_c = project_claude_rules()
        print(f"Claude CLAUDE.md:     {'[OK]' if ok_c else '[FAIL]'} {msg_c}")

        ok_x, msg_x = project_codex_rules()
        print(f"Codex AGENTS.md:      {'[OK]' if ok_x else '[FAIL]'} {msg_x}")

        from agentrc.projector import project_cursor_rules, project_windsurf_rules
        ok_cur, msg_cur = project_cursor_rules()
        print(f"Cursor rules:         {'[OK]' if ok_cur else '[FAIL]'} {msg_cur}")

        ok_ws, msg_ws = project_windsurf_rules()
        print(f"Windsurf rules:       {'[OK]' if ok_ws else '[FAIL]'} {msg_ws}")

        ok_a, msgs_a = project_subagents()
        print(f"Subagents:            {'[OK]' if ok_a else '[FAIL]'}")
        for m in msgs_a:
            print(f"  + {m}")

    elif args.command == "doctor":
        res = run_doctor(fix=args.fix)
        print(f"=== agentrc Doctor Audit: [{res['status']}] ===")
        for c in res["passed_checks"]:
            print(f"  [PASS] {c}")
        for i in res["issues"]:
            print(f"  [WARN] {i}")
        if res["repairs"]:
            print("\n=== Repairs Applied ===")
            for r in res["repairs"]:
                print(f"  * {r}")

    elif args.command == "budget":
        b = audit_budget()
        print("=== Startup Boot Token Budget Audit ===")
        print(f"Total Boot Tokens: {b['total_boot_tokens']} / {b['budget']} tokens [{b['status']}]")
        print(f"  - Core Rules:      ~{b['core_rules_tokens']} tokens")
        print(f"  - Skills Registry: ~{b['skills_registry_tokens']} tokens ({b['skills_count']} skills)")

    elif args.command == "hook":
        if args.event == "session-start":
            sys.exit(run_session_start_hook())

    elif args.command == "diff":
        from agentrc.promoter import detect_rule_drift
        report = detect_rule_drift()
        print("=== agentrc Rule Drift Audit ===")
        platforms = ["gemini", "claude", "codex"] if args.platform == "all" else [args.platform]
        drift_count = 0
        has_removals = False
        for p in platforms:
            info = report.get(p, {})
            name = {"gemini": "Google Antigravity", "claude": "Claude Code", "codex": "OpenAI Codex"}.get(p, p)
            if not info.get("exists", False):
                print(f"- {name}: [NOT FOUND] ({info.get('file')})")
                continue
            if not info.get("has_drift", False):
                print(f"- {name}: [IN SYNC] No drift detected")
            else:
                drift_count += 1
                print(f"- {name}: [DRIFT DETECTED] ({info.get('file')})")
                for c in info.get("added", []):
                    hdr = c.header or "(prelude)"
                    print(f"    + Added:    {hdr} (path: {' > '.join(c.path)})")
                for m in info.get("modified", []):
                    hdr = m['source'].header or "(prelude)"
                    print(f"    * Modified: {hdr}")
                for r in info.get("removed", []):
                    hdr = r.header or "(prelude)"
                    print(f"    - Removed:  {hdr}")
                    has_removals = True
        if drift_count == 0:
            print("\nAll platforms are synchronized with ~/.agentrc hub rules.")
        else:
            print(f"\nRule drift detected in {drift_count} platform(s). Use 'agentrc promote' to sync back to hub.")
            if has_removals:
                print("Note: Downstream rule removals cannot be automatically promoted; delete them directly from ~/.agentrc/rules/ to synchronize.")

    elif args.command == "promote":
        from agentrc.promoter import detect_rule_drift, promote_chunk
        from agentrc.projector import project_gemini_rules, project_claude_rules, project_codex_rules
        import shutil
        import datetime

        report = detect_rule_drift()
        plat_info = report.get(args.from_platform, {})
        if not plat_info.get("exists", False):
            print(f"Error: Target platform '{args.from_platform}' rules file does not exist ({plat_info.get('file')})")
            sys.exit(1)

        drifted = plat_info.get("added", []) + [m["source"] for m in plat_info.get("modified", [])]
        if not drifted:
            print(f"No rule drift found in platform '{args.from_platform}'. Nothing to promote.")
            sys.exit(0)

        to_promote = []
        if args.header:
            target_hdr = args.header.strip().lower()
            for c in drifted:
                if target_hdr in c.header.lower():
                    to_promote.append(c)
            if not to_promote:
                print(f"Error: No drifted chunk matching header '{args.header}' found in {args.from_platform}.")
                sys.exit(1)
        else:
            to_promote = drifted

        # If selective promotion is performed, back up downstream file to prevent data loss upon reprojection
        if len(to_promote) < len(drifted):
            downstream_file = Path(plat_info["file"])
            if downstream_file.is_file():
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = downstream_file.with_suffix(f".backup_{ts}.md")
                shutil.copy2(downstream_file, backup_path)
                print(f"[agentrc safety] Backed up {downstream_file.name} to {backup_path.name}")

        print(f"=== Promoting {len(to_promote)} Rule(s) from {args.from_platform} to {args.target} ===")
        has_failure = False
        for chunk in to_promote:
            ok, msg = promote_chunk(chunk, target_rule_file=args.target, reproject=False)
            print(f"  {'[OK]' if ok else '[FAIL]'} {msg}")
            if not ok:
                has_failure = True

        if not has_failure:
            project_gemini_rules()
            project_claude_rules()
            project_codex_rules()
            from agentrc.projector import project_cursor_rules, project_windsurf_rules
            project_cursor_rules()
            project_windsurf_rules()
            print("[OK] Reprojected rules across all platforms.")
        else:
            print("[FAIL] Promotion failed; skipped reprojection.")
            sys.exit(1)

    elif args.command == "mcp":
        from agentrc.mcp_sync import get_mcp_status, sync_mcp_servers
        if args.action == "status":
            st = get_mcp_status()
            print("=== agentrc MCP Registry Status ===")
            print(f"Hub Status:       {'Configured' if st['hub']['exists'] else 'Missing'} ({st['hub']['path']})")
            print(f"Registered in Hub: {len(st['hub']['servers'])} server(s)")
            for name, cfg in st["hub"]["servers"].items():
                kind = cfg.get("type") or ("http" if "url" in cfg else "stdio")
                target = cfg.get("url") or cfg.get("command", "")
                print(f"  * {name} [{kind}]: {target}")

            print("\n=== AI Platform MCP Sync Status ===")
            print(f"- Claude Code:     {len(st['claude']['servers'])} server(s)")
            print(f"- Antigravity:     {len(st['gemini']['servers'])} server(s)")
            print(f"\nOverall Sync:      {'[IN SYNC]' if st['in_sync'] else '[DRIFT DETECTED]'}")
            if st["missing_in_claude"]:
                print(f"  ! Missing in Claude:     {', '.join(st['missing_in_claude'])}")
            if st["missing_in_gemini"]:
                print(f"  ! Missing in Antigravity:{', '.join(st['missing_in_gemini'])}")
            if st["untracked_in_claude"]:
                print(f"  + Untracked in Claude:   {', '.join(st['untracked_in_claude'])}")
            if st["untracked_in_gemini"]:
                print(f"  + Untracked in Antigrav: {', '.join(st['untracked_in_gemini'])}")
            if not st["in_sync"]:
                print("\nRun 'agentrc mcp sync' to bidirectionally synchronize MCP servers.")

        elif args.action == "sync":
            print("=== Synchronizing MCP Servers across All Platforms ===")
            ok, actions = sync_mcp_servers()
            for a in actions:
                print(f"  + {a}")
            print(f"\nResult: {'[OK] Complete' if ok else '[FAIL]'}")

    elif args.command == "push":
        from agentrc.git_sync import git_push
        ok, msg = git_push(message=args.message, remote=args.remote)
        print(f"=== agentrc Hub Push: {'[OK]' if ok else '[FAIL]'} ===")
        print(msg)
        if not ok:
            sys.exit(1)

    elif args.command == "pull":
        from agentrc.git_sync import git_pull
        ok, msg = git_pull(remote=args.remote, reproject=not args.no_reproject)
        print(f"=== agentrc Hub Pull: {'[OK]' if ok else '[FAIL]'} ===")
        print(msg)
        if not ok:
            sys.exit(1)

    elif args.command == "git":
        from agentrc.git_sync import git_status, git_init_hub
        if args.action == "status":
            st = git_status()
            print("=== agentrc Hub Git Status ===")
            if not st.get("git_installed", False):
                print("Git is not installed or not found in PATH.")
                sys.exit(1)
            if not st.get("is_repo", False):
                print("Hub is not a git repository. Run 'agentrc git init' to initialize.")
                sys.exit(0)
            print(f"Branch:   {st.get('branch', 'unknown')}")
            print(f"Status:   {'Clean' if st.get('is_clean') else 'Uncommitted changes'}")
            remotes = st.get("remotes", {})
            if remotes:
                print("Remotes:")
                for rname, rurl in remotes.items():
                    print(f"  * {rname}: {rurl}")
            else:
                print("Remotes:  None configured")
            if st.get("modified"):
                print("Modified files:")
                for f in st["modified"]:
                    print(f"  * {f}")
            if st.get("untracked"):
                print("Untracked files:")
                for f in st["untracked"]:
                    print(f"  + {f}")

        elif args.action == "init":
            ok, msg = git_init_hub(remote_url=args.remote_url)
            print(f"=== agentrc Git Init: {'[OK]' if ok else '[FAIL]'} ===")
            print(msg)
            if not ok:
                sys.exit(1)

    elif args.command == "connect":
        from agentrc.connect import connect_platform
        target_path = Path(args.target_dir).resolve() if args.target_dir else None
        ok, msg = connect_platform(args.platform, target_dir=target_path)
        print(f"=== agentrc Connect {args.platform}: {'[OK]' if ok else '[FAIL]'} ===")
        print(msg)
        if not ok:
            sys.exit(1)

    elif args.command == "export":
        from agentrc.exporter import export_prompt_block
        ok, content, final_path = export_prompt_block(args.target, output_path=args.output)
        if not ok:
            print(f"Error: {content}")
            sys.exit(1)
        if args.stdout:
            print(content, end="")
        else:
            print(f"=== agentrc Prompt Block Export: [OK] ===")
            print(f"Platform: {args.target}")
            print(f"Exported to: {final_path}")
            print(f"Size: {len(content)} characters (~{len(content.split())} words)")
            print("\nPreview (first 10 lines):")
            for line in content.splitlines()[:10]:
                print(f"  {line}")


if __name__ == "__main__":
    main()
