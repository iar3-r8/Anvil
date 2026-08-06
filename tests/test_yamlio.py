"""Tests for anvilkit.yamlio - the only module permitted to import ``yaml``.

Written before the implementation (TDD step 2).

Scope notes:

* Anvil *reads* YAML and never writes it. ``config.yaml`` is owned by llama-swap
  and stays hand-authored, so there is no dump surface to test.
* ``pyyaml`` availability is not tested. The managed venv guarantees it, so a
  fallback path would be untestable dead code.

The contract is therefore narrow:

* loading is always safe - a YAML file must never execute code
* errors are typed and name the offending path, never a bare traceback
* the shapes actually present in config.yaml load correctly, including the
  folded ``cmd: >`` scalars used for the long vLLM command lines
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"


class YamlioTestCase(unittest.TestCase):
    def write_temp(self, content):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = Path(tmp_dir.name) / "sample.yaml"
        path.write_text(content, encoding="utf-8")
        return path


class TestLoadSupportedShapes(YamlioTestCase):
    def test_loads_scalars_with_native_types(self):
        path = self.write_temp(
            "port: 8000\n"
            "host: 0.0.0.0\n"
            "log_level: debug\n"
            "enabled: true\n"
            "ratio: 0.9\n"
        )

        data = yamlio.load(path)

        self.assertEqual(data["port"], 8000)
        self.assertEqual(data["host"], "0.0.0.0")
        self.assertEqual(data["log_level"], "debug")
        self.assertIs(data["enabled"], True)
        self.assertAlmostEqual(data["ratio"], 0.9)

    def test_loads_block_and_inline_lists(self):
        path = self.write_temp(
            "preload:\n"
            "  - alpha\n"
            "  - beta\n"
            "gpus: [LLM_DEVICE_ID_1, LLM_DEVICE_ID_2]\n"
        )

        data = yamlio.load(path)

        self.assertEqual(data["preload"], ["alpha", "beta"])
        self.assertEqual(data["gpus"], ["LLM_DEVICE_ID_1", "LLM_DEVICE_ID_2"])

    def test_loads_nested_mappings_with_slash_bearing_keys(self):
        # Model ids such as "Qwen/Qwen3.6-35B-A3B-FP8" are used as mapping keys.
        path = self.write_temp(
            "models:\n"
            '  "Qwen/Qwen3.6-35B-A3B-FP8":\n'
            "    checkEndpoint: /v1/models\n"
            "    type: proxy\n"
        )

        model = yamlio.load(path)["models"]["Qwen/Qwen3.6-35B-A3B-FP8"]

        self.assertEqual(model["checkEndpoint"], "/v1/models")
        self.assertEqual(model["type"], "proxy")

    def test_folded_scalar_becomes_one_logical_line(self):
        # config.yaml uses 'cmd: >' for the long docker run invocations.
        path = self.write_temp(
            "cmd: >\n"
            "  docker run --rm --runtime=nvidia\n"
            "  --model Qwen/Qwen3.6-35B-A3B-FP8\n"
            "  --max-model-len 262144\n"
        )

        cmd = yamlio.load(path)["cmd"]

        self.assertIn("docker run --rm --runtime=nvidia", cmd)
        self.assertIn("--max-model-len 262144", cmd)
        self.assertNotIn("\n", cmd.strip())

    def test_loads_the_real_config_fixture(self):
        data = yamlio.load(FIXTURES / "golden_config.yaml")

        self.assertEqual(data["port"], 8080)
        self.assertEqual(data["matrix"]["vars"]["coder"], "Qwen/Qwen3.6-35B-A3B-FP8")
        self.assertIn("Qwen/Qwen3.6-35B-A3B-FP8", data["models"])

    def test_loads_from_string(self):
        self.assertEqual(yamlio.loads("port: 8000\n"), {"port": 8000})


class TestLoadSafety(YamlioTestCase):
    def test_refuses_to_construct_arbitrary_python_objects(self):
        # The decisive safety property: safe_load, never load.
        path = self.write_temp("danger: !!python/object/apply:os.system ['echo pwned']\n")

        with self.assertRaises(yamlio.YamlError):
            yamlio.load(path)

    def test_refuses_python_object_tags_from_string_input(self):
        with self.assertRaises(yamlio.YamlError):
            yamlio.loads("danger: !!python/object/apply:os.system ['echo pwned']\n")


class TestLoadErrors(YamlioTestCase):
    def test_missing_file_raises_typed_error_naming_the_path(self):
        missing = REPO_ROOT / "definitely" / "not" / "here.yaml"

        with self.assertRaises(yamlio.YamlError) as ctx:
            yamlio.load(missing)

        self.assertIn("here.yaml", str(ctx.exception))

    def test_malformed_yaml_raises_typed_error_naming_the_path(self):
        path = self.write_temp("this: [unclosed\n  bracket: yes\n")

        with self.assertRaises(yamlio.YamlError) as ctx:
            yamlio.load(path)

        self.assertIn(path.name, str(ctx.exception))

    def test_non_mapping_document_is_rejected(self):
        # Every config file Anvil reads is a mapping at the top level.
        path = self.write_temp("- one\n- two\n")

        with self.assertRaises(yamlio.YamlError):
            yamlio.load(path)

    def test_empty_file_returns_empty_mapping_not_none(self):
        self.assertEqual(yamlio.load(self.write_temp("")), {})

    def test_comments_only_file_returns_empty_mapping(self):
        self.assertEqual(yamlio.load(self.write_temp("# nothing here\n")), {})

    def test_yaml_error_is_an_oserror_free_custom_exception(self):
        # Callers should be able to catch one type for every failure mode.
        self.assertTrue(issubclass(yamlio.YamlError, Exception))


class TestPublicSurfaceIsLoadOnly(unittest.TestCase):
    def test_module_exposes_no_dump_function(self):
        # Anvil must never write YAML; config.yaml belongs to llama-swap.
        for forbidden in ("dump", "dumps", "safe_dump", "write"):
            self.assertFalse(
                hasattr(yamlio, forbidden),
                "yamlio must not expose {!r}: Anvil never writes YAML".format(forbidden),
            )


if __name__ == "__main__":
    unittest.main()
