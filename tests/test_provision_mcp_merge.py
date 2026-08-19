"""RED tests for the ``_merge_mcp_servers()`` pure helper in ``anvilkit/provision.py``.

Written before the implementation (TDD) for behaviours 3, 4, 5 and 8 of
``plans/package-registry-context.md`` (section 3, Group B).

The helper does not exist yet. The module imports it once at top level
inside a guarded ``try/except ImportError`` and binds ``None`` in the red
state; the shared ``_merge()`` wrapper then asserts the binding is not
``None`` before calling. While the helper is missing, every test that
exercises it therefore FAILs on that assertion — "the helper does not
exist yet", asserted — rather than an ``ImportError`` crash. The moment
the helper lands, every test proceeds to its real assertions unchanged.

The rendered text for every fixture is produced by
``render.mcp_settings()`` (reading the real ``templates/mcp.json.template``);
no rendered JSON is hand-written. Per plan section 2.2, "preserved" means
value-preserved, not byte-preserved: assertions are on parsed structures
and on key order, never on raw bytes.

Return convention (deliberately different from ``_merge_gitignore``): the
helper always returns the merged text. Detecting "unchanged" belongs to the
provisioning step, which compares before writing.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import provision, render  # noqa: E402

try:
    from anvilkit.provision import _merge_mcp_servers  # noqa: E402
except ImportError:  # red state: helper not implemented yet
    _merge_mcp_servers = None

# The source argument used in error-message assertions, so a test proves the
# helper names the offending file without ever touching a real path.
SOURCE = "repo/.roo/mcp.json"


def _rendered(**overrides) -> str:
    """Render ``.roo/mcp.json`` via the real renderer.

    Defaults give every server non-empty credentials; callers override to
    produce the specific incoming values each behaviour needs.
    """
    kwargs = {
        "workspace_folder": "/tmp/example-workspace",
        "github_token": "ghp_rendered_token",
        "oxylabs_username": "render_user",
        "oxylabs_password": "render_pass",
    }
    kwargs.update(overrides)
    return render.mcp_settings(**kwargs)


def _existing(servers, extra_top_level=None) -> str:
    """Build an existing-file fixture as a JSON string."""
    data = {}
    if extra_top_level:
        for key, value in extra_top_level.items():
            data[key] = value
    data["mcpServers"] = servers
    return json.dumps(data, indent=4)


def _github_entry(token) -> dict:
    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "disabled": False,
        "alwaysAllow": [],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": token},
    }


def _oxylabs_entry(username, password, disabled=False) -> dict:
    return {
        "command": "uvx",
        "args": ["oxylabs-mcp"],
        "disabled": disabled,
        "env": {
            "OXYLABS_USERNAME": username,
            "OXYLABS_PASSWORD": password,
        },
    }


def _merge(existing_text, rendered_text, source=SOURCE):
    """Invoke ``_merge_mcp_servers``, asserting the red state first.

    While the helper is missing the module-level guard bound ``None`` and
    this assertion makes the test FAIL — for the expected reason — instead
    of crashing with an ``ImportError`` or a ``TypeError`` from calling
    ``None``. Once the helper exists the guard is a no-op and the call is
    unchanged.
    """
    assert (
        _merge_mcp_servers is not None
    ), "_merge_mcp_servers is not implemented in anvilkit.provision (red state)"

    return _merge_mcp_servers(existing_text, rendered_text, source)


# ---------------------------------------------------------------------------
# Behaviour 3 — no-op on a first run
# ---------------------------------------------------------------------------


class Behaviour3NoOpOnFirstRunTests(unittest.TestCase):
    """Behaviour 3: empty existing text → the rendered text, verbatim.

    First-run semantics: the provisioning step writes wholesale, so the
    helper returns the rendered text unchanged.
    """

    def test_empty_existing_returns_rendered_verbatim(self):
        rendered_text = _rendered()
        result = _merge("", rendered_text)
        self.assertEqual(
            result,
            rendered_text,
            "Empty existing text must yield the rendered text verbatim",
        )

    def test_empty_existing_result_parses_to_rendered_structure(self):
        rendered_text = _rendered()
        result = _merge("", rendered_text)
        self.assertEqual(
            json.loads(result),
            json.loads(rendered_text),
            "Parsed structure of first-run output must equal the rendered structure",
        )

    def test_whitespace_only_existing_treated_as_empty(self):
        rendered_text = _rendered()
        result = _merge("   \n\t  \n", rendered_text)
        self.assertEqual(
            result,
            rendered_text,
            "Whitespace-only existing text must be treated as empty (verbatim path)",
        )


# ---------------------------------------------------------------------------
# Behaviour 4 — user-added server preserved, position kept
# ---------------------------------------------------------------------------


class Behaviour4UserServerPreservedTests(unittest.TestCase):
    """Behaviour 4: a server absent from the rendered text is preserved untouched.

    User-owned servers keep their parsed value and their position; Anvil
    servers missing from the existing file are appended after all existing
    entries; nothing is ever removed.
    """

    USER_SERVER = {
        "command": "node",
        "args": ["/home/user/scripts/my-server.js"],
        "disabled": False,
        "env": {"MY_SERVER_KEY": "my-secret"},
    }

    def setUp(self):
        # Existing file: user server first, then two Anvil servers, in an
        # order that is NOT the rendered order (oxylabs before github).
        self.existing_servers = {
            "my-server": self.USER_SERVER,
            "oxylabs": _oxylabs_entry("stored_user", "stored_pass"),
            "github": _github_entry("ghp_old"),
        }
        self.existing_text = _existing(self.existing_servers)
        self.rendered_text = _rendered()
        self.rendered_servers = json.loads(self.rendered_text)["mcpServers"]

    def test_user_server_present_with_parsed_value_equal(self):
        result = json.loads(_merge(self.existing_text, self.rendered_text))
        self.assertIn("my-server", result["mcpServers"])
        self.assertEqual(
            result["mcpServers"]["my-server"],
            self.USER_SERVER,
            "User-owned server entry must survive with its parsed value intact",
        )

    def test_user_server_position_before_any_appended_anvil_server(self):
        result = json.loads(_merge(self.existing_text, self.rendered_text))
        keys = list(result["mcpServers"].keys())
        user_idx = keys.index("my-server")
        appended = [name for name in keys if name not in self.existing_servers]
        self.assertTrue(appended, "Expected at least one appended Anvil server")
        for name in appended:
            self.assertLess(
                user_idx,
                keys.index(name),
                "User server '{}' must appear before appended Anvil server "
                "'{}' (order: {})".format("my-server", name, keys),
            )

    def test_existing_anvil_servers_keep_their_existing_positions(self):
        # Full expected order: existing keys in their existing order, then
        # the rendered servers not already present, in rendered order.
        expected_keys = list(self.existing_servers.keys())
        for name in self.rendered_servers:
            if name not in expected_keys:
                expected_keys.append(name)
        result = json.loads(_merge(self.existing_text, self.rendered_text))
        self.assertEqual(
            list(result["mcpServers"].keys()),
            expected_keys,
            "Existing servers must keep their positions; missing Anvil "
            "servers must be appended after all existing entries",
        )

    def test_top_level_keys_other_than_mcpservers_preserved(self):
        existing_text = _existing(
            self.existing_servers,
            extra_top_level={"schemaVersion": 2, "notes": "hand-tuned"},
        )
        result = json.loads(_merge(existing_text, self.rendered_text))
        self.assertEqual(result.get("schemaVersion"), 2, "Top-level key lost")
        self.assertEqual(result.get("notes"), "hand-tuned", "Top-level key lost")
        self.assertIn("mcpServers", result)

    def test_missing_mcpservers_key_is_created_and_other_keys_survive(self):
        existing_text = json.dumps({"custom": 1}, indent=4)
        result = json.loads(_merge(existing_text, self.rendered_text))
        self.assertEqual(
            result["mcpServers"],
            self.rendered_servers,
            "A missing mcpServers key must be created with the rendered servers",
        )
        self.assertEqual(result.get("custom"), 1, "Other top-level keys must survive")

    def test_existing_mcpservers_is_a_list_raises(self):
        existing_text = _existing(["github"])
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_existing_mcpservers_is_a_string_raises(self):
        existing_text = _existing("github")
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_existing_top_level_not_a_mapping_raises(self):
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge("[1, 2, 3]", self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )

    def test_invalid_existing_json_raises(self):
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge("not json at all", self.rendered_text)
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )


# ---------------------------------------------------------------------------
# Behaviour 5 — Anvil-owned server refreshed; missing Anvil server appended
# ---------------------------------------------------------------------------


class Behaviour5AnvilServerRefreshedTests(unittest.TestCase):
    """Behaviour 5: a server named in the rendered text is Anvil-owned.

    A1 option 1: the whole existing entry is replaced by the rendered entry.
    An Anvil server absent from the existing file is appended, equal to the
    rendered entry.
    """

    def setUp(self):
        self.existing_servers = {
            "github": _github_entry("ghp_old"),
            "git": {
                "command": "uvx",
                "args": [
                    "--with",
                    "mcp<1.10",
                    "mcp-server-git",
                    "--repository",
                    "/old/workspace",
                ],
                "disabled": False,
                "alwaysAllow": [],
            },
            "oxylabs": _oxylabs_entry("stored_user", "stored_pass"),
        }
        self.existing_text = _existing(self.existing_servers)
        self.rendered_text = _rendered(github_token="ghp_new")
        self.rendered_servers = json.loads(self.rendered_text)["mcpServers"]

    def test_github_token_is_refreshed(self):
        result = json.loads(_merge(self.existing_text, self.rendered_text))
        self.assertEqual(
            result["mcpServers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"],
            "ghp_new",
            "The rendered (incoming) credential must win on refresh",
        )

    def test_refreshed_entry_equals_rendered_entry_whole(self):
        result = json.loads(_merge(self.existing_text, self.rendered_text))
        self.assertEqual(
            result["mcpServers"]["github"],
            self.rendered_servers["github"],
            "A refreshed Anvil-owned server must equal the rendered entry "
            "wholesale (A1 option 1)",
        )

    def test_missing_anvil_server_appended_equal_to_rendered(self):
        # A repo provisioned before package-registry existed: it is absent
        # from the existing file and must be appended.
        self.assertNotIn("package-registry", self.existing_servers)
        result = json.loads(_merge(self.existing_text, self.rendered_text))
        keys = list(result["mcpServers"].keys())
        self.assertIn("package-registry", keys)
        self.assertEqual(
            result["mcpServers"]["package-registry"],
            self.rendered_servers["package-registry"],
            "An appended Anvil server must equal its rendered entry",
        )
        self.assertEqual(
            keys.index("package-registry"),
            len(self.existing_servers),
            "Appended servers must come after all existing entries",
        )


# ---------------------------------------------------------------------------
# Behaviour 8 — empty incoming credential does not blank a stored one
# ---------------------------------------------------------------------------


class Behaviour8EmptyCredentialNotBlankedTests(unittest.TestCase):
    """Behaviour 8: A2 — per env key, an empty incoming value must not blank
    a non-empty stored one; a non-empty incoming value always wins.

    Applies to ``env`` values only. The ``disabled`` flag is NOT an env value:
    per A1 option 1 it is refreshed wholesale with the Anvil server, so no
    test here asserts on ``disabled`` surviving.
    """

    def setUp(self):
        self.existing_text = _existing(
            {"oxylabs": _oxylabs_entry("stored_user", "stored_pass")}
        )

    def test_empty_incoming_username_keeps_stored_value(self):
        # Both credentials empty → the renderer flips disabled=True; the
        # refresh must still keep the stored username.
        rendered_text = _rendered(oxylabs_username="", oxylabs_password="")
        result = json.loads(_merge(self.existing_text, rendered_text))
        env = result["mcpServers"]["oxylabs"]["env"]
        self.assertEqual(
            env["OXYLABS_USERNAME"],
            "stored_user",
            "An empty incoming credential must not blank a stored one",
        )

    def test_empty_incoming_password_keeps_stored_value(self):
        rendered_text = _rendered(oxylabs_username="new_user", oxylabs_password="")
        result = json.loads(_merge(self.existing_text, rendered_text))
        env = result["mcpServers"]["oxylabs"]["env"]
        self.assertEqual(
            env["OXYLABS_PASSWORD"],
            "stored_pass",
            "An empty incoming password must not blank the stored one",
        )

    def test_non_empty_incoming_username_wins(self):
        rendered_text = _rendered(oxylabs_username="new_user", oxylabs_password="x")
        result = json.loads(_merge(self.existing_text, rendered_text))
        env = result["mcpServers"]["oxylabs"]["env"]
        self.assertEqual(
            env["OXYLABS_USERNAME"],
            "new_user",
            "A non-empty incoming value always wins, including a deliberate change",
        )

    def test_per_value_independence(self):
        # One key comes in empty, the other non-empty: each is handled
        # independently.
        rendered_text = _rendered(oxylabs_username="", oxylabs_password="new_pass")
        result = json.loads(_merge(self.existing_text, rendered_text))
        env = result["mcpServers"]["oxylabs"]["env"]
        self.assertEqual(
            env["OXYLABS_USERNAME"],
            "stored_user",
            "Empty incoming username must keep the stored value",
        )
        self.assertEqual(
            env["OXYLABS_PASSWORD"],
            "new_pass",
            "Non-empty incoming password must win",
        )

    def test_empty_incoming_with_empty_stored_stays_empty(self):
        # Nothing stored, nothing incoming: the value stays empty.
        existing_text = _existing({"oxylabs": _oxylabs_entry("", "")})
        rendered_text = _rendered(oxylabs_username="", oxylabs_password="")
        result = json.loads(_merge(existing_text, rendered_text))
        env = result["mcpServers"]["oxylabs"]["env"]
        self.assertEqual(env["OXYLABS_USERNAME"], "")
        self.assertEqual(env["OXYLABS_PASSWORD"], "")


# ---------------------------------------------------------------------------
# Rendered-text error semantics (design note from the task)
# ---------------------------------------------------------------------------


class RenderedTextErrorSemanticsTests(unittest.TestCase):
    """Invalid rendered JSON is a pipeline bug, not user fault.

    Choice stated per the task: the helper raises ``ProvisionError`` (never a
    bare ``json.JSONDecodeError``), keeping one exception type per module so
    the provisioning step's single ``except`` still holds.
    """

    def test_invalid_rendered_json_raises_provision_error_naming_source(self):
        existing_text = _existing({"oxylabs": _oxylabs_entry("u", "p")})
        with self.assertRaises(provision.ProvisionError) as ctx:
            _merge(existing_text, "definitely not json")
        self.assertIn(
            SOURCE,
            str(ctx.exception),
            "ProvisionError must name the source: {}".format(ctx.exception),
        )


if __name__ == "__main__":
    unittest.main()
