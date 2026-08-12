"""Tests for devcontainer provisioning (templates/devcontainer).

Written before the implementation.

The devcontainer is a scaffold that setup-repo copies into the target
repository.  It is deliberately validated **before** anything is written
and skipped when the target already carries its own .devcontainer — overwriting
a developer's own container config would be destructive.
"""

import json
import shutil
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


class DevcontainerProvisionCase(unittest.TestCase):
    """Base class: a throwaway target repo and the template directory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = Path(self._tmp.name) / "repo"
        self.target.mkdir()
        self.template_root = Path(self._tmp.name) / "templates"
        self.template_root.mkdir()
        # Create the devcontainer template tree inside the template root.
        self.devcontainer_template = self.template_root / "devcontainer"
        self.devcontainer_template.mkdir()
        (self.devcontainer_template / "Dockerfile").write_text(
            "FROM python:3.11-slim\n", encoding="utf-8"
        )
        (self.devcontainer_template / "devcontainer.json").write_text(
            json.dumps({"name": "Test"}), encoding="utf-8"
        )
        # Also create the other templates the provisioner needs.
        self._make_mini_templates()
        self.messages = []

    def tearDown(self):
        self._tmp.cleanup()

    def _make_mini_templates(self):
        """Create minimal required templates so setup_repo can validate()."""
        for name in (
            "zoo-code-settings.json.template",
            "mcp.json.template",
            "extensions.json.template",
            "update_roo_rules.md",
            ".gitignore.template",
        ):
            (self.template_root / name).write_text("{}\n", encoding="utf-8")
        roo = self.template_root / "roo_template"
        roo.mkdir()
        (roo / ".roomodes").write_text("# dummy\n", encoding="utf-8")
        (roo / "commands").mkdir()
        (roo / "rules").mkdir()

    def provision(self, **kwargs):
        params = dict(
            target=self.target,
            repo_plan=plan(),
            templates_dir=self.template_root,
            echo=self.messages.append,
        )
        params.update(kwargs)
        return provision.setup_repo(**params)


class DevcontainerSkipTests(DevcontainerProvisionCase):
    """Provisioning skips the devcontainer when the target already has one."""

    def test_skips_when_target_already_has_devcontainer(self):
        existing = self.target / ".devcontainer"
        existing.mkdir()
        (existing / "Dockerfile").write_text("EXISTING", encoding="utf-8")

        self.provision()

        self.assertEqual(
            (self.target / ".devcontainer" / "Dockerfile").read_text(
                encoding="utf-8"
            ),
            "EXISTING",
        )

    def test_skips_modifying_any_existing_files(self):
        existing = self.target / ".devcontainer"
        existing.mkdir()
        (existing / "Dockerfile").write_text("MY_CUSTOM_DOCKERFILE", encoding="utf-8")
        (existing / "devcontainer.json").write_text(
            json.dumps({"name": "my-dev"}), encoding="utf-8"
        )

        self.provision()

        self.assertEqual(
            (self.target / ".devcontainer" / "Dockerfile").read_text(
                encoding="utf-8"
            ),
            "MY_CUSTOM_DOCKERFILE",
        )
        content = json.loads(
            (self.target / ".devcontainer" / "devcontainer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(content["name"], "my-dev")

    def test_skips_when_devcontainer_is_a_file_not_directory(self):
        # Edge case: someone has .devcontainer as a file, not a directory.
        dc = self.target / ".devcontainer"
        dc.write_text("not a directory", encoding="utf-8")

        self.provision()

        self.assertTrue(dc.is_file())

    def test_dry_run_skips_existing_devcontainer(self):
        existing = self.target / ".devcontainer"
        existing.mkdir()

        self.provision(dry_run=True)

        self.assertFalse((self.target / ".devcontainer" / "Dockerfile").exists())


class DevcontainerDeployTests(DevcontainerProvisionCase):
    """When the target does NOT have a devcontainer, it gets copied."""

    def test_copies_devcontainer_dockerfile(self):
        self.provision()

        dc = self.target / ".devcontainer"
        self.assertTrue(dc.is_dir())
        self.assertTrue((dc / "Dockerfile").is_file())

    def test_copies_devcontainer_json(self):
        self.provision()

        dc = self.target / ".devcontainer"
        content = json.loads((dc / "devcontainer.json").read_text(encoding="utf-8"))
        self.assertEqual(content["name"], "Test")

    def test_dockerfile_content_matches_template(self):
        self.provision()

        dc = self.target / ".devcontainer"
        actual = (dc / "Dockerfile").read_text(encoding="utf-8")
        expected = (
            self.devcontainer_template / "Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertEqual(actual, expected)

    def test_devcontainer_json_content_matches_template(self):
        self.provision()

        dc = self.target / ".devcontainer"
        actual = json.loads(
            (dc / "devcontainer.json").read_text(encoding="utf-8")
        )
        expected = json.loads(
            (self.devcontainer_template / "devcontainer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(actual, expected)

    def test_dry_run_does_not_create_devcontainer(self):
        self.provision(dry_run=True)

        self.assertFalse((self.target / ".devcontainer").exists())


class DevcontainerMissingTemplateTests(DevcontainerProvisionCase):
    """Provisioning fails validation when the devcontainer template is missing."""

    def test_missing_devcontainer_template_directory_raises(self):
        # Remove the devcontainer directory entirely.
        shutil.rmtree(str(self.devcontainer_template))

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision()

        self.assertIn("devcontainer", str(ctx.exception).lower())

    def test_missing_devcontainer_error_names_the_path(self):
        shutil.rmtree(str(self.devcontainer_template))

        with self.assertRaises(provision.ProvisionError) as ctx:
            self.provision()

        self.assertIn(str(self.template_root / "devcontainer"), str(ctx.exception))

    def test_nothing_written_when_devcontainer_template_is_missing(self):
        shutil.rmtree(str(self.devcontainer_template))

        with self.assertRaises(provision.ProvisionError):
            self.provision()

        self.assertEqual(list(self.target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
