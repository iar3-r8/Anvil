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
        use_anthropic_for_architect=False,
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
                use_anthropic_for_architect=True,
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
                use_anthropic_for_architect=True,
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
                use_anthropic_for_architect=True,
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
                use_anthropic_for_architect=True,
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
                use_anthropic_for_architect=True,
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


if __name__ == "__main__":
    unittest.main()
