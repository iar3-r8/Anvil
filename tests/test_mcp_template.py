"""Tests for templates/mcp.json.template as a data file.

RED step for plans/package-registry-context.md, section 3 Group A item 1:
the template must declare the ``package-registry`` server. The template is
read as data and every assertion is on the parsed structure, never on raw
bytes, so indentation or key-order changes in the file are not part of the
contract.

Expected to fail now with an assertion error (the key ``package-registry``
is absent); the template itself is untouched in this step.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEMPLATE_PATH = REPO_ROOT / "templates" / "mcp.json.template"

# The exact launch config required by the plan. No "env" key: the server
# needs no credentials, so nothing may be substituted into it.
EXPECTED_PACKAGE_REGISTRY = {
    "command": "npx",
    "args": ["package-registry-mcp"],
    "disabled": False,
    "alwaysAllow": [],
}

# The current values of the pre-existing servers, as of this red step.
# "Unchanged" means byte-for-byte equal to these once parsed, including the
# raw ${...} placeholders that render.mcp_settings substitutes later.
EXPECTED_GITHUB = {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "disabled": False,
    "alwaysAllow": [],
    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
    "disabledTools": [
        "create_or_update_file",
        "push_files",
        "fork_repository",
        "search_code",
    ],
}

EXPECTED_GIT = {
    "command": "uvx",
    "args": ["--with", "mcp<1.10", "mcp-server-git", "--repository", "${workspaceFolder}"],
    "disabled": False,
    "alwaysAllow": [],
}

EXPECTED_OXYLABS = {
    "command": "uvx",
    "args": ["oxylabs-mcp"],
    "disabled": False,
    "env": {
        "OXYLABS_USERNAME": "${OXYLABS_USERNAME}",
        "OXYLABS_PASSWORD": "${OXYLABS_PASSWORD}",
    },
}


class TestMcpTemplatePackageRegistry(unittest.TestCase):
    """templates/mcp.json.template declares the package-registry server."""

    def setUp(self):
        # Arrange: read the template as data. If it were not valid JSON,
        # json.loads would raise here and the module would error rather
        # than pass silently.
        self.data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        self.servers = self.data["mcpServers"]

    def test_package_registry_key_present(self):
        # Act + Assert: the server is declared.
        self.assertIn("package-registry", self.servers)

    def test_package_registry_entry_matches_launch_config(self):
        # The whole entry must equal the launch config, which also fixes
        # the exact set of keys the entry carries.
        self.assertIn("package-registry", self.servers)

        self.assertEqual(self.servers["package-registry"], EXPECTED_PACKAGE_REGISTRY)

    def test_package_registry_entry_has_no_env_key(self):
        # Edge: no credentials needed, so nothing may be substituted in.
        self.assertIn("package-registry", self.servers)

        self.assertNotIn("env", self.servers["package-registry"])

    def test_existing_servers_still_present_and_unchanged(self):
        # Edge: adding the new server must not disturb the old ones.
        self.assertEqual(self.servers.get("github"), EXPECTED_GITHUB)
        self.assertEqual(self.servers.get("git"), EXPECTED_GIT)
        self.assertEqual(self.servers.get("oxylabs"), EXPECTED_OXYLABS)

    def test_template_is_valid_json_object_with_single_top_level_key(self):
        # The template remains a well-formed document whose only
        # top-level concern is the server table.
        self.assertIsInstance(self.data, dict)
        self.assertEqual(set(self.data), {"mcpServers"})
        self.assertIsInstance(self.servers, dict)
