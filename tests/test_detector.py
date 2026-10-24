import unittest
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import detect_platforms, get_home_dir, get_hub_dir


class TestDetector(unittest.TestCase):
    def test_paths(self):
        home = get_home_dir()
        hub = get_hub_dir()
        self.assertTrue(home.is_dir())
        self.assertEqual(hub, home / ".agentrc")

    def test_detection_structure(self):
        res = detect_platforms()
        self.assertIn("hub", res)
        self.assertIn("platforms", res)
        self.assertIn("antigravity", res["platforms"])
        self.assertIn("claude", res["platforms"])


if __name__ == "__main__":
    unittest.main()
