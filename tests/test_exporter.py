import unittest
import tempfile
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.scaffold import init_hub
from agentrc.exporter import export_prompt_block, EXPORT_TARGETS


class TestExporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home_dir = Path(self.temp_dir.name) / "home"
        self.hub_dir = self.home_dir / ".agentrc"

        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.hub_dir.mkdir(parents=True, exist_ok=True)

        set_custom_home(self.home_dir, self.hub_dir)

        # Initialize hub with starter files
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        init_hub(template_dir=template_dir)

    def tearDown(self):
        set_custom_home(None, None)
        self.temp_dir.cleanup()

    def test_export_chatgpt(self):
        ok, content, dest = export_prompt_block("chatgpt", self.hub_dir)
        self.assertTrue(ok)
        self.assertIn("ChatGPT Custom Instructions", content)
        self.assertIn("1. Think Before Coding", content)
        self.assertIn("Codex Defaults & Overrides", content)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.name, "chatgpt_custom_instructions.md")

    def test_export_claude(self):
        ok, content, dest = export_prompt_block("claude", self.hub_dir)
        self.assertTrue(ok)
        self.assertIn("Claude Web Project System Instructions", content)
        self.assertIn("1. Think Before Coding", content)
        self.assertIn("Offload to Antigravity CLI (agy)", content)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.name, "claude_project_instructions.md")

    def test_export_cursor(self):
        ok, content, dest = export_prompt_block("cursor", self.hub_dir)
        self.assertTrue(ok)
        self.assertIn("Cursor .cursorrules Export", content)
        self.assertIn("1. Think Before Coding", content)
        self.assertIn("Cursor Defaults & Overrides", content)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.name, "cursor_rules_export.md")

    def test_export_custom_output_path(self):
        custom_out = Path(self.temp_dir.name) / "my_custom_prompt.txt"
        ok, content, dest = export_prompt_block("chatgpt", self.hub_dir, output_path=custom_out)
        self.assertTrue(ok)
        self.assertEqual(dest, custom_out)
        self.assertTrue(custom_out.is_file())

    def test_export_unsupported_platform(self):
        ok, msg, dest = export_prompt_block("invalid_platform", self.hub_dir)
        self.assertFalse(ok)
        self.assertIn("Unsupported export target", msg)
        self.assertIsNone(dest)


if __name__ == "__main__":
    unittest.main()
