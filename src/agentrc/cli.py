"""
CLI entry point for agentrc.
"""

import argparse
import sys
import json
from pathlib import Path

from agentrc.detector import detect_platforms
from agentrc.scaffold import init_hub
from agentrc.linker import link_skills_for_claude, link_skills_for_gemini, link_skills_for_codex
from agentrc.projector import project_gemini_rules, project_claude_rules, project_codex_rules, project_subagents
from agentrc.doctor import run_doctor
from agentrc.token_budget import audit_budget
from agentrc.hook import run_session_start_hook


def main():
    parser = argparse.ArgumentParser(
        prog="agentrc",
        description="agentrc: Centralized Multi-AI Configuration & Skill Management Hub"
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

    args = parser.parse_args()

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

    elif args.command == "project":
        print("=== Projecting Rules and Subagents ===")
        ok_g, msg_g = project_gemini_rules()
        print(f"Antigravity GEMINI.md: {'[OK]' if ok_g else '[FAIL]'} {msg_g}")

        ok_c, msg_c = project_claude_rules()
        print(f"Claude CLAUDE.md:     {'[OK]' if ok_c else '[FAIL]'} {msg_c}")

        ok_x, msg_x = project_codex_rules()
        print(f"Codex AGENTS.md:      {'[OK]' if ok_x else '[FAIL]'} {msg_x}")

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


if __name__ == "__main__":
    main()
