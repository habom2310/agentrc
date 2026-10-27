import unittest
from pathlib import Path
import sys
import tempfile

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.projector import parse_frontmatter, project_subagents


class TestProjector(unittest.TestCase):
    def test_parse_frontmatter(self):
        sample = """---
name: sample-agent
tier: pro
effort: medium
---

Body of agent.
"""
        meta, body = parse_frontmatter(sample)
        self.assertEqual(meta.get("name"), "sample-agent")
        self.assertEqual(meta.get("tier"), "pro")
        self.assertEqual(meta.get("effort"), "medium")
        self.assertIn("Body of agent.", body)

    def test_parse_frontmatter_multiline(self):
        sample = """---
name: multi-agent
description: >
  Line one of description.
  Line two of description.
tier: fast
---

Agent prompt body.
"""
        meta, body = parse_frontmatter(sample)
        self.assertEqual(meta.get("name"), "multi-agent")
        self.assertEqual(meta.get("description"), "Line one of description. Line two of description.")
        self.assertEqual(meta.get("tier"), "fast")
        self.assertIn("Agent prompt body.", body)

    def _project(self, agent_md: str) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            hub = Path(tmp) / "hub"
            (hub / "agents").mkdir(parents=True)
            (hub / "agents" / "sample.md").write_text(agent_md, encoding="utf-8")
            set_custom_home(home, hub)
            try:
                ok, _ = project_subagents()
                self.assertTrue(ok)
                claude = (home / ".claude" / "agents" / "sample.md").read_text(encoding="utf-8")
                agy = (home / ".gemini" / "config" / "agents" / "sample.md").read_text(encoding="utf-8")
            finally:
                set_custom_home(None, None)
        return claude, agy

    def test_project_subagents_claude_fields_passthrough(self):
        agent_md = """---
name: sample
description: Sample agent
tier: fast
effort: medium
mode: read-write
claude_model: claude-haiku-5-5
claude_tools: Bash, Read, Edit, Write, Grep, Glob, ToolSearch, mcp__codegraph__codegraph_explore
permissionMode: auto
omitClaudeMd: true
---

Agent body.
"""
        claude, agy = self._project(agent_md)
        self.assertIn("model: claude-haiku-5-5\n", claude)
        self.assertIn("permissionMode: auto\n", claude)
        self.assertIn("omitClaudeMd: true\n", claude)
        self.assertIn(
            "tools: Bash, Read, Edit, Write, Grep, Glob, ToolSearch, mcp__codegraph__codegraph_explore\n",
            claude,
        )
        self.assertLess(claude.index("effort: medium"), claude.index("permissionMode: auto"))
        self.assertLess(claude.index("omitClaudeMd: true"), claude.index("tools: Bash"))
        self.assertNotIn("model: haiku\n", claude)

        self.assertNotIn("claude_model", agy)
        self.assertNotIn("claude_tools", agy)
        self.assertNotIn("permissionMode", agy)
        self.assertNotIn("omitClaudeMd", agy)

    def test_project_subagents_legacy_output_unchanged(self):
        agent_md = """---
name: sample
description: Sample agent
tier: pro
effort: high
mode: read-only
---

Agent body.
"""
        claude, _ = self._project(agent_md)
        expected = (
            "---\n"
            "name: sample\n"
            "description: Sample agent\n"
            "model: sonnet\n"
            "effort: high\n"
            "tools: Bash, Read, Glob, Grep\n"
            "---\n"
            "\n"
            "Agent body.\n"
        )
        self.assertEqual(claude, expected)


if __name__ == "__main__":
    unittest.main()
