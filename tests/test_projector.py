import unittest
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.projector import parse_frontmatter


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


if __name__ == "__main__":
    unittest.main()
