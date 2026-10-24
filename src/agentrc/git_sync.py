"""
Git dotfile federation for agentrc.
Provides git tracking, synchronization, and automated projection for ~/.agentrc hub.
"""

from pathlib import Path
import subprocess
import shutil
import datetime
from agentrc.detector import get_hub_dir

DEFAULT_GITIGNORE = """backups/
*.backup_*
*.tmp
__pycache__/
*.pyc
.DS_Store
Thumbs.db
"""


def is_git_installed() -> bool:
    """Checks if git executable is available in PATH."""
    return shutil.which("git") is not None


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Helper to run git commands with captured output."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def is_git_repo(hub_dir: Path) -> bool:
    """Checks whether the directory is an initialized git repository."""
    if not (hub_dir / ".git").exists():
        return False
    res = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=hub_dir)
    return res.returncode == 0 and res.stdout.strip() == "true"


def _ensure_gitignore(hub_dir: Path) -> None:
    """Ensures hub directory has the standard .gitignore entries."""
    gitignore = hub_dir / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text(DEFAULT_GITIGNORE, encoding="utf-8")
        return

    existing = gitignore.read_text(encoding="utf-8")
    needed_entries = [line.strip() for line in DEFAULT_GITIGNORE.splitlines() if line.strip()]
    to_append = [e for e in needed_entries if e not in existing]
    if to_append:
        separator = "\n" if existing.endswith("\n") else "\n\n"
        gitignore.write_text(existing + separator + "\n".join(to_append) + "\n", encoding="utf-8")


def git_status(hub_dir: Path | None = None) -> dict:
    """
    Reports whether hub is a git repo, current branch, whether working tree is clean,
    list of modified/untracked files, and remotes.
    """
    if hub_dir is None:
        hub_dir = get_hub_dir()

    if not is_git_installed():
        return {
            "git_installed": False,
            "is_repo": False,
            "branch": None,
            "is_clean": True,
            "modified": [],
            "untracked": [],
            "remotes": {},
        }

    if not is_git_repo(hub_dir):
        return {
            "git_installed": True,
            "is_repo": False,
            "branch": None,
            "is_clean": True,
            "modified": [],
            "untracked": [],
            "remotes": {},
        }

    # Detect current branch
    b_res = _run_git(["branch", "--show-current"], cwd=hub_dir)
    branch = b_res.stdout.strip()
    if not branch:
        r_res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=hub_dir)
        branch = r_res.stdout.strip()
        if branch == "HEAD":
            branch = "main"

    # Status porcelain
    st_res = _run_git(["status", "--porcelain"], cwd=hub_dir)
    modified = []
    untracked = []
    for raw_line in st_res.stdout.splitlines():
        if not raw_line or len(raw_line) < 3:
            continue
        code = raw_line[:2]
        path_str = raw_line[3:].strip()
        if code == "??":
            untracked.append(path_str)
        else:
            modified.append(path_str)

    # Remotes
    rem_res = _run_git(["remote", "-v"], cwd=hub_dir)
    remotes = {}
    for line in rem_res.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            remotes[parts[0]] = parts[1]

    return {
        "git_installed": True,
        "is_repo": True,
        "branch": branch,
        "is_clean": len(modified) == 0 and len(untracked) == 0,
        "modified": modified,
        "untracked": untracked,
        "remotes": remotes,
    }


def git_init_hub(hub_dir: Path | None = None, remote_url: str | None = None) -> tuple[bool, str]:
    """
    Initializes git repo in hub if not already one, creates .gitignore,
    and adds remote if provided.
    """
    if not is_git_installed():
        return False, "Git executable not found in PATH. Please install git."

    if hub_dir is None:
        hub_dir = get_hub_dir()

    hub_dir.mkdir(parents=True, exist_ok=True)

    if not is_git_repo(hub_dir):
        init_res = _run_git(["init", "-b", "main"], cwd=hub_dir)
        if init_res.returncode != 0:
            init_res = _run_git(["init"], cwd=hub_dir)
            if init_res.returncode != 0:
                return False, f"git init failed: {init_res.stderr.strip()}"

    _ensure_gitignore(hub_dir)

    if remote_url:
        rem_res = _run_git(["remote"], cwd=hub_dir)
        remotes = [r.strip() for r in rem_res.stdout.splitlines() if r.strip()]
        if "origin" in remotes:
            set_res = _run_git(["remote", "set-url", "origin", remote_url], cwd=hub_dir)
            if set_res.returncode != 0:
                return False, f"Failed to update origin remote URL: {set_res.stderr.strip()}"
        else:
            add_res = _run_git(["remote", "add", "origin", remote_url], cwd=hub_dir)
            if add_res.returncode != 0:
                return False, f"Failed to add origin remote: {add_res.stderr.strip()}"

    return True, f"Git repository initialized in {hub_dir}"


def git_push(
    hub_dir: Path | None = None,
    message: str | None = None,
    remote: str = "origin",
    branch: str | None = None,
) -> tuple[bool, str]:
    """
    Stages all files, commits with a timestamped or provided message,
    and pushes to the specified remote repository if configured.
    """
    if not is_git_installed():
        return False, "Git executable not found in PATH. Please install git."

    if hub_dir is None:
        hub_dir = get_hub_dir()

    if not is_git_repo(hub_dir):
        ok, msg = git_init_hub(hub_dir)
        if not ok:
            return False, f"Failed to initialize git repository: {msg}"
    else:
        _ensure_gitignore(hub_dir)

    # Stage all changes
    add_res = _run_git(["add", "-A"], cwd=hub_dir)
    if add_res.returncode != 0:
        return False, f"git add failed: {add_res.stderr.strip()}"

    # Check if there are changes to commit
    st_res = _run_git(["status", "--porcelain"], cwd=hub_dir)
    has_changes = bool(st_res.stdout.strip())
    if has_changes:
        if not message:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"agentrc sync: {now_str}"

        commit_res = _run_git(
            ["-c", "user.name=agentrc", "-c", "user.email=agentrc@local", "commit", "-m", message],
            cwd=hub_dir,
        )
        if commit_res.returncode != 0:
            return False, f"git commit failed: {commit_res.stderr.strip()}"

    # Check if remote exists
    rem_res = _run_git(["remote"], cwd=hub_dir)
    remotes = [r.strip() for r in rem_res.stdout.splitlines() if r.strip()]
    if remote not in remotes:
        return True, (
            f"Changes committed locally ({message or 'no new changes'}). "
            f"No remote '{remote}' configured. "
            f"To configure a remote: agentrc git init --remote-url <url>"
        )

    # Determine branch
    if not branch:
        status = git_status(hub_dir)
        branch = status.get("branch") or "main"

    push_res = _run_git(["push", "-u", remote, branch], cwd=hub_dir)
    if push_res.returncode != 0:
        push_res2 = _run_git(["push", remote, branch], cwd=hub_dir)
        if push_res2.returncode != 0:
            return False, f"git push failed: {push_res.stderr.strip() or push_res2.stderr.strip()}"

    return True, f"Successfully pushed to {remote}/{branch}"


def git_pull(
    hub_dir: Path | None = None,
    remote: str = "origin",
    branch: str | None = None,
    reproject: bool = True,
) -> tuple[bool, str]:
    """
    Pulls changes from remote and optionally triggers automatic reprojection
    across all configured AI coding platforms.
    """
    if not is_git_installed():
        return False, "Git executable not found in PATH. Please install git."

    if hub_dir is None:
        hub_dir = get_hub_dir()

    if not is_git_repo(hub_dir):
        return False, f"Hub directory {hub_dir} is not a git repository. Run 'agentrc git init' first."

    rem_res = _run_git(["remote"], cwd=hub_dir)
    remotes = [r.strip() for r in rem_res.stdout.splitlines() if r.strip()]
    if remote not in remotes:
        return False, f"Remote '{remote}' does not exist on {hub_dir}."

    if not branch:
        status = git_status(hub_dir)
        branch = status.get("branch") or "main"

    cmd = ["pull", remote, branch]
    pull_res = _run_git(cmd, cwd=hub_dir)
    if pull_res.returncode != 0:
        return False, f"git pull failed: {pull_res.stderr.strip()}"

    if reproject:
        from agentrc.projector import (
            project_gemini_rules,
            project_claude_rules,
            project_codex_rules,
            project_cursor_rules,
            project_windsurf_rules,
            project_subagents,
        )
        from agentrc.linker import project_codex_skill_manifests

        project_gemini_rules()
        project_claude_rules()
        project_codex_rules()
        project_cursor_rules()
        project_windsurf_rules()
        project_subagents()
        project_codex_skill_manifests(hub_dir)

    return True, f"Successfully pulled from {remote}. Reprojection {'applied' if reproject else 'skipped'}."
