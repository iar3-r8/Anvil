"""Tests for anvilkit.render - generating the Zoo Code artifacts.

Written before the implementation (TDD step 5). This is the correctness gate:
the rendered output must match the golden fixtures captured from the bash
implementation in tests/fixtures/, so the rewrite is provably behaviour-preserving.

Comparisons are made on parsed dictionaries rather than raw text, because key
ordering and whitespace are not part of the contract - but validity is.

The decisive new property: values are injected by building a dict and calling
json.dumps, so a secret containing ``\\``, ``&`` or ``|`` can no longer corrupt
the output. That was the bug ``escape_sed_replacement()`` at ``anvil:95`` existed
to work around.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import render  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
TEMPLATES = REPO_ROOT / "templates"

# Must match tests/fixtures/README.md exactly, or the parity tests are meaningless.
GOLDEN_PORT = 8000
GOLDEN_CONTEXT_WINDOW = 262144
GOLDEN_LOCAL_PROFILE_ID = "4aj3zc43616"
GOLDEN_ANTHROPIC_PROFILE_ID = "anthropic_profile"
GOLDEN_ANTHROPIC_KEY = "sk-ant-golden-test-key"
GOLDEN_ANTHROPIC_MODEL = "claude-opus-5"
GOLDEN_CODER_MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"
GOLDEN_EMBEDDER_MODEL = "nomic-ai/nomic-embed-text-v1.5"
GOLDEN_WORKSPACE = "/golden/target/repo"
GOLDEN_GITHUB_TOKEN = "ghp_goldentesttoken"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def anthropic_settings(**overrides):
    """Settings for the accepted (frontier model) path."""
    params = dict(
        port=GOLDEN_PORT,
        context_window=GOLDEN_CONTEXT_WINDOW,
        coder_model_id=GOLDEN_CODER_MODEL,
        embedder_model_id=GOLDEN_EMBEDDER_MODEL,
        local_profile_id=GOLDEN_LOCAL_PROFILE_ID,
        anthropic_profile_id=GOLDEN_ANTHROPIC_PROFILE_ID,
        anthropic_api_key=GOLDEN_ANTHROPIC_KEY,
        anthropic_model_id=GOLDEN_ANTHROPIC_MODEL,
        use_anthropic_for_frontier_modes=True,
    )
    params.update(overrides)
    return params


def local_settings(**overrides):
    """Settings for the declined path: architect and orchestrator stay on the local gateway."""
    return anthropic_settings(
        anthropic_api_key="to set",
        use_anthropic_for_frontier_modes=False,
        **overrides
    )


class TestZooSettingsGoldenParity(unittest.TestCase):
    """The rendered settings must equal what bash produced."""

    def test_accepted_path_matches_golden_fixture(self):
        rendered = json.loads(render.zoo_code_settings(**anthropic_settings()))

        self.assertEqual(rendered, load_fixture("golden_zoo_settings_anthropic.json"))

    def test_declined_path_matches_golden_fixture(self):
        rendered = json.loads(render.zoo_code_settings(**local_settings()))

        self.assertEqual(rendered, load_fixture("golden_zoo_settings_local.json"))


class TestZooSettingsContent(unittest.TestCase):
    def setUp(self):
        self.accepted = json.loads(render.zoo_code_settings(**anthropic_settings()))
        self.declined = json.loads(render.zoo_code_settings(**local_settings()))

    def test_output_is_valid_json(self):
        # Valid by construction now, rather than by luck of escaping.
        self.assertIsInstance(self.accepted, dict)
        self.assertIsInstance(self.declined, dict)

    def test_no_unexpanded_placeholders_remain(self):
        for payload in (
            render.zoo_code_settings(**anthropic_settings()),
            render.zoo_code_settings(**local_settings()),
        ):
            self.assertNotIn("${", payload)

    def test_context_window_comes_from_config_yaml(self):
        info = self.accepted["providerProfiles"]["apiConfigs"]["llama_swap"][
            "openAiCustomModelInfo"
        ]

        self.assertEqual(info["contextWindow"], GOLDEN_CONTEXT_WINDOW)
        self.assertIsInstance(info["contextWindow"], int)

    def test_coder_model_id_comes_from_config_yaml(self):
        profile = self.accepted["providerProfiles"]["apiConfigs"]["llama_swap"]

        self.assertEqual(profile["openAiModelId"], GOLDEN_CODER_MODEL)

    def test_embedder_model_id_comes_from_config_yaml(self):
        index_config = self.accepted["globalSettings"]["codebaseIndexConfig"]

        self.assertEqual(
            index_config["codebaseIndexEmbedderModelId"], GOLDEN_EMBEDDER_MODEL
        )

    def test_gateway_port_is_applied_to_every_url(self):
        settings = json.loads(render.zoo_code_settings(**anthropic_settings(port=9999)))

        profile = settings["providerProfiles"]["apiConfigs"]["llama_swap"]
        index_config = settings["globalSettings"]["codebaseIndexConfig"]

        self.assertEqual(profile["openAiBaseUrl"], "http://localhost:9999/v1")
        self.assertEqual(
            index_config["codebaseIndexOpenAiCompatibleBaseUrl"],
            "http://localhost:9999/v1",
        )

    def test_qdrant_url_is_the_template_default(self):
        index_config = self.accepted["globalSettings"]["codebaseIndexConfig"]

        self.assertEqual(index_config["codebaseIndexQdrantUrl"], "http://localhost:6333")

    def test_accepted_path_binds_architect_to_anthropic_profile(self):
        modes = self.accepted["providerProfiles"]["modeApiConfigs"]

        self.assertEqual(modes["architect"], GOLDEN_ANTHROPIC_PROFILE_ID)

    def test_declined_path_binds_architect_to_local_profile(self):
        modes = self.declined["providerProfiles"]["modeApiConfigs"]

        self.assertEqual(modes["architect"], GOLDEN_LOCAL_PROFILE_ID)

    def test_accepted_path_binds_orchestrator_to_anthropic_profile(self):
        modes = self.accepted["providerProfiles"]["modeApiConfigs"]

        self.assertEqual(modes["orchestrator"], GOLDEN_ANTHROPIC_PROFILE_ID)

    def test_declined_path_binds_orchestrator_to_local_profile(self):
        modes = self.declined["providerProfiles"]["modeApiConfigs"]

        self.assertEqual(modes["orchestrator"], GOLDEN_LOCAL_PROFILE_ID)

    def test_other_modes_always_use_the_local_profile(self):
        for settings in (self.accepted, self.declined):
            modes = settings["providerProfiles"]["modeApiConfigs"]
            for mode in ("code", "ask", "debug"):
                self.assertEqual(modes[mode], GOLDEN_LOCAL_PROFILE_ID, mode)

    def test_anthropic_profile_carries_key_and_model(self):
        profile = self.accepted["providerProfiles"]["apiConfigs"]["anthropic"]

        self.assertEqual(profile["anthropicApiKey"], GOLDEN_ANTHROPIC_KEY)
        self.assertEqual(profile["apiModelId"], GOLDEN_ANTHROPIC_MODEL)
        self.assertEqual(profile["apiProvider"], "anthropic")

    def test_declined_path_keeps_anthropic_profile_dormant_but_valid(self):
        profile = self.declined["providerProfiles"]["apiConfigs"]["anthropic"]

        self.assertEqual(profile["anthropicApiKey"], "to set")
        self.assertEqual(profile["apiProvider"], "anthropic")

    def test_local_profile_id_is_applied(self):
        profile = self.accepted["providerProfiles"]["apiConfigs"]["llama_swap"]

        self.assertEqual(profile["id"], GOLDEN_LOCAL_PROFILE_ID)

    def test_always_allow_global_settings_are_true(self):
        """Verify every alwaysAllow* global setting is true in the rendered output."""
        always_allow_keys = (
            "alwaysAllowReadOnly",
            "alwaysAllowReadOnlyOutsideWorkspace",
            "alwaysAllowWrite",
            "alwaysAllowWriteOutsideWorkspace",
            "alwaysAllowWriteProtected",
            "alwaysAllowMcp",
            "alwaysAllowModeSwitch",
            "alwaysAllowSubtasks",
            "alwaysAllowExecute",
            "alwaysAllowFollowupQuestions",
        )

        for label, settings in (("accepted", self.accepted), ("declined", self.declined)):
            global_settings = settings["globalSettings"]
            for key in always_allow_keys:
                self.assertTrue(
                    global_settings.get(key, False),
                    f"{label}: globalSettings['{key}'] must be true, got {global_settings.get(key)!r}",
                )

    def test_followup_auto_approve_timeout(self):
        """Verify followupAutoApproveTimeoutMs is 20000 in both accepted and declined paths."""
        expected_timeout = 20000

        for label, settings in (("accepted", self.accepted), ("declined", self.declined)):
            global_settings = settings["globalSettings"]
            self.assertEqual(
                global_settings.get("followupAutoApproveTimeoutMs"),
                expected_timeout,
                f"{label}: globalSettings['followupAutoApproveTimeoutMs'] must be {expected_timeout}, "
                f"got {global_settings.get('followupAutoApproveTimeoutMs')!r}",
            )

    def test_deny_destructive_git_commands(self):
        """Verify deniedCommands includes destructive git commands.

        The template currently has deniedCommands as an empty array [], so this
        test fails until the renderer populates it with at least:
        - "git reset --hard"
        - "git push --force"
        """
        denied_accepted = self.accepted["globalSettings"]["deniedCommands"]
        denied_declined = self.declined["globalSettings"]["deniedCommands"]

        self.assertIn("git reset --hard", denied_accepted)
        self.assertIn("git push --force", denied_accepted)
        self.assertIn("git reset --hard", denied_declined)
        self.assertIn("git push --force", denied_declined)


class TestSecretsAreNotCorrupted(unittest.TestCase):
    """Regression tests for the escape_sed_replacement() class of bug."""

    def test_api_key_with_sed_metacharacters_survives_intact(self):
        nasty = r"sk-ant-a\b&c|d/e"

        settings = json.loads(
            render.zoo_code_settings(**anthropic_settings(anthropic_api_key=nasty))
        )

        profile = settings["providerProfiles"]["apiConfigs"]["anthropic"]
        self.assertEqual(profile["anthropicApiKey"], nasty)

    def test_api_key_with_quotes_and_newlines_produces_valid_json(self):
        nasty = 'key"with\\quotes\nand-newline'

        payload = render.zoo_code_settings(
            **anthropic_settings(anthropic_api_key=nasty)
        )

        # Must parse, and the value must be preserved exactly.
        settings = json.loads(payload)
        self.assertEqual(
            settings["providerProfiles"]["apiConfigs"]["anthropic"]["anthropicApiKey"],
            nasty,
        )

    def test_custom_model_id_with_metacharacters_survives(self):
        model_id = "claude-custom|v2&beta"

        settings = json.loads(
            render.zoo_code_settings(**anthropic_settings(anthropic_model_id=model_id))
        )

        self.assertEqual(
            settings["providerProfiles"]["apiConfigs"]["anthropic"]["apiModelId"],
            model_id,
        )


class TestMcpGoldenParity(unittest.TestCase):
    def test_matches_golden_fixture(self):
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder=GOLDEN_WORKSPACE,
                github_token=GOLDEN_GITHUB_TOKEN,
            )
        )

        self.assertEqual(rendered, load_fixture("golden_mcp.json"))

    def test_injects_workspace_folder(self):
        rendered = json.loads(
            render.mcp_settings(workspace_folder="/some/repo", github_token="")
        )

        self.assertIn("/some/repo", rendered["mcpServers"]["git"]["args"])

    def test_injects_github_token(self):
        rendered = json.loads(
            render.mcp_settings(workspace_folder="/some/repo", github_token="ghp_abc")
        )

        env = rendered["mcpServers"]["github"]["env"]
        self.assertEqual(env["GITHUB_PERSONAL_ACCESS_TOKEN"], "ghp_abc")

    def test_declined_github_leaves_token_empty_but_json_valid(self):
        rendered = json.loads(
            render.mcp_settings(workspace_folder="/some/repo", github_token="")
        )

        env = rendered["mcpServers"]["github"]["env"]
        self.assertEqual(env["GITHUB_PERSONAL_ACCESS_TOKEN"], "")

    def test_workspace_path_with_spaces_is_preserved(self):
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/home/user/My Repos/anvil", github_token=""
            )
        )

        self.assertIn("/home/user/My Repos/anvil", rendered["mcpServers"]["git"]["args"])

    def test_no_unexpanded_placeholders_remain(self):
        payload = render.mcp_settings(
            workspace_folder="/some/repo", github_token="ghp_abc"
        )

        self.assertNotIn("${", payload)

    def test_git_server_args_carry_no_sdk_pin(self):
        """Regression: the --with mcp<1.10 pin must be gone.

        Current mcp-server-git releases require mcp>=2.3,<3
        (https://pypi.org/project/mcp-server-git/), so the mcp<1.10 pin is
        unsatisfiable and uvx could never resolve it. The git entry must
        launch the package bare: uvx mcp-server-git --repository <workspace>.
        """
        entry = json.loads(
            render.mcp_settings(workspace_folder="/some/repo", github_token="")
        )["mcpServers"]["git"]

        self.assertEqual(entry["command"], "uvx")
        self.assertEqual(entry["args"], ["mcp-server-git", "--repository", "/some/repo"])
        self.assertNotIn("--with", entry["args"])
        self.assertFalse(
            any(arg.startswith("mcp<") for arg in entry["args"]),
            "no SDK pin of the form mcp<... may appear in the git args",
        )


class TestMcpOxylabs(unittest.TestCase):
    """Tests for plans/oxylabs-hosted-mcp.md behaviour 1 (render-oxylabs-hosted)
    and the stable half of behaviour 2: both-empty credentials render a
    disabled hosted entry with both header keys present as empty strings."""

    def test_oxylabs_hosted_shape_when_credentials_supplied(self):
        """Non-empty credentials produce the hosted streamable-HTTP entry.

        The entry must carry type "streamable-http", the hosted url, both
        headers set to the exact credential values, disabled false, and no
        command/args/env key.
        """
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/some/repo",
                github_token="ghp_test",
                oxylabs_username="test_user",
                oxylabs_password="test_pass",
            )
        )

        entry = rendered["mcpServers"].get("oxylabs")
        self.assertIsInstance(entry, dict, "oxylabs server entry is missing")
        self.assertEqual(
            entry.get("type"),
            "streamable-http",
            "oxylabs entry must be a streamable-http server",
        )
        self.assertEqual(
            entry.get("url"),
            "https://mcp.oxylabs.io/mcp",
            "oxylabs entry must point at the hosted endpoint",
        )
        headers = entry.get("headers")
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(headers.get("X-Oxylabs-Username"), "test_user")
        self.assertEqual(headers.get("X-Oxylabs-Password"), "test_pass")
        self.assertFalse(
            entry.get("disabled", False),
            "a complete credential pair must not disable the server",
        )
        for key in ("command", "args", "env"):
            self.assertNotIn(
                key,
                entry,
                "a hosted entry carries no '{}' key".format(key),
            )

    def test_oxylabs_header_credentials_with_quote_backslash_and_newline_stay_intact(self):
        """Error edge: a hostile credential survives json.dumps by construction.

        A quote, backslash and newline in a credential must parse back to the
        exact same value, which only holds if the output is built with
        json.dumps rather than string substitution.
        """
        nasty_password = 'pass"with\\backslash\nand-newline'

        payload = render.mcp_settings(
            workspace_folder="/some/repo",
            github_token="ghp_test",
            oxylabs_username="user",
            oxylabs_password=nasty_password,
        )

        entry = json.loads(payload)["mcpServers"].get("oxylabs")
        self.assertIsInstance(entry, dict, "oxylabs server entry is missing")
        headers = entry.get("headers")
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers.get("X-Oxylabs-Password"),
            nasty_password,
            "a credential with a quote, backslash and newline must parse back intact",
        )

    def test_oxylabs_disabled_when_credentials_empty(self):
        """Both-empty credentials yield disabled: true with both header keys
        present as empty strings, so no ${...} token survives into the output."""
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/some/repo",
                github_token="ghp_test",
                oxylabs_username="",
                oxylabs_password="",
            )
        )

        entry = rendered["mcpServers"].get("oxylabs")
        self.assertIsInstance(entry, dict, "oxylabs server entry is missing")
        self.assertTrue(entry.get("disabled", False))
        headers = entry.get("headers")
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers.get("X-Oxylabs-Username"),
            "",
            "both-empty credentials must leave the username header present but empty",
        )
        self.assertEqual(
            headers.get("X-Oxylabs-Password"),
            "",
            "both-empty credentials must leave the password header present but empty",
        )

    def test_oxylabs_disabled_when_username_empty_and_password_set(self):
        """Stricter rule (plans/oxylabs-hosted-mcp.md behaviour 2, Error clause):
        a partial pair can never authenticate, so an empty username with a set
        password must render disabled: true. The header values still substitute
        exactly; only disabled is the new assertion."""
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/some/repo",
                github_token="ghp_test",
                oxylabs_username="",
                oxylabs_password="test_pass",
            )
        )

        entry = rendered["mcpServers"].get("oxylabs")
        self.assertIsInstance(entry, dict, "oxylabs server entry is missing")
        self.assertTrue(
            entry.get("disabled", False),
            "an empty username with a set password is a partial pair and "
            "must render the server disabled",
        )
        headers = entry.get("headers")
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers.get("X-Oxylabs-Username"),
            "",
            "the empty username header must still substitute as an empty string",
        )
        self.assertEqual(
            headers.get("X-Oxylabs-Password"),
            "test_pass",
            "the set password header must substitute to its exact value",
        )

    def test_oxylabs_disabled_when_password_empty_and_username_set(self):
        """Stricter rule (plans/oxylabs-hosted-mcp.md behaviour 2, Error clause):
        the inverse partial pair — a set username with an empty password —
        must also render disabled: true, with both header values substituting
        exactly."""
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/some/repo",
                github_token="ghp_test",
                oxylabs_username="test_user",
                oxylabs_password="",
            )
        )

        entry = rendered["mcpServers"].get("oxylabs")
        self.assertIsInstance(entry, dict, "oxylabs server entry is missing")
        self.assertTrue(
            entry.get("disabled", False),
            "a set username with an empty password is a partial pair and "
            "must render the server disabled",
        )
        headers = entry.get("headers")
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers.get("X-Oxylabs-Username"),
            "test_user",
            "the set username header must substitute to its exact value",
        )
        self.assertEqual(
            headers.get("X-Oxylabs-Password"),
            "",
            "the empty password header must still substitute as an empty string",
        )

    def test_backward_compat_two_positional_args(self):
        """2. Calling mcp_settings with only workspace_folder and github_token (positional) still works.

        The function must accept two positional arguments with defaults for
        oxylabs_username and oxylabs_password, rendering an oxylabs server
        that is disabled by default.
        """
        rendered = json.loads(
            render.mcp_settings("/some/repo", "")
        )

        self.assertIn("mcpServers", rendered)
        self.assertIn("oxylabs", rendered["mcpServers"])
        self.assertTrue(rendered["mcpServers"]["oxylabs"].get("disabled", False))

    def test_oxylabs_appears_alongside_github_and_git(self):
        """4. The oxylabs server is added to the existing github and git servers, not replacing them.

        All three servers must coexist in the rendered JSON.
        """
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/some/repo",
                github_token="ghp_abc",
                oxylabs_username="user",
                oxylabs_password="pass",
            )
        )

        servers = rendered["mcpServers"]
        self.assertIn("github", servers)
        self.assertIn("git", servers)
        self.assertIn("oxylabs", servers)


class TestWriteToDisk(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.tmp_path = Path(tmp_dir.name)

    def test_write_json_creates_parent_directories(self):
        target = self.tmp_path / "nested" / "deeper" / "out.json"

        render.write_text(target, '{"a": 1}')

        self.assertTrue(target.is_file())

    def test_written_file_ends_with_newline(self):
        target = self.tmp_path / "out.json"

        render.write_text(target, '{"a": 1}')

        self.assertTrue(target.read_text(encoding="utf-8").endswith("\n"))

    def test_written_settings_parse_as_json(self):
        target = self.tmp_path / "zoo-code-settings.json"

        render.write_text(target, render.zoo_code_settings(**anthropic_settings()))

        self.assertIsInstance(
            json.loads(target.read_text(encoding="utf-8")), dict
        )


class TestTemplatesStayInSync(unittest.TestCase):
    """Guards against the template and renderer drifting apart."""

    def test_zoo_template_is_valid_json_once_placeholders_are_filled(self):
        # The template itself is not valid JSON (it holds a bare ${CONTEXT_WINDOW}),
        # so this asserts the renderer produces valid JSON from it.
        payload = render.zoo_code_settings(**anthropic_settings())

        self.assertIsInstance(json.loads(payload), dict)

    def test_extensions_template_is_copied_verbatim_and_is_valid_json(self):
        source = TEMPLATES / "extensions.json.template"

        self.assertIsInstance(
            json.loads(source.read_text(encoding="utf-8")), dict
        )


class TestZooSettingsContainerTarget(unittest.TestCase):
    """``container_target=True`` re-points the rendered URLs at
    ``host.docker.internal`` (reaching the host via the devcontainer's
    ``--add-host=host.docker.internal:host-gateway``) with the host-mapped
    LLM port, instead of ``localhost``.
    """

    def test_gateway_urls_use_host_docker_internal_and_the_host_port(self):
        settings = json.loads(
            render.zoo_code_settings(**anthropic_settings(container_target=True))
        )

        profile = settings["providerProfiles"]["apiConfigs"]["llama_swap"]
        index_config = settings["globalSettings"]["codebaseIndexConfig"]

        self.assertEqual(
            profile["openAiBaseUrl"],
            "http://host.docker.internal:{}/v1".format(GOLDEN_PORT),
        )
        self.assertEqual(
            index_config["codebaseIndexOpenAiCompatibleBaseUrl"],
            "http://host.docker.internal:{}/v1".format(GOLDEN_PORT),
        )

    def test_qdrant_url_uses_host_docker_internal(self):
        settings = json.loads(
            render.zoo_code_settings(**anthropic_settings(container_target=True))
        )

        index_config = settings["globalSettings"]["codebaseIndexConfig"]

        self.assertEqual(
            index_config["codebaseIndexQdrantUrl"], "http://host.docker.internal:6333"
        )

    def test_container_target_uses_the_host_llm_port(self):
        # The host-side LLM_PORT must reach the sandbox through the host
        # mapping, so the container-target URL uses exactly the passed port.
        settings = json.loads(
            render.zoo_code_settings(**anthropic_settings(container_target=True, port=9999))
        )

        profile = settings["providerProfiles"]["apiConfigs"]["llama_swap"]

        self.assertEqual(profile["openAiBaseUrl"], "http://host.docker.internal:9999/v1")

    def test_default_target_stays_on_localhost(self):
        settings = json.loads(render.zoo_code_settings(**anthropic_settings()))

        profile = settings["providerProfiles"]["apiConfigs"]["llama_swap"]

        self.assertEqual(profile["openAiBaseUrl"], "http://localhost:8000/v1")


class TestMcpSettingsContainerTarget(unittest.TestCase):
    """``container_target=True`` re-points the git ``--repository`` at the
    devcontainer mount ``/workspaces/<basename>`` (the target of
    ``workspaceMount`` in ``templates/devcontainer/devcontainer.json``),
    instead of the host ``workspace_folder``.
    """

    def test_git_repository_maps_to_the_devcontainer_mount(self):
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/home/me/Repositories/anvil",
                github_token="",
                container_target=True,
            )
        )

        self.assertEqual(
            rendered["mcpServers"]["git"]["args"],
            ["mcp-server-git", "--repository", "/workspaces/anvil"],
        )

    def test_trailing_slash_yields_the_same_mount_path(self):
        rendered = json.loads(
            render.mcp_settings(
                workspace_folder="/home/me/anvil/",
                github_token="",
                container_target=True,
            )
        )

        self.assertEqual(
            rendered["mcpServers"]["git"]["args"],
            ["mcp-server-git", "--repository", "/workspaces/anvil"],
        )

    def test_root_workspace_folder_raises_render_error_naming_the_value(self):
        # "/" has no basename, so "/workspaces/" + name would be a dangling
        # repository path that fails at MCP launch with a far less obvious
        # error; refuse it up front, naming the offending value.
        with self.assertRaises(render.RenderError) as ctx:
            render.mcp_settings(
                workspace_folder="/",
                github_token="",
                container_target=True,
            )

        self.assertIn("/", str(ctx.exception))

    def test_empty_workspace_folder_raises_render_error_naming_the_value(self):
        # The empty string has no basename either; the message must say which
        # argument was unusable, since the value itself has nothing to quote.
        with self.assertRaises(render.RenderError) as ctx:
            render.mcp_settings(
                workspace_folder="",
                github_token="",
                container_target=True,
            )

        self.assertIn("workspace_folder", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
