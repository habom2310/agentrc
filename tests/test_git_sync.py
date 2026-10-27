import unittest
import tempfile
import subprocess
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.git_sync import (
    git_status,
    git_init_hub,
    git_push,
    git_pull,
    is_git_installed,
)
from agentrc.projector import project_gemini_rules


class TestGitSync(unittest.TestCase):
    def setUp(self):
        if not is_git_installed():
            self.skipTest("git is not installed on this system")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.home_dir = Path(self.temp_dir.name) / "home"
        self.hub_dir = self.home_dir / ".agentrc"

        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.hub_dir.mkdir(parents=True, exist_ok=True)
        (self.hub_dir / "rules").mkdir(parents=True, exist_ok=True)

        set_custom_home(self.home_dir, self.hub_dir)

    def tearDown(self):
        set_custom_home(None, None)
        self.temp_dir.cleanup()

    def test_git_status_on_non_git_dir(self):
        st = git_status(self.hub_dir)
        self.assertTrue(st["git_installed"])
        self.assertFalse(st["is_repo"])
        self.assertTrue(st["is_clean"])
        self.assertEqual(st["modified"], [])
        self.assertEqual(st["untracked"], [])
        self.assertEqual(st["remotes"], {})

    def test_git_init_and_gitignore(self):
        ok, msg = git_init_hub(self.hub_dir, remote_url="https://github.com/example/dotfiles.git")
        self.assertTrue(ok)
        self.assertTrue((self.hub_dir / ".git").exists())

        gitignore = self.hub_dir / ".gitignore"
        self.assertTrue(gitignore.is_file())
        gitignore_content = gitignore.read_text(encoding="utf-8")
        for entry in ["backups/", "*.backup_*", "*.tmp", "__pycache__/", "*.pyc", ".DS_Store", "Thumbs.db"]:
            self.assertIn(entry, gitignore_content)

        st = git_status(self.hub_dir)
        self.assertTrue(st["is_repo"])
        self.assertEqual(st["remotes"].get("origin"), "https://github.com/example/dotfiles.git")

    def test_git_push_locally_no_remote(self):
        ok, msg = git_init_hub(self.hub_dir)
        self.assertTrue(ok)

        rule_file = self.hub_dir / "rules" / "common.md"
        rule_file.write_text("## Coding Standards\nAlways write tests.\n", encoding="utf-8")

        ok, push_msg = git_push(self.hub_dir, message="Test local commit")
        self.assertTrue(ok)
        self.assertIn("No remote 'origin' configured", push_msg)

        st = git_status(self.hub_dir)
        self.assertTrue(st["is_clean"])
        self.assertEqual(st["modified"], [])
        self.assertEqual(st["untracked"], [])

    def test_git_push_with_configured_user_name(self):
        ok, msg = git_init_hub(self.hub_dir)
        self.assertTrue(ok)

        subprocess.run(["git", "config", "user.name", "Test Author"], cwd=self.hub_dir, check=True)
        subprocess.run(["git", "config", "user.email", "author@example.com"], cwd=self.hub_dir, check=True)

        rule_file = self.hub_dir / "rules" / "common.md"
        rule_file.write_text("## Rule\nContent\n", encoding="utf-8")

        ok, push_msg = git_push(self.hub_dir, message="Configured user commit")
        self.assertTrue(ok)

        res = subprocess.run(["git", "log", "-1", "--format=%an <%ae>"], cwd=self.hub_dir, capture_output=True, text=True, check=True)
        self.assertEqual(res.stdout.strip(), "Test Author <author@example.com>")

    def test_git_status_unstaged_modification_path_integrity(self):
        ok, msg = git_init_hub(self.hub_dir)
        self.assertTrue(ok)

        rule_file = self.hub_dir / "rules" / "common.md"
        rule_file.write_text("## Initial\n", encoding="utf-8")
        git_push(self.hub_dir, message="Initial commit")

        # Now make an unstaged modification
        rule_file.write_text("## Modified unstaged\n", encoding="utf-8")

        st = git_status(self.hub_dir)
        self.assertFalse(st["is_clean"])
        # Path must be exactly "rules/common.md", not truncated to "ules/common.md"
        self.assertIn("rules/common.md", [f.replace("\\", "/") for f in st["modified"]])

    def test_git_push_and_pull_with_bare_remote_reprojection(self):
        # 1. Bare remote with default branch main
        bare_remote = Path(self.temp_dir.name) / "remote.git"
        bare_remote.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(["git", "init", "--bare", "-b", "main", str(bare_remote)], capture_output=True)
        if res.returncode != 0:
            subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(bare_remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=False)

        # 2. Setup initial rule and initial projection
        common_md = self.hub_dir / "rules" / "common.md"
        common_md.write_text("## Rule Version 1\nInitial rule content\n", encoding="utf-8")
        project_gemini_rules()

        gemini_rules = self.home_dir / ".gemini" / "GEMINI.md"
        self.assertTrue(gemini_rules.is_file())
        self.assertIn("## Rule Version 1", gemini_rules.read_text(encoding="utf-8"))

        # 3. Init hub with bare remote
        ok, msg = git_init_hub(self.hub_dir, remote_url=str(bare_remote))
        self.assertTrue(ok)

        # 4. Push initial commit
        ok, msg = git_push(self.hub_dir, message="Initial hub commit", remote="origin", branch="main")
        self.assertTrue(ok)

        # 5. Clone bare remote to worker directory and push a change
        worker_dir = Path(self.temp_dir.name) / "worker"
        subprocess.run(["git", "clone", str(bare_remote), str(worker_dir)], check=True, capture_output=True)

        worker_rule = worker_dir / "rules" / "common.md"
        worker_rule.write_text("## Rule Version 2\nUpdated via federation\n", encoding="utf-8")

        subprocess.run(["git", "-C", str(worker_dir), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(worker_dir), "-c", "user.name=worker", "-c", "user.email=worker@local", "commit", "-m", "Remote update"],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "-C", str(worker_dir), "push", "origin", "main"], check=True, capture_output=True)

        # 6. Pull in hub with reproject=True
        ok, msg = git_pull(self.hub_dir, remote="origin", branch="main", reproject=True)
        self.assertTrue(ok)

        # Verify hub rule updated
        self.assertIn("## Rule Version 2", common_md.read_text(encoding="utf-8"))

        # Verify downstream GEMINI.md reprojected automatically
        self.assertIn("## Rule Version 2", gemini_rules.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
