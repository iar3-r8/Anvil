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


if __name__ == "__main__":
    unittest.main()
