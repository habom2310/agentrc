"""
Unit and integration tests for agentrc uninstaller.
Tests backup restoration, junction cleanup, rule/subagent removal,
path traversal defenses, dry-run immutability, and purge safety guards.
"""

import unittest
import tempfile
import shutil
import os
import sys
from pathlib import Path
from unittest.mock import patch

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.linker import create_junction
from agentrc.uninstaller import (
    find_earliest_backup,
    restore_from_backup,
    cleanup_junctions,
    cleanup_generated_rules,
    uninstall_hub,
)


class TestUninstaller(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temp_dir.name).resolve()
        self.home = self.sandbox / "user_home"
        self.hub = self.sandbox / "user_home" / ".agentrc"

        self.home.mkdir(parents=True, exist_ok=True)
        self.hub.mkdir(parents=True, exist_ok=True)
        (self.hub / "skills").mkdir(parents=True, exist_ok=True)
        (self.hub / "agents").mkdir(parents=True, exist_ok=True)
        (self.hub / "backups").mkdir(parents=True, exist_ok=True)

        set_custom_home(self.home, self.hub)

    def tearDown(self):
        set_custom_home(None, None)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_find_earliest_backup(self):
        # Empty backups
        self.assertIsNone(find_earliest_backup(self.hub))

        # Create multiple backups out of order
        b3 = self.hub / "backups" / "pre-agentrc-20261026_120000Z"
        b1 = self.hub / "backups" / "pre-agentrc-20261020_080000Z"
        b2 = self.hub / "backups" / "pre-agentrc-20261022_150000Z"
        other = self.hub / "backups" / "other-backup-20261019_000000Z"

        for b in [b3, b1, b2, other]:
            b.mkdir(parents=True, exist_ok=True)

        earliest = find_earliest_backup(self.hub)
        self.assertIsNotNone(earliest)
        self.assertEqual(earliest.name, "pre-agentrc-20261020_080000Z")

    def test_backup_restoration(self):
        backup_dir = self.hub / "backups" / "pre-agentrc-20261020_080000Z"
        claude_cfg = backup_dir / ".claude" / "CLAUDE.md"
        claude_cfg.parent.mkdir(parents=True, exist_ok=True)
        claude_cfg.write_text("# Original Claude Config\nKeep me", encoding="utf-8")

        gemini_cfg = backup_dir / ".gemini" / "config" / "skills.json"
        gemini_cfg.parent.mkdir(parents=True, exist_ok=True)
        gemini_cfg.write_text('{"entries": []}', encoding="utf-8")

        # Destination in home currently has modified/agentrc content
        dest_claude = self.home / ".claude" / "CLAUDE.md"
        dest_claude.parent.mkdir(parents=True, exist_ok=True)
        dest_claude.write_text("agentrc modified rules", encoding="utf-8")

        restored = restore_from_backup(backup_dir, self.home, dry_run=False)

        self.assertIn(".claude/CLAUDE.md", restored)
        self.assertIn(".gemini/config/skills.json", restored)
        self.assertEqual(dest_claude.read_text(encoding="utf-8"), "# Original Claude Config\nKeep me")
        self.assertTrue((self.home / ".gemini" / "config" / "skills.json").is_file())

    def test_path_traversal_guard(self):
        backup_dir = self.hub / "backups" / "pre-agentrc-20261020_080000Z"
        sub = backup_dir / "subdir"
        sub.mkdir(parents=True, exist_ok=True)
        evil_file = sub / "evil.txt"
        evil_file.write_text("malicious payload", encoding="utf-8")

        # Mock relative_to to return a path traversal sequence
        with patch.object(Path, "relative_to", return_value=Path("../../evil.txt")):
            with self.assertRaises(ValueError) as ctx:
                restore_from_backup(backup_dir, self.home)
            self.assertIn("Path traversal detected", str(ctx.exception))

    def test_junction_unlinking_and_skills_old_restoration(self):
        claude_skills = self.home / ".claude" / "skills"
        claude_skills_old = self.home / ".claude" / "skills.old"
        claude_skills.parent.mkdir(parents=True, exist_ok=True)

        # Create original backup skills folder
        old_tool = claude_skills_old / "my-native-skill"
        old_tool.mkdir(parents=True, exist_ok=True)
        (old_tool / "SKILL.md").write_text("# Native Skill", encoding="utf-8")

        # Create junction to agentrc skills
        hub_skills = self.hub / "skills"
        ok, msg = create_junction(claude_skills, hub_skills)
        self.assertTrue(ok, f"Failed creating test junction: {msg}")

        # Run cleanup
        res = cleanup_junctions(self.home, self.hub, dry_run=False)

        self.assertIn(".claude/skills", res["unlinked"])
        self.assertIn(".claude/skills", res["restored"])

        # Junction should be gone, replaced by regular skills.old folder renamed to skills
        self.assertFalse(claude_skills_old.exists())
        self.assertTrue(claude_skills.is_dir())
        self.assertFalse(claude_skills.is_symlink())
        if hasattr(claude_skills, "is_junction"):
            self.assertFalse(claude_skills.is_junction())
        self.assertTrue((claude_skills / "my-native-skill" / "SKILL.md").is_file())

    def test_non_agentrc_junction_preservation(self):
        other_skills = self.sandbox / "other_custom_skills"
        other_skills.mkdir(parents=True, exist_ok=True)
        (other_skills / "test.txt").write_text("hello", encoding="utf-8")

        codex_skills = self.home / ".codex" / "skills"
        codex_skills.parent.mkdir(parents=True, exist_ok=True)
        ok, msg = create_junction(codex_skills, other_skills)
        self.assertTrue(ok, f"Failed creating junction: {msg}")

        res = cleanup_junctions(self.home, self.hub, dry_run=False)

        self.assertEqual(len(res["unlinked"]), 0)
        self.assertTrue(os.path.lexists(codex_skills))
        self.assertEqual(codex_skills.resolve(), other_skills.resolve())

    def test_generated_rules_cleanup(self):
        # Create generated rules
        cursor_mdc = self.home / ".cursor" / "rules" / "agentrc.mdc"
        cursor_mdc.parent.mkdir(parents=True, exist_ok=True)
        cursor_mdc.write_text("agentrc rule mdc", encoding="utf-8")

        cursorrules = self.home / ".cursorrules"
        cursorrules.write_text("<!-- autogenerated by agentrc -->\nsome rules", encoding="utf-8")

        windsurfrules = self.home / ".windsurfrules"
        windsurfrules.write_text("agentrc windsurf rules", encoding="utf-8")

        gemini_md = self.home / ".gemini" / "GEMINI.md"
        gemini_md.parent.mkdir(parents=True, exist_ok=True)
        gemini_md.write_text("<!-- AUTOGENERATED BY AGENTRC -->", encoding="utf-8")

        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir(parents=True, exist_ok=True)
        claude_md.write_text("@.agentrc/rules/common.md", encoding="utf-8")

        # Create subagent
        scout_ag = self.home / ".claude" / "agents" / "scout.md"
        scout_ag.parent.mkdir(parents=True, exist_ok=True)
        scout_ag.write_text("---\nname: scout\n---\nautogenerated by agentrc", encoding="utf-8")

        # Create non-agentrc user rule (should NOT be removed)
        user_rule = self.home / ".codex" / "AGENTS.md"
        user_rule.parent.mkdir(parents=True, exist_ok=True)
        user_rule.write_text("# My Personal Prompt\nDo not delete me", encoding="utf-8")

        # Create GEMINI.md.backup to verify restoration
        gemini_backup = self.home / ".gemini" / "GEMINI.md.backup"
        gemini_backup.write_text("# Original Pre-Agentrc Gemini", encoding="utf-8")

        # Simulate that claude_md was restored from pre-agentrc backup
        restored_files = {".claude/CLAUDE.md"}

        removed = cleanup_generated_rules(self.home, self.hub, restored_files, dry_run=False)

        self.assertIn(".cursor/rules/agentrc.mdc", removed)
        self.assertIn(".cursorrules", removed)
        self.assertIn(".windsurfrules", removed)
        self.assertIn(".claude/agents/scout.md", removed)
        self.assertNotIn(".claude/CLAUDE.md", removed)  # Preserved because in restored_files

        # Check file existence
        self.assertFalse(cursor_mdc.exists())
        self.assertFalse(cursorrules.exists())
        self.assertFalse(windsurfrules.exists())
        self.assertFalse(scout_ag.exists())
        self.assertTrue(claude_md.exists())
        self.assertTrue(user_rule.exists())

        # Check backup restoration
        self.assertFalse(gemini_backup.exists())
        self.assertTrue(gemini_md.exists())
        self.assertEqual(gemini_md.read_text(encoding="utf-8"), "# Original Pre-Agentrc Gemini")

    def test_dry_run_immutability(self):
        # Create backup
        backup_dir = self.hub / "backups" / "pre-agentrc-20261020_000000Z"
        b_file = backup_dir / ".claude" / "CLAUDE.md"
        b_file.parent.mkdir(parents=True, exist_ok=True)
        b_file.write_text("Old Claude", encoding="utf-8")

        # Create live file in home
        live_file = self.home / ".claude" / "CLAUDE.md"
        live_file.parent.mkdir(parents=True, exist_ok=True)
        live_file.write_text("agentrc active", encoding="utf-8")

        # Create junction
        claude_skills = self.home / ".claude" / "skills"
        ok, msg = create_junction(claude_skills, self.hub / "skills")
        self.assertTrue(ok)

        # Create generated rule
        cursorrules = self.home / ".cursorrules"
        cursorrules.write_text("agentrc rules", encoding="utf-8")

        # Execute in dry-run mode with purge=True
        res = uninstall_hub(home=self.home, hub=self.hub, dry_run=True, purge=True)

        self.assertTrue(res["dry_run"])
        self.assertTrue(res["purged"])

        # Verify nothing was changed on disk
        self.assertEqual(live_file.read_text(encoding="utf-8"), "agentrc active")
        self.assertTrue(cursorrules.exists())
        self.assertTrue(os.path.lexists(claude_skills))
        self.assertTrue(self.hub.exists())

    def test_purge_sanity_checks_and_hub_directory_removal(self):
        # Sanity check: hub == home
        with self.assertRaises(ValueError) as ctx:
            uninstall_hub(home=self.home, hub=self.home, purge=True)
        self.assertIn("identical to home", str(ctx.exception))

        # Sanity check: hub == root
        root_dir = Path(self.home.resolve().anchor)
        with self.assertRaises(ValueError) as ctx:
            uninstall_hub(home=self.home, hub=root_dir, purge=True)
        self.assertIn("root directory", str(ctx.exception))

        # purge=False leaves hub intact
        res1 = uninstall_hub(home=self.home, hub=self.hub, purge=False)
        self.assertFalse(res1["purged"])
        self.assertTrue(self.hub.exists())

        # purge=True deletes hub directory
        res2 = uninstall_hub(home=self.home, hub=self.hub, purge=True)
        self.assertTrue(res2["purged"])
        self.assertFalse(self.hub.exists())

    def test_cli_uninstall_non_interactive_guard(self):
        from agentrc.cli import main
        with patch.object(sys, "argv", ["agentrc", "--home", str(self.home), "uninstall"]):
            with patch("sys.stdin.isatty", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)

    def test_cli_uninstall_interactive_cancel(self):
        from agentrc.cli import main
        with patch.object(sys, "argv", ["agentrc", "--home", str(self.home), "uninstall"]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("builtins.input", return_value="n"):
                    with self.assertRaises(SystemExit) as ctx:
                        main()
                    self.assertEqual(ctx.exception.code, 0)
        # Hub should still exist
        self.assertTrue(self.hub.exists())

    def test_cli_uninstall_yes_purge(self):
        from agentrc.cli import main
        with patch.object(sys, "argv", ["agentrc", "--home", str(self.home), "uninstall", "-y", "--purge"]):
            main()
        self.assertFalse(self.hub.exists())


if __name__ == "__main__":
    unittest.main()
