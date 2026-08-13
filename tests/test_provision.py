"""Tests for anvilkit.provision - the setup-repo orchestration.

Written before the implementation (TDD step 8).

Replaces ``anvil:274-421``. Everything happens inside
``tempfile.TemporaryDirectory``: no test touches ``$HOME``, the real repo, or the
network.

What is asserted:

* the validation errors of ``anvil:284-318``, each preserved and each distinct;
* the created tree - ``.roo/{commands,skills,rules}``, ``.vscode/``,
  ``roo_template/``;
* the generated artifacts parse as JSON and carry the resolved values;
* the "IMPORTANT NEXT STEP" guidance of ``anvil:417`` survives;
* ``dry_run`` writes absolutely nothing.

Never asserted: the source text of the module under test.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import provision  # noqa: E402

CODER_MODEL = "Qwen/Qwen3.6-35B-A3B-FP8"
EMBEDDER_MODEL = "nomic-ai/nomic-embed-text-v1.5"
LOCAL_PROFILE_ID = "4aj3zc43616"
ANTHROPIC_PROFILE_ID = "anthropic_profile"


def plan(**overrides):
    """A fully-resolved provisioning request, as the CLI would assemble it."""
    params = dict(
        port=8000,
        context_window=262144,
        coder_model_id=CODER_MODEL,
        embedder_model_id=EMBEDDER_MODEL,
        local_profile_id=LOCAL_PROFILE_ID,
        anthropic_profile_id=ANTHROPIC_PROFILE_ID,
        anthropic_api_key="to set",
        anthropic_model_id="claude-opus-5",
        use_anthropic_for_frontier_modes=False,
        github_token="",
    )
    params.update(overrides)
    return provision.RepoPlan(**params)


class ProvisionCase(unittest.TestCase):
    """Base class giving every test its own throwaway target repository."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.messages = []

    def tearDown(self):
        self._tmp.cleanup()

    def provision(self, **kwargs):
        params = dict(target=self.target, repo_plan=plan(), echo=self.messages.append)
        params.update(kwargs)
        return provision.setup_repo(**params)

    def read_json(self, relative):
        return json.loads((self.target / relative).read_text(encoding="utf-8"))

    @property
    def output(self):
        return "\n".join(self.messages)


class ValidationTests(ProvisionCase):
    """The safeguards at anvil:284-318, each preserved and distinguishable."""

    def test_missing_target_path_is_rejected(self):
        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(target=None)

        self.assertIn("target repository", str(ctx.exception).lower())

    def test_empty_target_path_is_rejected(self):
        with self.assertRaises(provision.ProvisionError):
            self.provision(target="")

    def test_nonexistent_target_is_rejected(self):
        missing = self.target / "does" / "not" / "exist"

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(target=missing)

        self.assertIn("does not exist", str(ctx.exception))

    def test_error_message_names_the_offending_directory(self):
        missing = self.target / "nope"

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(target=missing)

        self.assertIn("nope", str(ctx.exception))

    def test_target_that_is_a_file_is_rejected(self):
        a_file = self.target / "afile"
        a_file.write_text("x", encoding="utf-8")

        with self.assertRaises(provision.ProvisionError):
            self.provision(target=a_file)

    def test_valid_target_does_not_raise(self):
        self.provision()


class DirectoryTreeTests(ProvisionCase):
    """The .roo and .vscode scaffolding of anvil:334 and anvil:396."""

    def test_creates_the_roo_tree(self):
        self.provision()

        for relative in (".roo", ".roo/commands", ".roo/skills", ".roo/rules"):
            self.assertTrue(
                (self.target / relative).is_dir(), "missing {}".format(relative)
            )

    def test_creates_the_vscode_directory(self):
        self.provision()

        self.assertTrue((self.target / ".vscode").is_dir())

    def test_existing_directories_are_left_alone(self):
        keeper = self.target / ".roo" / "rules" / "existing.md"
        keeper.parent.mkdir(parents=True)
        keeper.write_text("keep me", encoding="utf-8")

        self.provision()

        self.assertEqual(keeper.read_text(encoding="utf-8"), "keep me")

    def test_is_idempotent(self):
        self.provision()
        self.provision()

        self.assertTrue((self.target / ".roo" / "commands").is_dir())


class ArtifactTests(ProvisionCase):
    """The generated files, replacing the sed pipelines at anvil:373 and 389."""

    def test_writes_zoo_code_settings(self):
        self.provision()

        self.assertTrue((self.target / "zoo-code-settings.json").is_file())

    def test_zoo_code_settings_is_valid_json(self):
        self.provision()

        self.assertIsInstance(self.read_json("zoo-code-settings.json"), dict)

    def test_zoo_code_settings_has_no_unsubstituted_placeholders(self):
        self.provision()

        text = (self.target / "zoo-code-settings.json").read_text(encoding="utf-8")

        self.assertNotIn("${", text)

    def test_zoo_code_settings_carries_the_resolved_values(self):
        self.provision()

        settings = self.read_json("zoo-code-settings.json")
        local = settings["providerProfiles"]["apiConfigs"]["llama_swap"]

        self.assertEqual(local["openAiModelId"], CODER_MODEL)
        self.assertEqual(local["openAiCustomModelInfo"]["contextWindow"], 262144)
        self.assertIn("8000", local["openAiBaseUrl"])

    def test_declined_anthropic_points_architect_at_the_local_profile(self):
        self.provision()

        settings = self.read_json("zoo-code-settings.json")

        self.assertEqual(
            settings["providerProfiles"]["modeApiConfigs"]["architect"],
            LOCAL_PROFILE_ID,
        )

    def test_accepted_anthropic_points_architect_at_the_anthropic_profile(self):
        self.provision(
            repo_plan=plan(
                use_anthropic_for_frontier_modes=True,
                anthropic_api_key="sk-ant-secret",
                anthropic_model_id="claude-fable-5",
            )
        )

        settings = self.read_json("zoo-code-settings.json")

        self.assertEqual(
            settings["providerProfiles"]["modeApiConfigs"]["architect"],
            ANTHROPIC_PROFILE_ID,
        )

    def test_writes_mcp_json_into_the_roo_directory(self):
        self.provision()

        self.assertTrue((self.target / ".roo" / "mcp.json").is_file())

    def test_mcp_json_is_valid_json(self):
        self.provision()

        self.assertIsInstance(self.read_json(".roo/mcp.json"), dict)

    def test_mcp_json_resolves_the_workspace_to_an_absolute_path(self):
        self.provision()

        text = (self.target / ".roo" / "mcp.json").read_text(encoding="utf-8")

        self.assertIn(str(self.target.resolve()), text)
        self.assertNotIn("${workspaceFolder}", text)

    def test_mcp_json_carries_the_github_token(self):
        self.provision(repo_plan=plan(github_token="ghp_secret"))

        config = self.read_json(".roo/mcp.json")

        self.assertEqual(
            config["mcpServers"]["github"]["env"][
                "GITHUB_PERSONAL_ACCESS_TOKEN"
            ],
            "ghp_secret",
        )

    def test_writes_vscode_extensions(self):
        self.provision()

        self.assertIsInstance(self.read_json(".vscode/extensions.json"), dict)

    def test_installs_the_roo_rules_command(self):
        self.provision()

        self.assertTrue(
            (self.target / ".roo" / "commands" / "update_roo_rules.md").is_file()
        )

    def test_copies_the_roo_template_tree(self):
        self.provision()

        copied = self.target / "roo_template"

        self.assertTrue(copied.is_dir())
        self.assertTrue((copied / "rules").is_dir())
        self.assertTrue((copied / "commands").is_dir())

    def test_roo_template_copy_includes_file_contents(self):
        self.provision()

        source = REPO_ROOT / "templates" / "roo_template" / "rules" / "AGENTS.md"
        copied = self.target / "roo_template" / "rules" / "AGENTS.md"

        self.assertEqual(
            copied.read_text(encoding="utf-8"), source.read_text(encoding="utf-8")
        )

    def test_rerunning_refreshes_the_roo_template_without_nesting_it(self):
        """'cp -r' into an existing directory would create roo_template/roo_template."""
        self.provision()
        self.provision()

        self.assertFalse((self.target / "roo_template" / "roo_template").exists())


class SecretHandlingTests(ProvisionCase):
    """The bug escape_sed_replacement() at anvil:95 existed to work around."""

    HOSTILE_KEY = r"sk-ant-\&|'\"$(rm -rf /)"

    def test_hostile_api_key_survives_intact(self):
        self.provision(
            repo_plan=plan(
                use_anthropic_for_frontier_modes=True,
                anthropic_api_key=self.HOSTILE_KEY,
            )
        )

        settings = self.read_json("zoo-code-settings.json")

        self.assertEqual(
            settings["providerProfiles"]["apiConfigs"]["anthropic"][
                "anthropicApiKey"
            ],
            self.HOSTILE_KEY,
        )

    def test_hostile_api_key_still_yields_valid_json(self):
        self.provision(
            repo_plan=plan(
                use_anthropic_for_frontier_modes=True,
                anthropic_api_key=self.HOSTILE_KEY,
            )
        )

        self.assertIsInstance(self.read_json("zoo-code-settings.json"), dict)

    def test_hostile_github_token_survives_intact(self):
        self.provision(repo_plan=plan(github_token=self.HOSTILE_KEY))

        config = self.read_json(".roo/mcp.json")

        self.assertEqual(
            config["mcpServers"]["github"]["env"][
                "GITHUB_PERSONAL_ACCESS_TOKEN"
            ],
            self.HOSTILE_KEY,
        )

    def test_secrets_are_not_echoed_to_the_console(self):
        self.provision(
            repo_plan=plan(
                use_anthropic_for_frontier_modes=True,
                anthropic_api_key="sk-ant-topsecret",
                github_token="ghp_topsecret",
            )
        )

        self.assertNotIn("sk-ant-topsecret", self.output)
        self.assertNotIn("ghp_topsecret", self.output)


class GuidanceTests(ProvisionCase):
    """The reporting of anvil:333-420, which users rely on."""

    def test_reports_the_resolved_target(self):
        self.provision()

        self.assertIn(str(self.target.resolve()), self.output)

    def test_reports_the_context_window(self):
        self.provision()

        self.assertIn("262144", self.output)

    def test_reports_the_local_architect_choice(self):
        self.provision()

        self.assertIn("local", self.output.lower())

    def test_reports_the_anthropic_architect_choice_with_the_model(self):
        self.provision(
            repo_plan=plan(
                use_anthropic_for_frontier_modes=True,
                anthropic_api_key="k",
                anthropic_model_id="claude-fable-5",
            )
        )

        self.assertIn("claude-fable-5", self.output)

    def test_preserves_the_important_next_step_guidance(self):
        self.provision()

        self.assertIn("update_roo_rules", self.output)

    def test_reports_completion(self):
        self.provision()

        self.assertIn("complete", self.output.lower())

    def test_returns_the_resolved_target_path(self):
        result = self.provision()

        self.assertEqual(Path(result), self.target.resolve())


class DryRunTests(ProvisionCase):
    """--dry-run must describe the work without doing any of it."""

    def test_creates_no_directories(self):
        self.provision(dry_run=True)

        self.assertFalse((self.target / ".roo").exists())
        self.assertFalse((self.target / ".vscode").exists())

    def test_writes_no_files(self):
        self.provision(dry_run=True)

        self.assertEqual(list(self.target.iterdir()), [])

    def test_copies_no_templates(self):
        self.provision(dry_run=True)

        self.assertFalse((self.target / "roo_template").exists())

    def test_still_reports_what_it_would_do(self):
        self.provision(dry_run=True)

        self.assertIn("zoo-code-settings.json", self.output)

    def test_still_validates_the_target(self):
        """A dry run must not hide a mistake it would have caught."""
        with self.assertRaises(provision.ProvisionError):
            self.provision(target=self.target / "missing", dry_run=True)


class TemplateAvailabilityTests(ProvisionCase):
    """The template checks at anvil:295-318."""

    def test_missing_template_directory_is_reported(self):
        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(templates_dir=self.target / "no-templates")

        self.assertIn("not found", str(ctx.exception).lower())

    def test_missing_template_error_names_the_missing_path(self):
        empty = Path(self._tmp.name) / "empty-templates"
        empty.mkdir()

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(templates_dir=empty)

        self.assertIn(str(empty), str(ctx.exception))

    def test_nothing_is_written_when_a_template_is_missing(self):
        empty = Path(self._tmp.name) / "empty-templates2"
        empty.mkdir()

        with self.assertRaises(provision.ProvisionError):
            self.provision(templates_dir=empty)

        self.assertEqual(list(self.target.iterdir()), [])


class RoomodesDeploymentTests(ProvisionCase):
    """The .roomodes file is deployed to the repo root during provisioning."""

    def test_roomodes_is_deployed_to_repo_root(self):
        self.provision()

        roomodes_path = self.target / ".roomodes"
        self.assertTrue(roomodes_path.is_file())

    def test_roomodes_contains_docs_manager_mode(self):
        self.provision()

        content = (self.target / ".roomodes").read_text(encoding="utf-8")

        self.assertIn("slug: docs-manager", content)

    def test_roomodes_contains_qna_tester_mode(self):
        self.provision()

        content = (self.target / ".roomodes").read_text(encoding="utf-8")

        self.assertIn("slug: qna-tester", content)

    def test_roomodes_contains_qna_tester_name(self):
        self.provision()

        content = (self.target / ".roomodes").read_text(encoding="utf-8")

        self.assertIn("Q&A Tester", content)

    def test_dry_run_does_not_write_roomodes(self):
        self.provision(dry_run=True)

        self.assertFalse((self.target / ".roomodes").is_file())

    def test_roomodes_content_matches_template(self):
        self.provision()

        template_content = (
            REPO_ROOT / "templates" / "roo_template" / ".roomodes"
        ).read_text(encoding="utf-8")
        deployed_content = (self.target / ".roomodes").read_text(encoding="utf-8")

        self.assertEqual(deployed_content, template_content)


class ModeRulesDeploymentTests(ProvisionCase):
    """Mode-specific rules-* directories are deployed into .roo/."""

    def test_rules_qna_tester_is_deployed(self):
        self.provision()

        qna_rules = self.target / ".roo" / "rules-qna-tester"
        self.assertTrue(qna_rules.is_dir())

    def test_rules_qna_tester_contains_instructions(self):
        self.provision()

        instructions = (
            self.target / ".roo" / "rules-qna-tester" / "instructions.xml"
        )
        self.assertTrue(instructions.is_file())

    def test_rules_qna_tester_content_matches_template(self):
        self.provision()

        template_content = (
            REPO_ROOT
            / "templates"
            / "roo_template"
            / "rules-qna-tester"
            / "instructions.xml"
        ).read_text(encoding="utf-8")
        deployed_content = (
            self.target / ".roo" / "rules-qna-tester" / "instructions.xml"
        ).read_text(encoding="utf-8")

        self.assertEqual(deployed_content, template_content)

    def test_rules_docs_manager_is_deployed(self):
        self.provision()

        docs_rules = self.target / ".roo" / "rules-docs-manager"
        self.assertTrue(docs_rules.is_dir())

    def test_rules_docs_manager_contains_guidelines(self):
        self.provision()

        guidelines = (
            self.target / ".roo" / "rules-docs-manager" / "guidelines.xml"
        )
        self.assertTrue(guidelines.is_file())

    def test_dry_run_does_not_deploy_mode_rules(self):
        self.provision(dry_run=True)

        self.assertFalse(
            (self.target / ".roo" / "rules-qna-tester").exists()
        )
        self.assertFalse(
            (self.target / ".roo" / "rules-docs-manager").exists()
        )

    def test_existing_mode_rules_are_overwritten(self):
        existing = (
            self.target / ".roo" / "rules-qna-tester" / "instructions.xml"
        )
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("old content", encoding="utf-8")

        self.provision()

        new_content = (
            self.target / ".roo" / "rules-qna-tester" / "instructions.xml"
        ).read_text(encoding="utf-8")
        self.assertNotEqual(new_content, "old content")
        self.assertIn("<instructions>", new_content)


class FullDeploymentIntegrationTests(ProvisionCase):
    """End-to-end: the full provisioned tree has all expected files."""

    def test_complete_tree_structure(self):
        self.provision()

        expected = [
            ".roomodes",
            ".roo",
            ".roo/commands",
            ".roo/skills",
            ".roo/rules",
            ".roo/mcp.json",
            ".roo/rules-qna-tester",
            ".roo/rules-qna-tester/instructions.xml",
            ".roo/rules-docs-manager",
            ".roo/rules-docs-manager/guidelines.xml",
            ".vscode/extensions.json",
            "roo_template",
            "zoo-code-settings.json",
        ]

        for relative in expected:
            self.assertTrue(
                (self.target / relative).exists(),
                "missing {}".format(relative),
            )

    def test_deployed_roomodes_and_qna_rules_both_present(self):
        self.provision()

        self.assertTrue((self.target / ".roomodes").is_file())
        self.assertTrue(
            (self.target / ".roo" / "rules-qna-tester" / "instructions.xml").is_file()
        )

    def test_deployed_roomodes_mentions_both_modes(self):
        self.provision()

        content = (self.target / ".roomodes").read_text(encoding="utf-8")

        self.assertIn("docs-manager", content)
        self.assertIn("qna-tester", content)


class OxylabsPlanTests(ProvisionCase):
    """Behavior 2: RepoPlan accepts oxylabs fields and _write_mcp_settings passes them through."""

    def test_repo_plan_accepts_oxylabs_username_and_password_defaults(self):
        """2a: RepoPlan must accept oxylabs_username="" and oxylabs_password="" as kwargs with defaults of ""."""
        repo_plan = plan()

        self.assertTrue(hasattr(repo_plan, "oxylabs_username"))
        self.assertTrue(hasattr(repo_plan, "oxylabs_password"))
        self.assertEqual(repo_plan.oxylabs_username, "")
        self.assertEqual(repo_plan.oxylabs_password, "")

    def test_write_mcp_settings_passes_oxylabs_credentials(self):
        """2b: _write_mcp_settings passes oxylabs_username and oxylabs_password from repo_plan."""
        self.provision(repo_plan=plan(oxylabs_username="test_user", oxylabs_password="test_pass"))

        config = self.read_json(".roo/mcp.json")

        self.assertEqual(
            config["mcpServers"]["oxylabs"]["env"]["OXYLABS_USERNAME"],
            "test_user",
        )
        self.assertEqual(
            config["mcpServers"]["oxylabs"]["env"]["OXYLABS_PASSWORD"],
            "test_pass",
        )

    def test_empty_oxylabs_credentials_yield_disabled_server(self):
        """2c: empty oxylabs credentials yield disabled server in .roo/mcp.json."""
        self.provision(repo_plan=plan(oxylabs_username="", oxylabs_password=""))

        config = self.read_json(".roo/mcp.json")

        self.assertEqual(config["mcpServers"]["oxylabs"]["disabled"], True)
        self.assertEqual(
            config["mcpServers"]["oxylabs"]["env"]["OXYLABS_USERNAME"],
            "",
        )
        self.assertEqual(
            config["mcpServers"]["oxylabs"]["env"]["OXYLABS_PASSWORD"],
            "",
        )


class RulesArchitectDeploymentTests(ProvisionCase):
    """Behavior 5: the existing _deploy_mode_rules loop picks up any rules-* directory."""

    def test_provisioning_deploys_roo_rules_architect_via_existing_rules_loop(self):
        """5: _deploy_mode_rules copies rules-architect from roo_template into .roo/.

        The loop at provision:472 iterates over every sub-directory in
        ``roo_template/`` whose name starts with ``rules-`` and copies it into
        ``.roo/``.  The new ``rules-architect/instructions.xml`` template sits in
        that tree, so the existing loop should deploy it without any Python code
        change.
        """
        self.provision()

        # File exists in the deployed tree
        deployed = self.target / ".roo" / "rules-architect" / "instructions.xml"
        self.assertTrue(deployed.is_file(), ".roo/rules-architect/instructions.xml missing")

        # File is valid XML (parse with ElementTree)
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(deployed))
        root = tree.getroot()
        self.assertEqual(root.tag, "instructions")


class ReprovisioningEndToEndTests(ProvisionCase):
    """Behavior 6: re-provisioning an already-set-up repo does not corrupt it."""

    def test_reprovisioning_an_already_setup_repo_end_to_end(self):
        """6: re-running setup-repo on the same target preserves all files.

        First provisioning writes ``.roo/mcp.json`` with oxylabs credentials.
        A second provisioning on the same target should not corrupt ``mcp.json``
        or ``zoo-code-settings.json``.
        """
        # -- First provisioning with oxylabs credentials ---
        self.provision(
            repo_plan=plan(
                oxylabs_username="test_user",
                oxylabs_password="test_pass",
            )
        )

        # Read back mcp.json after first provisioning
        config_first = self.read_json(".roo/mcp.json")
        self.assertEqual(
            config_first["mcpServers"]["oxylabs"]["env"]["OXYLABS_USERNAME"],
            "test_user",
        )
        self.assertEqual(
            config_first["mcpServers"]["oxylabs"]["env"]["OXYLABS_PASSWORD"],
            "test_pass",
        )

        # Verify zoo-code-settings.json still exists and is valid
        settings_first = self.read_json("zoo-code-settings.json")
        self.assertIsInstance(settings_first, dict)

        # -- Second provisioning on the same target ---
        self.provision(
            repo_plan=plan(
                oxylabs_username="test_user",
                oxylabs_password="test_pass",
            )
        )

        # Read back mcp.json after second provisioning
        config_second = self.read_json(".roo/mcp.json")
        self.assertEqual(
            config_second["mcpServers"]["oxylabs"]["env"]["OXYLABS_USERNAME"],
            "test_user",
        )
        self.assertEqual(
            config_second["mcpServers"]["oxylabs"]["env"]["OXYLABS_PASSWORD"],
            "test_pass",
        )
        # mcp.json is valid JSON (read_json already parses it, so if we got here it's valid)
        self.assertIsInstance(config_second, dict)

        # zoo-code-settings.json still exists and is valid
        settings_second = self.read_json("zoo-code-settings.json")
        self.assertIsInstance(settings_second, dict)


if __name__ == "__main__":
    unittest.main()
