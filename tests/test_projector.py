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


if __name__ == "__main__":
    unittest.main()
