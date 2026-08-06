"""Tests for anvilkit.config - reading config.yaml and anvil.yaml.

Written before the implementation (TDD step 4).

Two distinct responsibilities, with a strict ownership boundary:

* ``config.yaml`` is owned by llama-swap. Anvil only reads it, to answer "which
  model is the coder?" and "what is its context window?". These tests are written
  to fail against the original ``grep -A50 ... | awk '{print $NF}'`` pipeline at
  ``anvil:329``, which broke if the model block moved, was reindented, or grew
  past 50 lines.
* ``anvil.yaml`` holds Anvil's own values - the profile ids and Anthropic model
  menu previously hardcoded at ``anvil:89`` and ``anvil:137``.
"""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import config  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"


class ConfigTestCase(unittest.TestCase):
    def write_yaml(self, content, name="sample.yaml"):
        return self.write_raw_yaml(textwrap.dedent(content), name=name)

    def write_raw_yaml(self, content, name="sample.yaml"):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / name
        path.write_text(content, encoding="utf-8")
        return path


MINIMAL_SWAP_CONFIG = """\
    port: 8080
    matrix:
      vars:
        generic: "vendor/generic-model"
        coder: "vendor/coder-model"
        nomic: "vendor/embed-model"
    models:
      "vendor/generic-model":
        cmd: >
          docker run --model vendor/generic-model --max-model-len 248320
      "vendor/coder-model":
        cmd: >
          docker run --model vendor/coder-model --max-model-len 262144
      "vendor/embed-model":
        cmd: >
          docker run --model vendor/embed-model --max-model-len 2048
    """


class TestReadRealConfigFixture(ConfigTestCase):
    """The captured production config.yaml must be understood correctly."""

    def setUp(self):
        self.models = config.read_models(FIXTURES / "golden_config.yaml")

    def test_resolves_coder_model_id(self):
        self.assertEqual(self.models.coder_id, "Qwen/Qwen3.6-35B-A3B-FP8")

    def test_resolves_coder_context_window(self):
        # The single source of truth for what was duplicated across 4 files.
        self.assertEqual(self.models.coder_context_window, 262144)

    def test_resolves_embedder_model_id(self):
        self.assertEqual(self.models.embedder_id, "nomic-ai/nomic-embed-text-v1.5")

    def test_resolves_gateway_port(self):
        self.assertEqual(self.models.gateway_port, 8080)


class TestCoderResolutionIsStructural(ConfigTestCase):
    """Immunity to the failure modes of the old grep -A50 pipeline."""

    def test_survives_models_being_reordered(self):
        path = self.write_yaml(
            """\
            matrix:
              vars:
                coder: "vendor/coder-model"
                nomic: "vendor/embed-model"
            models:
              "vendor/embed-model":
                cmd: >
                  docker run --max-model-len 2048
              "vendor/coder-model":
                cmd: >
                  docker run --max-model-len 262144
            """
        )

        self.assertEqual(config.read_models(path).coder_context_window, 262144)

    def test_survives_deeper_indentation(self):
        # grep '^  "Qwen/..."' anchored on exactly two spaces.
        path = self.write_yaml(
            """\
            matrix:
                vars:
                    coder: "vendor/coder-model"
                    nomic: "vendor/embed-model"
            models:
                "vendor/coder-model":
                    cmd: >
                        docker run --max-model-len 262144
                "vendor/embed-model":
                    cmd: >
                        docker run --max-model-len 2048
            """
        )

        self.assertEqual(config.read_models(path).coder_context_window, 262144)

    def test_survives_a_model_block_longer_than_fifty_lines(self):
        # The old pipeline used 'grep -A50', so anything past line 50 of the
        # model block was invisible to it.
        filler = "\n".join(
            "      flag_{}: value".format(index) for index in range(60)
        )
        # Assembled without dedent: the filler is already at final indentation.
        content = (
            "matrix:\n"
            "  vars:\n"
            '    coder: "vendor/coder-model"\n'
            '    nomic: "vendor/embed-model"\n'
            "models:\n"
            '  "vendor/coder-model":\n'
            "    extra:\n"
            + filler
            + "\n"
            "    cmd: >\n"
            "      docker run --max-model-len 262144\n"
            '  "vendor/embed-model":\n'
            "    cmd: >\n"
            "      docker run --max-model-len 2048\n"
        )
        path = self.write_raw_yaml(content)

        self.assertEqual(config.read_models(path).coder_context_window, 262144)

    def test_does_not_read_another_models_context_window(self):
        # The old pipeline's 'head -1' could pick up a neighbouring model's value.
        path = self.write_yaml(
            """\
            matrix:
              vars:
                coder: "vendor/coder-model"
                nomic: "vendor/embed-model"
            models:
              "vendor/decoy-model":
                cmd: >
                  docker run --max-model-len 999999
              "vendor/coder-model":
                cmd: >
                  docker run --max-model-len 262144
              "vendor/embed-model":
                cmd: >
                  docker run --max-model-len 2048
            """
        )

        self.assertEqual(config.read_models(path).coder_context_window, 262144)

    def test_accepts_equals_separated_flag_spelling(self):
        path = self.write_yaml(
            """\
            matrix:
              vars:
                coder: "vendor/coder-model"
                nomic: "vendor/embed-model"
            models:
              "vendor/coder-model":
                cmd: >
                  docker run --max-model-len=131072
              "vendor/embed-model":
                cmd: >
                  docker run --max-model-len 2048
            """
        )

        self.assertEqual(config.read_models(path).coder_context_window, 131072)

    def test_reads_max_model_len_when_not_the_last_flag(self):
        # The old 'awk {print $NF}' only worked because it was last on its line.
        path = self.write_yaml(
            """\
            matrix:
              vars:
                coder: "vendor/coder-model"
                nomic: "vendor/embed-model"
            models:
              "vendor/coder-model":
                cmd: >
                  docker run --max-model-len 262144 --gpu-memory-utilization 0.9
              "vendor/embed-model":
                cmd: >
                  docker run --max-model-len 2048
            """
        )

        self.assertEqual(config.read_models(path).coder_context_window, 262144)

    def test_falls_back_to_default_when_max_model_len_absent(self):
        path = self.write_yaml(
            """\
            matrix:
              vars:
                coder: "vendor/coder-model"
                nomic: "vendor/embed-model"
            models:
              "vendor/coder-model":
                cmd: >
                  docker run --gpu-memory-utilization 0.9
              "vendor/embed-model":
                cmd: >
                  docker run --max-model-len 2048
            """
        )

        self.assertEqual(
            config.read_models(path).coder_context_window,
            config.DEFAULT_CONTEXT_WINDOW,
        )


class TestConfigYamlErrors(ConfigTestCase):
    def test_missing_matrix_vars_coder_raises_explicit_error(self):
        # Must fail loudly rather than silently returning a wrong answer.
        path = self.write_yaml(
            """\
            matrix:
              vars:
                nomic: "vendor/embed-model"
            models: {}
            """
        )

        with self.assertRaises(config.ConfigError) as ctx:
            config.read_models(path)

        self.assertIn("coder", str(ctx.exception))

    def test_coder_referencing_an_undefined_model_raises(self):
        path = self.write_yaml(
            """\
            matrix:
              vars:
                coder: "vendor/absent-model"
                nomic: "vendor/embed-model"
            models:
              "vendor/embed-model":
                cmd: >
                  docker run --max-model-len 2048
            """
        )

        with self.assertRaises(config.ConfigError) as ctx:
            config.read_models(path)

        self.assertIn("vendor/absent-model", str(ctx.exception))

    def test_missing_file_raises_config_error(self):
        with self.assertRaises(config.ConfigError):
            config.read_models(Path("/nonexistent/config.yaml"))

    def test_gateway_port_defaults_when_absent(self):
        path = self.write_yaml(MINIMAL_SWAP_CONFIG)

        self.assertEqual(config.read_models(path).gateway_port, 8080)


class TestAnvilSettings(ConfigTestCase):
    """anvil.yaml holds only Anvil's own values."""

    def test_reads_committed_anvil_yaml(self):
        settings = config.read_settings(REPO_ROOT / "anvil.yaml")

        self.assertEqual(settings.local_profile_id, "4aj3zc43616")
        self.assertEqual(settings.anthropic_profile_id, "anthropic_profile")
        self.assertEqual(settings.default_anthropic_model, "claude-opus-5")

    def test_committed_anvil_yaml_offers_the_expected_model_lineup(self):
        settings = config.read_settings(REPO_ROOT / "anvil.yaml")

        ids = [model["id"] for model in settings.anthropic_models]
        self.assertEqual(
            ids,
            ["claude-fable-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"],
        )

    def test_every_offered_model_has_a_label(self):
        settings = config.read_settings(REPO_ROOT / "anvil.yaml")

        for model in settings.anthropic_models:
            self.assertTrue(model.get("label"), model)

    def test_default_model_must_be_one_of_the_offered_models(self):
        settings = config.read_settings(REPO_ROOT / "anvil.yaml")

        ids = [model["id"] for model in settings.anthropic_models]
        self.assertIn(settings.default_anthropic_model, ids)

    def test_missing_required_key_is_rejected(self):
        path = self.write_yaml(
            """\
            version: 1
            zoo_code:
              anthropic_profile_id: "anthropic_profile"
            """
        )

        with self.assertRaises(config.ConfigError) as ctx:
            config.read_settings(path)

        self.assertIn("local_profile_id", str(ctx.exception))

    def test_unknown_top_level_key_is_rejected(self):
        path = self.write_yaml(
            """\
            version: 1
            gateway:
              default_port: 8000
            zoo_code:
              local_profile_id: "abc"
              anthropic_profile_id: "anthropic_profile"
              default_anthropic_model: "claude-opus-5"
              anthropic_models:
                - id: claude-opus-5
                  label: balanced
            surprise: true
            """
        )

        with self.assertRaises(config.ConfigError) as ctx:
            config.read_settings(path)

        self.assertIn("surprise", str(ctx.exception))

    def test_local_overrides_take_precedence(self):
        base = self.write_yaml(
            """\
            version: 1
            gateway:
              default_port: 8000
            zoo_code:
              local_profile_id: "base-id"
              anthropic_profile_id: "anthropic_profile"
              default_anthropic_model: "claude-opus-5"
              anthropic_models:
                - id: claude-opus-5
                  label: balanced
            """,
            name="anvil.yaml",
        )
        local = base.parent / "anvil.local.yaml"
        local.write_text(
            textwrap.dedent(
                """\
                gateway:
                  default_port: 9999
                """
            ),
            encoding="utf-8",
        )

        settings = config.read_settings(base, local_path=local)

        self.assertEqual(settings.default_port, 9999)
        # Untouched keys survive the merge.
        self.assertEqual(settings.local_profile_id, "base-id")

    def test_absent_local_overrides_are_not_an_error(self):
        base = self.write_yaml(
            """\
            version: 1
            gateway:
              default_port: 8000
            zoo_code:
              local_profile_id: "base-id"
              anthropic_profile_id: "anthropic_profile"
              default_anthropic_model: "claude-opus-5"
              anthropic_models:
                - id: claude-opus-5
                  label: balanced
            """,
            name="anvil.yaml",
        )

        settings = config.read_settings(base, local_path=base.parent / "absent.yaml")

        self.assertEqual(settings.default_port, 8000)


class TestPortPrecedence(ConfigTestCase):
    """CLI flag > .env > anvil.yaml default. Existing installs must not break."""

    def test_env_value_beats_anvil_yaml_default(self):
        resolved = config.resolve_port(
            flag_value=None, env_value="8123", default_port=8000
        )

        self.assertEqual(resolved, 8123)

    def test_flag_beats_env_value(self):
        resolved = config.resolve_port(
            flag_value=8500, env_value="8123", default_port=8000
        )

        self.assertEqual(resolved, 8500)

    def test_default_used_when_nothing_else_supplied(self):
        resolved = config.resolve_port(
            flag_value=None, env_value=None, default_port=8000
        )

        self.assertEqual(resolved, 8000)

    def test_blank_env_value_is_ignored(self):
        resolved = config.resolve_port(flag_value=None, env_value="", default_port=8000)

        self.assertEqual(resolved, 8000)

    def test_non_numeric_env_value_is_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.resolve_port(flag_value=None, env_value="not-a-port", default_port=8000)


if __name__ == "__main__":
    unittest.main()
