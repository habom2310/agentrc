import unittest
import tempfile
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.chunker import parse_markdown_chunks
from agentrc.promoter import detect_rule_drift, promote_chunk
from agentrc.projector import project_gemini_rules


class TestPromoter(unittest.TestCase):
    def setUp(self):
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

    def test_detect_drift_and_promote(self):
        # 1. Populate hub with initial rule
        common_md = self.hub_dir / "rules" / "common.md"
        common_md.write_text("## Coding Guidelines\nWrite simple, verifiable code.\n", encoding="utf-8")

        # 2. Project rules downstream
        ok, msg = project_gemini_rules()
        self.assertTrue(ok)
        gemini_rules = self.home_dir / ".gemini" / "GEMINI.md"
        self.assertTrue(gemini_rules.is_file())

        # 3. Initial drift check: should be in sync
        drift = detect_rule_drift(self.home_dir, self.hub_dir)
        self.assertFalse(drift["gemini"]["has_drift"])
        self.assertEqual(len(drift["gemini"]["added"]), 0)

        # 4. Simulate downstream edit: append new rule to GEMINI.md
        current_content = gemini_rules.read_text(encoding="utf-8")
        extra_rule = "\n\n## Custom Drift Rule\nNever skip linting before push.\n"
        gemini_rules.write_text(current_content + extra_rule, encoding="utf-8")

        # 5. Detect drift
        drift_after = detect_rule_drift(self.home_dir, self.hub_dir)
        self.assertTrue(drift_after["gemini"]["has_drift"])
        self.assertEqual(len(drift_after["gemini"]["added"]), 1)
        added_chunk = drift_after["gemini"]["added"][0]
        self.assertEqual(added_chunk.header, "Custom Drift Rule")

        # 6. Promote chunk into common.md
        p_ok, p_msg = promote_chunk(added_chunk, target_rule_file="common.md", hub_dir=self.hub_dir)
        self.assertTrue(p_ok)

        # 7. Verify common.md now has the promoted rule
        updated_common = common_md.read_text(encoding="utf-8")
        self.assertIn("## Custom Drift Rule", updated_common)

        # 8. Verify GEMINI.md was reprojected and drift is now resolved
        drift_final = detect_rule_drift(self.home_dir, self.hub_dir)
        self.assertFalse(drift_final["gemini"]["has_drift"])
        self.assertEqual(len(drift_final["gemini"]["added"]), 0)

    def test_modify_in_place_with_crlf_and_spacing(self):
        # File with CRLF and two sections
        common_md = self.hub_dir / "rules" / "common.md"
        common_md.write_bytes(
            b"## Section One\r\nInitial text one.\r\n\r\n## Section Two\r\nText two.\r\n"
        )

        # Create updated chunk for Section One
        updated_text = "## Section One\nModified text one.\n"
        updated_chunk = parse_markdown_chunks(updated_text)[0]

        ok, msg = promote_chunk(updated_chunk, target_rule_file="common.md", hub_dir=self.hub_dir, reproject=False)
        self.assertTrue(ok)

        content = common_md.read_text(encoding="utf-8")
        # Ensure Section One was updated in place and Section Two was preserved with clean header delimiter
        self.assertIn("## Section One\nModified text one.", content)
        self.assertIn("\n\n## Section Two\nText two.", content)
        # Ensure it was not duplicated at the end
        self.assertEqual(content.count("## Section One"), 1)

    def test_nested_subsection_promotion(self):
        common_md = self.hub_dir / "rules" / "common.md"
        common_md.write_text(
            "## Parent Section\nParent body.\n\n## Unrelated Section\nUnrelated body.\n",
            encoding="utf-8"
        )

        child_text = "## Parent Section\nParent body.\n\n### Child Section\nChild body.\n"
        child_chunk = parse_markdown_chunks(child_text)[1]
        self.assertEqual(child_chunk.path, ("Parent Section", "Child Section"))

        ok, msg = promote_chunk(child_chunk, target_rule_file="common.md", hub_dir=self.hub_dir, reproject=False)
        self.assertTrue(ok)

        content = common_md.read_text(encoding="utf-8")
        # Verify Child Section is inserted right after Parent Section, before Unrelated Section
        self.assertTrue(content.index("### Child Section") > content.index("## Parent Section"))
        self.assertTrue(content.index("### Child Section") < content.index("## Unrelated Section"))

    def test_path_traversal_prevention(self):
        chunk = parse_markdown_chunks("## Bad Rule\nContent\n")[0]
        ok, msg = promote_chunk(chunk, target_rule_file="../../escaped.md", hub_dir=self.hub_dir, reproject=False)
        self.assertFalse(ok)
        self.assertIn("must reside inside hub rules directory", msg)

    def test_deeply_nested_siblings_promotion(self):
        common_md = self.hub_dir / "rules" / "common.md"
        common_md.write_text(
            "## Parent Section\nParent body.\n\n### Child A\nChild A body.\n\n#### Grandchild A1\nGrandchild body.\n\n### Child B\nChild B body.\n\n## Next Root Section\nNext body.\n",
            encoding="utf-8"
        )

        child_c_text = "## Parent Section\nParent body.\n\n### Child C\nChild C body.\n"
        child_c_chunk = parse_markdown_chunks(child_c_text)[1]
        self.assertEqual(child_c_chunk.path, ("Parent Section", "Child C"))

        ok, msg = promote_chunk(child_c_chunk, target_rule_file="common.md", hub_dir=self.hub_dir, reproject=False)
        self.assertTrue(ok)

        content = common_md.read_text(encoding="utf-8")
        # Ensure Child C is placed after Child B, and before Next Root Section
        self.assertTrue(content.index("### Child C") > content.index("### Child B"))
        self.assertTrue(content.index("### Child C") < content.index("## Next Root Section"))

    def test_promote_to_subfolder(self):
        chunk = parse_markdown_chunks("## Custom Override\nOverride body.\n")[0]
        ok, msg = promote_chunk(chunk, target_rule_file="overrides/custom.md", hub_dir=self.hub_dir, reproject=False)
        self.assertTrue(ok)
        override_file = self.hub_dir / "rules" / "overrides" / "custom.md"
        self.assertTrue(override_file.is_file())
        self.assertIn("## Custom Override", override_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
