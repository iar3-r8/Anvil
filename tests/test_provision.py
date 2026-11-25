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
import unittest.mock as mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import provision, render  # noqa: E402

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

    def test_container_target_zoo_settings_point_at_the_host_gateway(self):
        """container_target=True re-points every rendered URL at the host
        (``host.docker.internal``) with the host-mapped LLM port."""
        self.provision(repo_plan=plan(container_target=True))

        settings = self.read_json("zoo-code-settings.json")
        local = settings["providerProfiles"]["apiConfigs"]["llama_swap"]
        index_config = settings["globalSettings"]["codebaseIndexConfig"]

        self.assertEqual(local["openAiBaseUrl"], "http://host.docker.internal:8000/v1")
        self.assertEqual(
            index_config["codebaseIndexOpenAiCompatibleBaseUrl"],
            "http://host.docker.internal:8000/v1",
        )
        self.assertEqual(
            index_config["codebaseIndexQdrantUrl"], "http://host.docker.internal:6333"
        )

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

    def test_stray_files_in_mode_rules_are_removed_on_reprovision(self):
        """22 (guard): .roo/rules-*/ is still replaced wholesale, not merged.

        ``test_existing_mode_rules_are_overwritten`` locks the overwrite half;
        this test locks the removal half, so a future change cannot turn the
        deployment into a copy-only (merge) without breaking it.
        """
        self.provision()

        orphan = self.target / ".roo" / "rules-qna-tester" / "orphan.xml"
        orphan.write_text("<orphan/>", encoding="utf-8")
        self.assertTrue(orphan.is_file())

        self.provision()

        # (a) the stray file is gone.
        self.assertFalse(orphan.exists())

        # (b) instructions.xml is byte-identical to the template.
        template = (
            REPO_ROOT
            / "templates"
            / "roo_template"
            / "rules-qna-tester"
            / "instructions.xml"
        ).read_bytes()
        deployed = (
            self.target / ".roo" / "rules-qna-tester" / "instructions.xml"
        ).read_bytes()

        self.assertEqual(deployed, template)


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
        """2b: _write_mcp_settings passes oxylabs_username and oxylabs_password
        through to the hosted headers in .roo/mcp.json."""
        self.provision(repo_plan=plan(oxylabs_username="test_user", oxylabs_password="test_pass"))

        config = self.read_json(".roo/mcp.json")

        entry = config["mcpServers"].get("oxylabs")
        headers = entry.get("headers") if isinstance(entry, dict) else None
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers.get("X-Oxylabs-Username"),
            "test_user",
        )
        self.assertEqual(
            headers.get("X-Oxylabs-Password"),
            "test_pass",
        )

    def test_empty_oxylabs_credentials_yield_disabled_server(self):
        """2c: empty oxylabs credentials yield a disabled hosted server in
        .roo/mcp.json with both header keys present as empty strings."""
        self.provision(repo_plan=plan(oxylabs_username="", oxylabs_password=""))

        config = self.read_json(".roo/mcp.json")

        entry = config["mcpServers"].get("oxylabs")
        self.assertIsInstance(entry, dict, "oxylabs server entry is missing")
        self.assertEqual(entry.get("disabled"), True)
        headers = entry.get("headers")
        self.assertIsInstance(headers, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers.get("X-Oxylabs-Username"),
            "",
        )
        self.assertEqual(
            headers.get("X-Oxylabs-Password"),
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
        headers_first = config_first["mcpServers"].get("oxylabs", {}).get("headers")
        self.assertIsInstance(headers_first, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers_first.get("X-Oxylabs-Username"),
            "test_user",
        )
        self.assertEqual(
            headers_first.get("X-Oxylabs-Password"),
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
        headers_second = config_second["mcpServers"].get("oxylabs", {}).get("headers")
        self.assertIsInstance(headers_second, dict, "oxylabs entry must carry headers")
        self.assertEqual(
            headers_second.get("X-Oxylabs-Username"),
            "test_user",
        )
        self.assertEqual(
            headers_second.get("X-Oxylabs-Password"),
            "test_pass",
        )
        # mcp.json is valid JSON (read_json already parses it, so if we got here it's valid)
        self.assertIsInstance(config_second, dict)

        # zoo-code-settings.json still exists and is valid
        settings_second = self.read_json("zoo-code-settings.json")
        self.assertIsInstance(settings_second, dict)

    def test_zoo_code_settings_is_still_rewritten_wholesale(self):
        """21 (guard): zoo-code-settings.json is still rewritten wholesale.

        Locks the "no change" decision from the plan: if a future merge is
        ever added to the zoo-settings step, a key the user injected between
        runs would survive, and this test would fail.
        """
        # Baseline: what a fresh provision into a second target produces.
        # The rendered file depends only on the plan values, never on the
        # target path, so a whole-structure comparison is meaningful.
        baseline = self.target.parent / "baseline-repo"
        baseline.mkdir()
        self.provision(target=baseline, echo=lambda _line: None)
        baseline_settings = json.loads(
            (baseline / "zoo-code-settings.json").read_text(encoding="utf-8")
        )

        # First provision, then corrupt the file between runs.
        self.provision()
        stale = self.target / "zoo-code-settings.json"
        stale.write_text(
            json.dumps({"stale": True}), encoding="utf-8"
        )

        self.provision()

        settings = self.read_json("zoo-code-settings.json")

        # (a) the injected key is gone.
        self.assertNotIn("stale", settings)

        # (b) the resolved values are back, exactly as a fresh provision writes them.
        self.assertEqual(settings, baseline_settings)


class HarvestCommandExclusionTests(ProvisionCase):
    """B9: the anvil-local harvest command is not provisioned into targets.

    ``harvest-roo-templates.md`` reads ``templates/roo_template/``, a path a
    target repository does not have, so shipping it would install a command
    that cannot work. It lives only in the anvil repo's own
    ``.roo/commands/`` (re-included through the ``.gitignore`` negation);
    the provisioner's command source is ``templates/roo_template/``, so the
    command must never appear in a provisioned tree.
    """

    def test_harvest_command_is_not_in_the_target_roo_commands(self):
        self.provision()

        self.assertFalse(
            (self.target / ".roo" / "commands" / "harvest-roo-templates.md").exists()
        )

    def test_existing_provisioned_command_still_lands(self):
        """The exclusion is specific: the command the provisioner does own
        (``update_roo_rules.md``, the positive case at test_provision.py:266)
        is still shipped, so a blanket no-commands change would be caught.

        Note: only ``update_roo_rules.md`` is written into ``.roo/commands/``
        by the provisioner. The other template commands (e.g.
        ``create-pull-request.md``) travel with the whole
        ``templates/roo_template/`` tree into the root-level ``roo_template/``
        copy, not into ``.roo/commands/`` — locked by the sibling test below.
        """
        self.provision()

        self.assertTrue(
            (self.target / ".roo" / "commands" / "update_roo_rules.md").is_file()
        )

    def test_harvest_command_is_not_in_the_provisioned_template_copy(self):
        self.provision()

        template_commands = self.target / "roo_template" / "commands"

        self.assertFalse(
            (template_commands / "harvest-roo-templates.md").exists()
        )
        self.assertTrue((template_commands / "write-github-task.md").is_file())

    def test_harvest_command_lives_only_in_the_anvil_local_tree(self):
        """Guard: the boundary holds at the source side, so an anvil-local
        command cannot leak into a target through the provisioner's command
        source (``templates/roo_template/commands/``)."""
        local = REPO_ROOT / ".roo" / "commands" / "harvest-roo-templates.md"
        template = (
            REPO_ROOT / "templates" / "roo_template" / "commands"
            / "harvest-roo-templates.md"
        )

        self.assertTrue(local.is_file())
        self.assertFalse(template.exists())


class BrainstormCommandDeliveryTests(ProvisionCase):
    """Behaviour 6: provisioning delivers the brainstorm-feature command into
    the provisioned target, byte-identical to the template.

    Boundary pin: ``_copy_roo_template()`` already copies the whole
    roo_template/ tree, so this test passes on arrival. It stays green while
    the copy is a whole-tree copy and turns red if the copy is narrowed
    (e.g. commands/ excluded) or the bytes drift from the template.
    """

    def test_provisioned_target_contains_the_brainstorm_command_file(self):
        self.provision()

        copied = self.target / "roo_template" / "commands" / "brainstorm-feature.md"

        self.assertTrue(copied.is_file(), "missing {}".format(copied))

    def test_brainstorm_command_is_byte_identical_to_the_template(self):
        self.provision()

        source = (
            REPO_ROOT / "templates" / "roo_template" / "commands"
            / "brainstorm-feature.md"
        ).read_bytes()
        copied = (
            self.target / "roo_template" / "commands" / "brainstorm-feature.md"
        ).read_bytes()

        self.assertEqual(copied, source)


class ImplementNextIssueCommandDeliveryTests(ProvisionCase):
    """Behaviour 10 (plans/implement-next-issue.md): provisioning delivers the
    implement-next-issue command into the provisioned target, byte-identical
    to the template.

    Boundary pin: ``_copy_roo_template()`` already copies the whole
    roo_template/ tree, so this test passes the moment the template file
    exists. It stays green while the copy is a whole-tree copy and turns
    red if the copy is narrowed (e.g. commands/ excluded) or the bytes
    drift from the template.

    Expected red reason: the template file does not exist yet, so the
    target side is missing. The source-side read is a ``read_bytes`` of a
    missing path, so the red failure is a FileNotFoundError naming the
    template source — the intended failure mode, fixed by the green step
    creating the file.
    """

    def test_provisioned_target_contains_the_implement_next_issue_command_file(self):
        self.provision()

        copied = (
            self.target / "roo_template" / "commands"
            / "implement-next-issue.md"
        )

        self.assertTrue(copied.is_file(), "missing {}".format(copied))

    def test_implement_next_issue_command_is_byte_identical_to_the_template(self):
        self.provision()

        source = (
            REPO_ROOT / "templates" / "roo_template" / "commands"
            / "implement-next-issue.md"
        ).read_bytes()
        copied = (
            self.target / "roo_template" / "commands"
            / "implement-next-issue.md"
        ).read_bytes()

        self.assertEqual(copied, source)


class SetupRepoPiMcpJsonTests(ProvisionCase):
    """Behaviour 15 (plans/pi-phase12-launch-gen.md): setup-repo-writes-pi-mcp-json.

    ``provision.setup_repo`` must write ``<target>/.pi/mcp.json`` holding
    ``render.pi_mcp_settings(str(target))`` — the git server's argv carries the
    resolved target path, and the ``${GITHUB_TOKEN}`` / ``${OXYLABS_*}`` tokens
    stay verbatim (the renderer takes no credential, so nothing else can leak).

    The load-bearing assertion is byte-equality with the seam's own output —
    ``render.pi_mcp_settings(str(resolved_target))`` — plus the parsed pin that
    the git server's ``--repository`` argument is the target path. The golden
    fixture pin (seam vs ``tests/fixtures/golden_pi_mcp.json``) already lives in
    ``tests/test_render.py::TestPiMcpGoldenParity`` and is not repeated here.

    Expected red reason: ``setup_repo`` currently touches no ``.pi/`` at all,
    so the fresh target carries no ``.pi/mcp.json``. The first positive test
    fails on the absence assertion (``assertTrue``); the second fails with a
    ``FileNotFoundError`` when reading ``.pi/mcp.json``.

    The error-path test drives the same entry point through a faulted seam:
    ``render.pi_mcp_settings`` is patched to raise ``render.RenderError``, which
    is the only way to fail the pi-mcp step without touching production code
    (the renderer is a pure template read and always succeeds on this checkout).
    The patch is on the ``render`` module attribute that ``provision`` resolves
    at call time (``provision`` does ``from . import render``), so no private
    import site is forced.
    """

    def test_setup_repo_writes_pi_mcp_json_holding_the_rendered_seam_output(self):
        """Fresh target, one ``setup_repo`` run: ``.pi/mcp.json`` holds exactly
        ``render.pi_mcp_settings(str(resolved_target))``."""
        resolved = self.provision()

        pi_mcp = self.target / ".pi" / "mcp.json"
        self.assertTrue(
            pi_mcp.is_file(),
            "setup_repo left no {}".format(pi_mcp),
        )

        on_disk = pi_mcp.read_text(encoding="utf-8")
        expected = render.pi_mcp_settings(str(self.target))

        self.assertEqual(
            on_disk,
            expected,
            "<target>/.pi/mcp.json must hold render.pi_mcp_settings(str(target)) verbatim",
        )

    def test_pi_mcp_json_git_server_argv_carries_the_target_path(self):
        """Parsed pin: the git server's ``--repository`` argument is the
        resolved target path — ``${workspaceFolder}`` is substituted, not left
        for the IDE."""
        self.provision()

        config = self.read_json(".pi/mcp.json")
        git_args = config["mcpServers"]["git"]["args"]

        self.assertNotIn("${workspaceFolder}", git_args)
        self.assertIn(str(self.target), git_args)

    def test_render_error_from_the_pi_mcp_seam_propagates_and_writes_nothing_further(self):
        """Error clause: a ``RenderError`` from the ``pi_mcp_settings`` seam
        propagates out of ``setup_repo`` — not swallowed, not translated — and
        nothing is written beyond that step.

        Three pins:

        * the seam is actually called with the resolved target path (the patch
          records the argument), so a green ``setup_repo`` cannot pass by never
          reaching the pi-mcp step at all;
        * the raised exception is the *very same* ``render.RenderError``
          instance the seam raised — object identity proves it was propagated,
          not caught and re-raised as a ``ProvisionError`` wrapper or any other
          exception type;
        * the run never reaches its completion report: a mid-run failure at the
          pi-mcp step means ``setup_repo`` cannot finish, whatever order the
          steps land in. The positive steps before the failure (directories,
          ``.gitignore``, ``zoo-code-settings.json``) are expected to have
          written their files — the behaviour only guarantees nothing
          *further* is written, so the completion report is the right
          position-independent marker.

        The seam is faulted by patching ``render.pi_mcp_settings`` on the
        ``render`` module attribute that ``provision`` resolves at call time
        (``provision`` does ``from . import render``); the real renderer is a
        pure template read and always succeeds on this checkout, so a patch is
        the only way to make this step fail without touching production code.
        """
        boom = render.RenderError("render failed")
        seam_calls = []

        def faulted_seam(workspace_folder):
            seam_calls.append(workspace_folder)
            raise boom

        with mock.patch.object(render, "pi_mcp_settings", side_effect=faulted_seam):
            with self.assertRaises(render.RenderError) as ctx:
                self.provision()

        # The seam was reached with the resolved target path.
        self.assertEqual(seam_calls, [str(self.target)])

        # Propagation: the same object, not a translated or wrapped exception.
        self.assertIs(ctx.exception, boom)
        self.assertNotIsInstance(ctx.exception, provision.ProvisionError)

        # Nothing further was written: the run never finished.
        self.assertNotIn(
            "IMPORTANT NEXT STEP",
            self.output,
            "a mid-run RenderError must not reach the completion report",
        )

    def test_pi_mcp_json_carries_no_credential_value(self):
        """Behaviour 16 (plans/pi-phase12-launch-gen.md):
        pi-mcp-json-carries-no-credential-value [PIN] [SKIP].

        A plan carrying a non-empty ``github_token`` and a non-empty
        Oxylabs username/password pair is provisioned; the rendered
        ``.pi/mcp.json`` still holds ``${GITHUB_TOKEN}``,
        ``${OXYLABS_USERNAME}`` and ``${OXYLABS_PASSWORD}`` verbatim,
        and none of the three credential values appears anywhere in the
        file text.

        Boundary pin: ``render.pi_mcp_settings`` takes no credential
        parameter at all, so the invariant holds by construction and the
        test is green at write. It turns red if a future change ever
        substitutes plan credentials into the Pi file — the placeholders
        are asserted present and the values asserted absent, so a
        regression in either direction is caught.
        """
        token = "ghp_pin_4f7c9e2a1b8d"
        username = "pin-oxylabs-user"
        password = "pin-oxylabs-secret"

        repo_plan = plan(
            github_token=token,
            oxylabs_username=username,
            oxylabs_password=password,
        )
        self.provision(repo_plan=repo_plan)

        # The Given is real: the plan the run carried the non-empty values.
        self.assertEqual(repo_plan.github_token, token)
        self.assertEqual(repo_plan.oxylabs_username, username)
        self.assertEqual(repo_plan.oxylabs_password, password)

        text = (self.target / ".pi" / "mcp.json").read_text(encoding="utf-8")

        for placeholder in (
            "${GITHUB_TOKEN}",
            "${OXYLABS_USERNAME}",
            "${OXYLABS_PASSWORD}",
        ):
            self.assertIn(
                placeholder,
                text,
                "pi-mcp.json must keep {} verbatim for Pi runtime "
                "interpolation".format(placeholder),
            )

        for value in (token, username, password):
            self.assertNotIn(
                value,
                text,
                "a credential value leaked into .pi/mcp.json",
            )


class SetupRepoGuardrailsJsonTests(ProvisionCase):
    """Behaviour 17 (plans/pi-phase12-launch-gen.md):
    setup-repo-writes-guardrails.

    ``provision.setup_repo`` must write ``<target>/.pi/extensions/
    guardrails.json`` holding ``render.guardrails_settings()`` — the seam
    takes no arguments, builds the document, and re-validates it, so the
    file on disk is the validated document by construction.

    The load-bearing assertion is byte-equality with the seam's own
    output — ``render.guardrails_settings()`` — plus the parsed pin that
    the file decodes as JSON. The golden fixture pin (seam vs
    ``tests/fixtures/golden_pi_guardrails.json``) already lives in
    ``tests/test_piguardrails.py`` and is not repeated here.

    Expected red reason: ``setup_repo`` currently touches no
    ``.pi/extensions/`` at all, so the fresh target carries no
    ``guardrails.json``. The existence test fails on the absence
    assertion (``assertTrue``); the parse test fails with a
    ``FileNotFoundError`` reading ``.pi/extensions/guardrails.json``.

    The error-path test drives the same entry point through a faulted
    seam: ``render.guardrails_settings`` is patched to raise
    ``render.RenderError`` (no arguments — the seam takes none), which is
    the only way to fail the guardrails step without touching production
    code (the renderer re-validates and always succeeds on this checkout).
    The patch is on the ``render`` module attribute that ``provision``
    resolves at call time (``provision`` does ``from . import render``).
    """

    def test_setup_repo_writes_guardrails_json_holding_the_rendered_seam_output(self):
        """Fresh target, one ``setup_repo`` run:
        ``.pi/extensions/guardrails.json`` holds exactly
        ``render.guardrails_settings()``."""
        resolved = self.provision()

        guardrails = self.target / ".pi" / "extensions" / "guardrails.json"
        self.assertTrue(
            guardrails.is_file(),
            "setup_repo left no {}".format(guardrails),
        )

        on_disk = guardrails.read_text(encoding="utf-8")
        expected = render.guardrails_settings()

        self.assertEqual(
            on_disk,
            expected,
            "<target>/.pi/extensions/guardrails.json must hold "
            "render.guardrails_settings() verbatim",
        )

    def test_guardrails_json_parses_as_the_validated_document(self):
        """Parsed pin: the file on disk decodes as JSON and equals the
        seam's own parsed output — the document the renderer re-validated
        before returning it."""
        self.provision()

        on_disk = (
            self.target / ".pi" / "extensions" / "guardrails.json"
        ).read_text(encoding="utf-8")
        parsed = json.loads(on_disk)

        self.assertIsInstance(parsed, dict)
        self.assertEqual(
            parsed,
            json.loads(render.guardrails_settings()),
            "the on-disk document must be the validated guardrails document",
        )

    def test_render_error_from_the_guardrails_seam_propagates_and_writes_nothing_further(self):
        """Error clause: a ``RenderError`` from the ``guardrails_settings``
        seam propagates out of ``setup_repo`` — not swallowed, not
        translated — and nothing is written beyond that step.

        Three pins:

        * the seam is actually called (the patch records the call), so a
          green ``setup_repo`` cannot pass by never reaching the
          guardrails step at all;
        * the raised exception is the *very same* ``render.RenderError``
          instance the seam raised — object identity proves it was
          propagated, not caught and re-raised as a ``ProvisionError``
          wrapper or any other exception type;
        * the run never reaches its completion report: a mid-run failure
          at the guardrails step means ``setup_repo`` cannot finish,
          whatever order the steps land in. The positive steps before the
          failure are expected to have written their files — the behaviour
          only guarantees nothing *further* is written, so the completion
          report is the right position-independent marker.

        The seam is faulted by patching ``render.guardrails_settings`` on
        the ``render`` module attribute that ``provision`` resolves at
        call time (``provision`` does ``from . import render``); the real
        renderer is a pure build-plus-validate and always succeeds on
        this checkout, so a patch is the only way to make this step fail
        without touching production code.
        """
        boom = render.RenderError("render failed")
        seam_calls = []

        def faulted_seam():
            seam_calls.append(None)
            raise boom

        with mock.patch.object(render, "guardrails_settings", side_effect=faulted_seam):
            with self.assertRaises(render.RenderError) as ctx:
                self.provision()

        # The seam was reached.
        self.assertEqual(seam_calls, [None])

        # Propagation: the same object, not a translated or wrapped exception.
        self.assertIs(ctx.exception, boom)
        self.assertNotIsInstance(ctx.exception, provision.ProvisionError)

        # Nothing further was written: the run never finished.
        self.assertNotIn(
            "IMPORTANT NEXT STEP",
            self.output,
            "a mid-run RenderError must not reach the completion report",
        )


class SetupRepoModelsSeederTests(ProvisionCase):
    """Behaviour 19 (plans/pi-phase12-launch-gen.md):
    models-json-seeds-the-agent-volume-only.

    ``provision.setup_repo`` must seed the ``sandbox-agent`` docker
    volume — the sandbox container's agent home, where Pi reads
    ``models.json`` (``anvilkit/pi/pisandbox.py``) — through an
    **injected** seeder seam, never through docker itself. The suite
    injects a recorder, so no test touches the docker daemon.

    Seam shape pinned here (design decision, flagged to the green step):
    ``setup_repo`` gains an appended, defaulted parameter
    ``seed_models_json=None``. When a seeder is provided it is called
    exactly once with ``(volume_name, models_text)`` — the named volume
    and the ``render.pi_models_settings`` text — and returns the docker
    runner triple ``(code, stdout, stderr)``, matching the product of
    ``cli._docker_runner_factory()`` (anvilkit/cli.py:1018-1040), which
    the production seeder executes its seeding argv through. A
    non-zero exit code is the failure report — the way a docker argv
    runner reports failure, so that is what this class pins (not a
    raised exception). ``None`` (the default) skips seeding entirely:
    the 123 pre-existing tests call ``setup_repo`` without the
    parameter and the suite must never touch docker, and
    ``provision`` cannot import ``cli`` (``cli`` imports
    ``provision``), so the production docker seeder must be passed in
    by ``cli.setup_repo`` when it is wired. FLAG: the default path
    therefore seeds nothing until that wiring lands.

    The models document's arguments: ``model_id`` and ``context_window``
    source from the plan; the host and port are the IN-NETWORK gateway
    address ``llama-swap:8080`` — the manager-confirmed decision recorded
    under Assumptions in the plan: ``sandbox-internal`` is declared
    ``internal: true`` in ``docker-compose.yml`` (the sandbox container
    has no host route, so a ``127.0.0.1`` document would be
    unreachable), and the compose precedents pin
    ``PI_GATEWAY_HOST=llama-swap`` / ``PI_GATEWAY_PORT=8080``. They are
    fixed facts of the network, not plan values.

    The two negative pins: no ``models.json`` may exist anywhere under
    the target (the document lives in the volume, not the repo), and
    the seeder must receive the models document — never the bytes of a
    project-local file (``.pi/mcp.json``, ``.pi/extensions/
    guardrails.json``, any role document).

    Expected red reason: ``setup_repo`` takes no ``seed_models_json``
    parameter yet, so every test in this class fails with
    ``TypeError: setup_repo() got an unexpected keyword argument
    'seed_models_json'`` — not a collection error, and the pre-existing
    tests (which pass no such parameter) stay green.
    """

    AGENT_VOLUME = "sandbox-agent"
    # In-network gateway address — plan assumption (pi-phase12-launch-gen.md):
    # the sandbox-internal network has no host route, so 127.0.0.1 is unreachable.
    SANDBOX_GATEWAY_HOST = "llama-swap"
    SANDBOX_GATEWAY_PORT = 8080

    def _expected_models_text(self, repo_plan):
        """The models document seeded into the agent volume: plan values
        for model and context, the in-network address for host/port."""
        return render.pi_models_settings(
            repo_plan.coder_model_id,
            self.SANDBOX_GATEWAY_PORT,
            repo_plan.context_window,
            host=self.SANDBOX_GATEWAY_HOST,
        )

    def test_setup_repo_invokes_the_seeder_once_with_the_models_document_for_the_sandbox_agent_volume(self):
        """Positive: with a recording seeder injected, one
        ``setup_repo`` run invokes the seam exactly once, with the
        ``sandbox-agent`` volume and the ``render.pi_models_settings``
        text rendered from the plan's values."""
        repo_plan = plan()
        calls = []

        def seeder(volume, models_text):
            calls.append((volume, models_text))
            return (0, "", "")

        self.provision(repo_plan=repo_plan, seed_models_json=seeder)

        expected = self._expected_models_text(repo_plan)
        self.assertEqual(
            calls,
            [(self.AGENT_VOLUME, expected)],
            "the seeder must be invoked exactly once with "
            "(sandbox-agent, render.pi_models_settings text for the plan's values)",
        )

    def test_no_models_json_exists_anywhere_under_the_target(self):
        """[PIN] the models document goes into the agent volume, not the
        repository: after a successful seeded run, no file named
        ``models.json`` exists anywhere under ``<target>``."""
        def seeder(volume, models_text):
            return (0, "", "")

        self.provision(seed_models_json=seeder)

        offenders = sorted(
            str(path.relative_to(self.target))
            for path in self.target.rglob("models.json")
        )
        self.assertEqual(
            offenders,
            [],
            "no models.json may exist anywhere under <target> — it "
            "lives in the {} volume".format(self.AGENT_VOLUME),
        )

    def test_the_seeder_receives_the_models_document_not_project_local_files(self):
        """[PIN] what the seeder is asked to seed is the models document:
        it equals the renderer's own output for the plan's values, and
        it differs from the on-disk bytes of every project-local file
        the run wrote — ``.pi/mcp.json``, ``.pi/extensions/
        guardrails.json``, and any role document under ``.pi/roles/``."""
        repo_plan = plan()
        calls = []

        def seeder(volume, models_text):
            calls.append((volume, models_text))
            return (0, "", "")

        self.provision(repo_plan=repo_plan, seed_models_json=seeder)

        self.assertEqual(len(calls), 1, "the seeder must be invoked exactly once")
        volume, models_text = calls[0]

        self.assertEqual(
            models_text,
            self._expected_models_text(repo_plan),
            "the recorded payload must be the render.pi_models_settings "
            "output for the plan's values",
        )

        roles_dir = self.target / ".pi" / "roles"
        project_local = [
            self.target / ".pi" / "mcp.json",
            self.target / ".pi" / "extensions" / "guardrails.json",
        ]
        if roles_dir.is_dir():
            project_local.extend(sorted(roles_dir.glob("*.md")))

        for path in project_local:
            if path.is_file():
                self.assertNotEqual(
                    models_text,
                    path.read_text(encoding="utf-8"),
                    "the seeder must never receive the bytes of the "
                    "project-local file {}".format(path),
                )

    def test_a_seeder_that_reports_failure_raises_provision_error_naming_the_volume(self):
        """Error clause: a seeder that reports failure — a non-zero exit
        code, the way the production docker argv runner reports it —
        makes ``setup_repo`` raise ``ProvisionError`` naming the
        ``sandbox-agent`` volume, and the run never reaches its
        completion report."""
        calls = []

        def failing_seeder(volume, models_text):
            calls.append((volume, models_text))
            return (1, "", "docker: seeding the agent volume failed")

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(seed_models_json=failing_seeder)

        self.assertEqual(len(calls), 1, "the seeder must have been invoked")
        self.assertIn(
            self.AGENT_VOLUME,
            str(ctx.exception),
            "the ProvisionError must name the {} volume".format(self.AGENT_VOLUME),
        )
        self.assertNotIn(
            "IMPORTANT NEXT STEP",
            self.output,
            "a failed seeder must not reach the completion report",
        )


class SetupRepoDryRunPiTests(ProvisionCase):
    """Behaviour 20 (plans/pi-phase12-launch-gen.md):
    dry-run-names-every-file-and-writes-none.

    A ``dry_run=True`` run must *name* every Pi artifact it would touch —
    ``<target>/.pi/mcp.json``, ``<target>/.pi/extensions/guardrails.json``,
    the ``models.json`` volume destination, and the ``.pi/roles/``
    ``.gitignore`` entry — and write *none* of them: ``<target>/.pi`` must
    not exist afterwards, and an injected seeder seam must be invoked zero
    times.

    FLAG (wording pin for the green step): the Pi steps' current
    placeholder lines (``   ↳ dry run: would write .pi/mcp.json`` and
    ``   ↳ dry run: would write .pi/extensions/guardrails.json``) are
    non-constraining and do not match the file's established dry-run style
    — every other dry_run branch reports
    ``   ↳ ⏭️  Dry-run: would {verb} {absolute path}`` (see
    ``_merge_gitignore_step``'s ``would create`` and
    ``_write_mcp_settings``'s ``would merge``). This class pins that style
    with absolute paths:

        ``   ↳ ⏭️  Dry-run: would write <target>/.pi/mcp.json``
        ``   ↳ ⏭️  Dry-run: would write <target>/.pi/extensions/guardrails.json``
        ``   ↳ ⏭️  Dry-run: would seed models.json into the sandbox-agent volume``

    The gitignore step's dry-run report must additionally carry the
    ``.pi/roles/`` entry; the current branch names only the file.
    Proposal: one ``↳`` line per entry, e.g.
    ``   ↳ ⏭️  Dry-run: would ensure .gitignore entry: .pi/roles/``
    (the assertion pins the entry string, not the line shape).

    Error path (FLAG — decision): the behaviour's Error clause says "a
    malformed existing file still fails under dry-run, per the existing
    validate-before-dry-run precedent". That precedent is
    ``.roo``-specific (``_write_mcp_settings``'s malformed
    ``.roo/mcp.json`` handling, pinned in
    ``tests/test_provision_mcp_merge.py``), so this class pins it for
    ``<target>/.pi/mcp.json`` — the file this behaviour owns: a
    pre-existing malformed ``.pi/mcp.json`` must raise
    ``ProvisionError`` naming the path under ``dry_run=True``, with the
    file's bytes untouched. The green step's dry-run branch must therefore
    validate the existing file, not just report.

    Expected red reasons:
    * the four report tests fail on their exact-line / entry assertions —
      the current placeholders use different casing, no emoji and a
      relative path; ``_seed_agent_volume`` has no dry-run branch (it
      invokes the seam and reports the ``Seeded`` success line); and the
      gitignore dry-run line does not carry ``.pi/roles/``;
    * the zero-invocation test fails because the current
      ``_seed_agent_volume`` invokes the seam exactly once even under
      dry-run;
    * the malformed-file test fails because ``_write_pi_mcp`` does not
      validate a pre-existing file, so the run completes without raising
      and the ``ProvisionError`` is never produced.
    Green-at-write: the writes-none test — ``_create_directories`` never
    creates ``.pi`` and both Pi placeholder branches already return before
    writing, so ``<target>/.pi`` is absent after a dry run today. It stays
    load-bearing: it fails the moment the green step's dry-run branches
    write anything.
    """

    AGENT_VOLUME = "sandbox-agent"
    ROLES_ENTRY = ".pi/roles/"

    def _would_write_line(self, relative):
        """The pinned dry-run line for a write step, in the file's
        established style with the absolute destination path."""
        return "   ↳ ⏭️  Dry-run: would write {}".format(
            self.target.resolve() / relative
        )

    def test_dry_run_report_names_the_pi_mcp_json_destination(self):
        self.provision(dry_run=True)

        self.assertIn(
            self._would_write_line(".pi/mcp.json"),
            self.output,
            "the dry-run report must name the absolute .pi/mcp.json "
            "destination in the file's dry-run style",
        )

    def test_dry_run_report_names_the_pi_guardrails_destination(self):
        self.provision(dry_run=True)

        self.assertIn(
            self._would_write_line(".pi/extensions/guardrails.json"),
            self.output,
            "the dry-run report must name the absolute "
            ".pi/extensions/guardrails.json destination in the "
            "file's dry-run style",
        )

    def test_dry_run_report_names_the_models_volume_destination(self):
        def seeder(volume, models_text):
            return (0, "", "")

        self.provision(dry_run=True, seed_models_json=seeder)

        self.assertIn(
            "   ↳ ⏭️  Dry-run: would seed models.json into the {} volume".format(
                self.AGENT_VOLUME
            ),
            self.output,
            "the dry-run report must name the models.json volume "
            "destination",
        )

    def test_dry_run_report_names_the_gitignore_roles_entry(self):
        self.provision(dry_run=True)

        self.assertIn(
            self.ROLES_ENTRY,
            self.output,
            "the dry-run report must name the .pi/roles/ .gitignore "
            "entry",
        )

    def test_dry_run_writes_nothing_under_dot_pi(self):
        self.provision(dry_run=True)

        self.assertFalse(
            (self.target / ".pi").exists(),
            "a dry run must not create <target>/.pi in any form — no "
            "mcp.json, no extensions/",
        )

    def test_dry_run_invokes_the_seeder_zero_times(self):
        calls = []

        def seeder(volume, models_text):
            calls.append((volume, models_text))
            return (0, "", "")

        self.provision(dry_run=True, seed_models_json=seeder)

        self.assertEqual(
            calls,
            [],
            "a dry run must not invoke the seeder seam at all",
        )

    def test_malformed_existing_pi_mcp_json_still_fails_under_dry_run(self):
        """Error clause, per the validate-before-dry-run precedent: a
        pre-existing malformed ``.pi/mcp.json`` must raise
        ``ProvisionError`` naming the path under ``dry_run=True``, and a
        dry run must not modify the file while reporting the fault."""
        path = self.target / ".pi" / "mcp.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json at all", encoding="utf-8")
        before = path.read_bytes()

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision(dry_run=True)

        self.assertIn(
            str(path.resolve()),
            str(ctx.exception),
            "ProvisionError must name the offending path: "
            "{}".format(ctx.exception),
        )
        self.assertEqual(
            path.read_bytes(),
            before,
            "A dry run must not modify the file while reporting the fault",
        )


if __name__ == "__main__":
    unittest.main()
