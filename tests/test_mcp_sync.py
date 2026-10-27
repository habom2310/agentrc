import unittest
import tempfile
import json
from pathlib import Path
import sys

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from agentrc.detector import set_custom_home
from agentrc.mcp_sync import get_mcp_status, sync_mcp_servers, _read_json_safely


class TestMcpSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home_dir = Path(self.temp_dir.name) / "home"
        self.hub_dir = self.home_dir / ".agentrc"

        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.hub_dir.mkdir(parents=True, exist_ok=True)
        (self.hub_dir / "mcp").mkdir(parents=True, exist_ok=True)

        set_custom_home(self.home_dir, self.hub_dir)

    def tearDown(self):
        set_custom_home(None, None)
        self.temp_dir.cleanup()

    def test_bidirectional_mcp_sync_and_preservation(self):
        # 1. Setup initial hub with codegraph server
        hub_mcp_file = self.hub_dir / "mcp" / "servers.json"
        hub_mcp_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {
                    "command": "codegraph",
                    "args": ["serve", "--mcp"]
                }
            }
        }), encoding="utf-8")

        # 2. Setup Claude Code with openchatcut HTTP server and custom non-mcp keys
        claude_file = self.home_dir / ".claude.json"
        claude_file.write_text(json.dumps({
            "oauthAccount": "user@example.com",
            "machineID": "abc-123",
            "mcpServers": {
                "openchatcut": {
                    "type": "http",
                    "url": "http://127.0.0.1:5199/api/external-mcp/mcp",
                    "headers": {"Authorization": "Bearer secret"}
                }
            }
        }), encoding="utf-8")

        # 3. Setup Gemini directory with custom settings keys
        gemini_dir = self.home_dir / ".gemini"
        (gemini_dir / "config").mkdir(parents=True, exist_ok=True)
        gemini_settings_file = gemini_dir / "settings.json"
        gemini_settings_file.write_text(json.dumps({
            "customGeminiKey": "active",
            "mcpServers": {}
        }), encoding="utf-8")

        # 4. Check initial status
        st_before = get_mcp_status(self.home_dir, self.hub_dir)
        self.assertFalse(st_before["in_sync"])
        self.assertIn("openchatcut", st_before["untracked_in_claude"])
        self.assertIn("codegraph", st_before["missing_in_claude"])
        self.assertIn("codegraph", st_before["missing_in_gemini"])

        # 5. Perform sync
        ok, actions = sync_mcp_servers(self.home_dir, self.hub_dir)
        self.assertTrue(ok)
        self.assertTrue(any("openchatcut" in a for a in actions))

        # 6. Verify Hub received openchatcut
        hub_updated = json.loads(hub_mcp_file.read_text(encoding="utf-8"))
        self.assertIn("codegraph", hub_updated["mcpServers"])
        self.assertIn("openchatcut", hub_updated["mcpServers"])
        self.assertEqual(hub_updated["mcpServers"]["openchatcut"]["url"], "http://127.0.0.1:5199/api/external-mcp/mcp")

        # 7. Verify Claude received codegraph while preserving oauthAccount and openchatcut
        claude_updated = json.loads(claude_file.read_text(encoding="utf-8"))
        self.assertEqual(claude_updated["oauthAccount"], "user@example.com")
        self.assertEqual(claude_updated["machineID"], "abc-123")
        self.assertIn("codegraph", claude_updated["mcpServers"])
        self.assertEqual(claude_updated["mcpServers"]["codegraph"]["type"], "stdio")
        self.assertIn("openchatcut", claude_updated["mcpServers"])

        # 8. Verify Gemini received both codegraph and openchatcut while preserving customGeminiKey
        gemini_updated = json.loads(gemini_settings_file.read_text(encoding="utf-8"))
        self.assertEqual(gemini_updated["customGeminiKey"], "active")
        self.assertIn("codegraph", gemini_updated["mcpServers"])
        self.assertIn("openchatcut", gemini_updated["mcpServers"])

        gemini_mcp_config = json.loads((gemini_dir / "config" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertIn("codegraph", gemini_mcp_config["mcpServers"])
        self.assertIn("openchatcut", gemini_mcp_config["mcpServers"])

        # 9. Verify status is now IN SYNC
        st_after = get_mcp_status(self.home_dir, self.hub_dir)
        self.assertTrue(st_after["in_sync"])

        # 10. Verify idempotence
        ok2, actions2 = sync_mcp_servers(self.home_dir, self.hub_dir)
        self.assertTrue(ok2)
        self.assertEqual(actions2, ["All MCP configurations are already synchronized."])

    def test_corrupt_json_safety_guard(self):
        # Corrupt claude.json with invalid JSON
        claude_file = self.home_dir / ".claude.json"
        corrupt_content = '{"oauthAccount": "user", "invalid_json_trailing_comma": ,'
        claude_file.write_text(corrupt_content, encoding="utf-8")

        # Sync should execute without crashing and refuse to overwrite corrupt claude.json
        ok, actions = sync_mcp_servers(self.home_dir, self.hub_dir)
        self.assertTrue(ok)
        self.assertTrue(any("[SKIP]" in a and ".claude.json" in a for a in actions))

        # Verify content was NOT wiped or replaced
        self.assertEqual(claude_file.read_text(encoding="utf-8"), corrupt_content)

    def test_drift_detection_for_existing_server(self):
        hub_mcp_file = self.hub_dir / "mcp" / "servers.json"
        hub_mcp_file.write_text(json.dumps({
            "mcpServers": {
                "server1": {"command": "s1", "args": ["--port", "8000"]}
            }
        }), encoding="utf-8")

        claude_file = self.home_dir / ".claude.json"
        claude_file.write_text(json.dumps({
            "mcpServers": {
                # Server exists but with drifted arguments
                "server1": {"type": "stdio", "command": "s1", "args": ["--port", "9999"]}
            }
        }), encoding="utf-8")

        st = get_mcp_status(self.home_dir, self.hub_dir)
        self.assertFalse(st["in_sync"])
        self.assertIn("server1", st["drifted_in_claude"])

    def test_uninstalled_platforms_not_marked_missing(self):
        hub_mcp_file = self.hub_dir / "mcp" / "servers.json"
        hub_mcp_file.write_text(json.dumps({
            "mcpServers": {
                "server1": {"command": "s1"}
            }
        }), encoding="utf-8")

        # Empty home directory with no .claude or .gemini
        empty_home = Path(self.temp_dir.name) / "empty_home"
        empty_home.mkdir(parents=True, exist_ok=True)
        st = get_mcp_status(home_dir=empty_home, hub_dir=self.hub_dir)
        self.assertEqual(st["missing_in_claude"], [])
        self.assertEqual(st["missing_in_gemini"], [])

    def test_always_load_preserved_on_claude_mirror(self):
        hub_mcp_file = self.hub_dir / "mcp" / "servers.json"
        hub_mcp_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {"command": "codegraph", "args": ["serve", "--mcp"]}
            }
        }), encoding="utf-8")

        claude_file = self.home_dir / ".claude.json"
        claude_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {
                    "type": "stdio",
                    "command": "codegraph",
                    "args": ["serve", "--mcp"],
                    "alwaysLoad": True,
                }
            }
        }), encoding="utf-8")

        ok, _ = sync_mcp_servers(self.home_dir, self.hub_dir)
        self.assertTrue(ok)

        claude_updated = json.loads(claude_file.read_text(encoding="utf-8"))
        self.assertIs(claude_updated["mcpServers"]["codegraph"]["alwaysLoad"], True)

        hub_updated = json.loads(hub_mcp_file.read_text(encoding="utf-8"))
        self.assertNotIn("alwaysLoad", hub_updated["mcpServers"]["codegraph"])

    def test_always_load_not_reported_as_drift(self):
        hub_mcp_file = self.hub_dir / "mcp" / "servers.json"
        hub_mcp_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {"command": "codegraph", "args": ["serve", "--mcp"]}
            }
        }), encoding="utf-8")

        claude_file = self.home_dir / ".claude.json"
        claude_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {
                    "type": "stdio",
                    "command": "codegraph",
                    "args": ["serve", "--mcp"],
                    "alwaysLoad": True,
                }
            }
        }), encoding="utf-8")

        ok, _ = sync_mcp_servers(self.home_dir, self.hub_dir)
        self.assertTrue(ok)

        status = get_mcp_status(self.home_dir, self.hub_dir)
        self.assertTrue(status["in_sync"])
        self.assertEqual(status["drifted_in_claude"], [])

    def test_always_load_preserved_when_hub_args_change(self):
        hub_mcp_file = self.hub_dir / "mcp" / "servers.json"
        hub_mcp_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {"command": "codegraph", "args": ["serve", "--mcp", "--new"]}
            }
        }), encoding="utf-8")

        claude_file = self.home_dir / ".claude.json"
        claude_file.write_text(json.dumps({
            "mcpServers": {
                "codegraph": {
                    "type": "stdio",
                    "command": "codegraph",
                    "args": ["serve", "--mcp"],
                    "alwaysLoad": True,
                }
            }
        }), encoding="utf-8")

        ok, _ = sync_mcp_servers(self.home_dir, self.hub_dir)
        self.assertTrue(ok)

        claude_entry = json.loads(claude_file.read_text(encoding="utf-8"))["mcpServers"]["codegraph"]
        self.assertEqual(claude_entry["args"], ["serve", "--mcp", "--new"])
        self.assertIs(claude_entry["alwaysLoad"], True)

        hub_entry = json.loads(hub_mcp_file.read_text(encoding="utf-8"))["mcpServers"]["codegraph"]
        self.assertNotIn("alwaysLoad", hub_entry)

    def test_non_dict_json_safety(self):
        array_file = self.home_dir / "array.json"
        array_file.write_text("[1, 2, 3]", encoding="utf-8")
        data, ok = _read_json_safely(array_file)
        self.assertFalse(ok)
        self.assertEqual(data, {})


if __name__ == "__main__":
    unittest.main()
