import unittest
import tempfile
import os
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.linker import link_skills_for_claude


class TestLinkerSkillMigration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home_dir = self.root / "home"
        self.hub_dir = self.home_dir / ".agentrc"
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.hub_dir.mkdir(parents=True, exist_ok=True)

        set_custom_home(self.home_dir, self.hub_dir)

    def tearDown(self):
        set_custom_home(None, None)
        self.temp_dir.cleanup()

    def test_migrate_keeps_symlinked_skill_and_copies_regular_skill(self):
        # Real source for the symlinked skill lives outside ~/.claude/skills
        source = self.root / "ripwire" / "skills" / "ripwire-find-bug"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("---\nname: ripwire-find-bug\n---\n", encoding="utf-8")

        claude_skills = self.home_dir / ".claude" / "skills"
        claude_skills.mkdir(parents=True)
        (claude_skills / "ripwire-find-bug").symlink_to(source, target_is_directory=True)

        regular = claude_skills / "my-skill"
        regular.mkdir()
        (regular / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")

        ok, _ = link_skills_for_claude()
        self.assertTrue(ok)

        hub_skills = self.hub_dir / "skills"

        linked = hub_skills / "ripwire-find-bug"
        self.assertTrue(linked.is_symlink())
        self.assertEqual(os.readlink(linked), str(source))
        self.assertEqual(linked.resolve(), source.resolve())

        copied = hub_skills / "my-skill"
        self.assertFalse(copied.is_symlink())
        self.assertTrue(copied.is_dir())
        self.assertTrue((copied / "SKILL.md").is_file())

    def test_migrate_resolves_relative_skill_symlink_against_original_dir(self):
        # Target "../rel-skill" is valid from ~/.claude/skills but not from ~/.agentrc/skills
        source = self.home_dir / ".claude" / "rel-skill"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("---\nname: rel-skill\n---\n", encoding="utf-8")

        claude_skills = self.home_dir / ".claude" / "skills"
        claude_skills.mkdir(parents=True)
        os.symlink("../rel-skill", claude_skills / "rel-skill")

        ok, _ = link_skills_for_claude()
        self.assertTrue(ok)

        linked = self.hub_dir / "skills" / "rel-skill"
        self.assertTrue(linked.is_symlink())
        self.assertTrue(os.path.isabs(os.readlink(linked)))
        self.assertEqual(linked.resolve(), source.resolve())
        self.assertTrue((linked / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
