"""Tests for the real config.yaml — model blocks that Anvil parses.

Written before the implementation (TDD step 1, Behaviour 1).

These tests load the *actual* config.yaml with ``yamlio.load()``, so the folded
scalar (YAML logical single-line value) is what we assert on — not raw file
text.  This is where the "missing space before --" bug hides: two flags get
silently concatenated in the folded value.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import yamlio  # noqa: E402


CONFIG_YAML = REPO_ROOT / "config.yaml"


class TestQwen38CoderModel(unittest.TestCase):
    """Behaviour 1: the Qwen3.8-27B-FP8 model block exists and is correct."""

    def _load_config(self):
        """Load config.yaml via yamlio.load() and return the ``models`` dict."""
        data = yamlio.load(CONFIG_YAML)
        self.assertIn("models", data, "config.yaml must contain a 'models' key")
        return data["models"]

    def test_model_key_exists(self):
        """The models dict must contain the key 'Qwen/Qwen3.8-27B-FP8'."""
        models = self._load_config()
        self.assertIn(
            "Qwen/Qwen3.8-27B-FP8",
            models,
            "models dict must contain key 'Qwen/Qwen3.8-27B-FP8'",
        )

    def test_cmd_contains_required_tokens(self):
        """The folded ``cmd`` value must contain all required flag tokens."""
        models = self._load_config()
        model = models["Qwen/Qwen3.8-27B-FP8"]
        cmd = model.get("cmd", "")
        self.assertIsInstance(cmd, str, "cmd must be a string (the YAML folded value)")

        required_tokens = [
            "--model Qwen/Qwen3.8-27B-FP8",
            "--tensor-parallel-size 2",
            "--max-model-len 262144",
            "--kv-cache-dtype fp8",
            "--reasoning-parser qwen3",
            "--enable-auto-tool-choice",
            "--tool-call-parser qwen3_coder",
        ]
        for token in required_tokens:
            self.assertIn(
                token,
                cmd,
                "cmd must contain token {!r} (folded value does not)".format(token),
            )

    def test_model_type_and_check_endpoint(self):
        """type must be 'proxy' and checkEndpoint must be '/v1/models'."""
        models = self._load_config()
        model = models["Qwen/Qwen3.8-27B-FP8"]
        self.assertEqual(
            model.get("type"),
            "proxy",
            "model type must be 'proxy'",
        )
        self.assertEqual(
            model.get("checkEndpoint"),
            "/v1/models",
            "checkEndpoint must be '/v1/models'",
        )

    def test_matrix_vars_coder_points_to_new_model(self):
        """matrix.vars.coder must equal 'Qwen/Qwen3.8-27B-FP8' and config.read_models() agrees."""
        from anvilkit.config import read_models  # noqa: E402

        data = yamlio.load(CONFIG_YAML)
        coder_id = (data.get("matrix") or {}).get("vars", {}).get("coder")
        self.assertEqual(coder_id, "Qwen/Qwen3.8-27B-FP8")

        # Also verify read_models() returns the same coder_id and context_window
        topology = read_models(CONFIG_YAML)
        self.assertEqual(topology.coder_id, "Qwen/Qwen3.8-27B-FP8")
        self.assertEqual(topology.coder_context_window, 262144)

        # matrix.vars.generic and .nomic must be untouched
        self.assertEqual(
            (data.get("matrix") or {}).get("vars", {}).get("generic"),
            "lovedheart/Qwen3.5-9B-FP8",
        )
        self.assertEqual(
            (data.get("matrix") or {}).get("vars", {}).get("nomic"),
            "nomic-ai/nomic-embed-text-v1.5",
        )

    def test_preload_names_new_model_excludes_old(self):
        """hooks.on_startup.preload contains Qwen3.8-27B-FP8 and must NOT contain Qwen3.6."""
        data = yamlio.load(CONFIG_YAML)
        preload = (data.get("hooks") or {}).get("on_startup", {}).get("preload", [])

        self.assertIn(
            "Qwen/Qwen3.8-27B-FP8",
            preload,
            "preload must include the new coder model",
        )
        self.assertIn(
            "nomic-ai/nomic-embed-text-v1.5",
            preload,
            "preload must still include the embedder",
        )
        self.assertNotIn(
            "Qwen/Qwen3.6-35B-A3B-FP8",
            preload,
            "preload must NOT include the retired coder",
        )

        # Every preloaded id must be a key in models
        models = data.get("models", {})
        for model_id in preload:
            self.assertIn(
                model_id,
                models,
                "preloaded id {!r} must be a key in models".format(model_id),
            )

    def test_old_coder_block_preserved(self):
        """The Qwen3.6-35B-A3B-FP8 model entry must still exist with key flags intact."""
        models = self._load_config()

        self.assertIn(
            "Qwen/Qwen3.6-35B-A3B-FP8",
            models,
            "The old coder model must still be in models section",
        )

        old_model = models["Qwen/Qwen3.6-35B-A3B-FP8"]
        cmd = old_model.get("cmd", "")
        self.assertIn("--tensor-parallel-size 2", cmd)
        self.assertIn("--max-model-len 262144", cmd)
        self.assertIn("--disable-custom-all-reduce", cmd)
        self.assertEqual(old_model.get("type"), "proxy")


class TestQwen38BatchModel(unittest.TestCase):
    """Second-setup Behaviour 1: the Qwen/Qwen3.8-27B-FP8-batch block exists and is well-formed.

    Written before the implementation (TDD step 1, plans/qwen38-concurrency-second-setup.md).
    Loads the real config.yaml via yamlio.load() and asserts on parsed values only.
    """

    MODEL_ID = "Qwen/Qwen3.8-27B-FP8-batch"

    def _load_config(self):
        """Load config.yaml via yamlio.load() and return the ``models`` dict."""
        data = yamlio.load(CONFIG_YAML)
        self.assertIn("models", data, "config.yaml must contain a 'models' key")
        return data["models"]

    def _load_batch_block(self):
        """Return the new model block, failing with a message naming the key."""
        models = self._load_config()
        self.assertIn(
            self.MODEL_ID,
            models,
            "models dict must contain key {!r} (second vLLM setup is missing)".format(self.MODEL_ID),
        )
        return models[self.MODEL_ID]

    def test_model_key_exists(self):
        """The models dict must contain the key 'Qwen/Qwen3.8-27B-FP8-batch'."""
        self._load_batch_block()

    def test_model_key_distinct_from_existing_keys(self):
        """The new id must differ from all three existing model keys, which must survive."""
        models = self._load_config()
        self.assertIn(
            self.MODEL_ID,
            models,
            "models dict must contain key {!r}".format(self.MODEL_ID),
        )
        for existing in (
            "Qwen/Qwen3.8-27B-FP8",
            "Qwen/Qwen3.6-35B-A3B-FP8",
            "lovedheart/Qwen3.5-9B-FP8",
        ):
            self.assertIn(
                existing,
                models,
                "existing model key {!r} must still be present in models".format(existing),
            )
            self.assertNotEqual(
                self.MODEL_ID,
                existing,
                "new model id {!r} must differ from existing key {!r}".format(self.MODEL_ID, existing),
            )

    def test_block_is_mapping(self):
        """The new block must parse as a mapping, not a scalar or list."""
        block = self._load_batch_block()
        self.assertIsInstance(
            block,
            dict,
            "models[ {!r} ] must be a mapping, got {}".format(self.MODEL_ID, type(block).__name__),
        )

    def test_cmd_is_string(self):
        """``cmd`` must parse as a str (the YAML folded value, one logical line)."""
        block = self._load_batch_block()
        cmd = block.get("cmd")
        self.assertIsInstance(
            cmd,
            str,
            "cmd in models[ {!r} ] must be a string, got {}".format(self.MODEL_ID, type(cmd).__name__),
        )

    def test_model_type_and_check_endpoint(self):
        """type must be 'proxy' and checkEndpoint must be '/v1/models'."""
        block = self._load_batch_block()
        self.assertEqual(
            block.get("type"),
            "proxy",
            "type in models[ {!r} ] must be 'proxy', got {!r}".format(self.MODEL_ID, block.get("type")),
        )
        self.assertEqual(
            block.get("checkEndpoint"),
            "/v1/models",
            "checkEndpoint in models[ {!r} ] must be '/v1/models', got {!r}".format(
                self.MODEL_ID, block.get("checkEndpoint")
            ),
        )

    def test_proxy_points_at_vllm_container(self):
        """proxy must be 'http://vllm-${PORT}:${PORT}'."""
        block = self._load_batch_block()
        self.assertEqual(
            block.get("proxy"),
            "http://vllm-${PORT}:${PORT}",
            "proxy in models[ {!r} ] must be 'http://vllm-${{PORT}}:{{PORT}}', got {!r}".format(
                self.MODEL_ID, block.get("proxy")
            ),
        )

    def test_cmd_stop_stops_vllm_container(self):
        """cmdStop must be 'docker stop vllm-${PORT} || true'."""
        block = self._load_batch_block()
        self.assertEqual(
            block.get("cmdStop"),
            "docker stop vllm-${PORT} || true",
            "cmdStop in models[ {!r} ] must be 'docker stop vllm-${{PORT}} || true', got {!r}".format(
                self.MODEL_ID, block.get("cmdStop")
            ),
        )

    # -- Behaviour 2: the batching flags are the ones under test -----------------
    # All checks below are token-level on the folded ``cmd`` (whitespace-split).
    # Token comparison is the only airtight form: "--max-num-seqs 1" is a substring
    # prefix of "--max-num-seqs 16", so substring asserts could pass or fail by
    # accident.

    def _cmd_tokens(self):
        """Return the folded ``cmd`` of the batch block split into tokens."""
        block = self._load_batch_block()
        cmd = block.get("cmd")
        self.assertIsInstance(
            cmd,
            str,
            "cmd in models[ {!r} ] must be a string, got {}".format(self.MODEL_ID, type(cmd).__name__),
        )
        return cmd.split()

    @staticmethod
    def _flag_values(tokens, flag):
        """Return the value token following each occurrence of ``flag`` (or None if it dangles)."""
        return [
            tokens[i + 1] if i + 1 < len(tokens) else None
            for i, tok in enumerate(tokens)
            if tok == flag
        ]

    def test_cmd_has_max_num_seqs_64(self):
        """cmd must carry the token pair ['--max-num-seqs', '64'] — the variable under test."""
        tokens = self._cmd_tokens()
        values = self._flag_values(tokens, "--max-num-seqs")
        self.assertIn(
            "64",
            values,
            "cmd must carry the token pair ['--max-num-seqs', '64']; "
            "offending tokens found: {!r}".format(values),
        )

    def test_cmd_has_max_num_batched_tokens_16384(self):
        """cmd must carry the token pair ['--max-num-batched-tokens', '16384']."""
        tokens = self._cmd_tokens()
        values = self._flag_values(tokens, "--max-num-batched-tokens")
        self.assertIn(
            "16384",
            values,
            "cmd must carry the token pair ['--max-num-batched-tokens', '16384']; "
            "offending tokens found: {!r}".format(values),
        )

    def test_cmd_does_not_have_max_num_seqs_1(self):
        """cmd must NOT carry the token pair ['--max-num-seqs', '1'] — the whole point of the block."""
        tokens = self._cmd_tokens()
        values = self._flag_values(tokens, "--max-num-seqs")
        self.assertNotIn(
            "1",
            values,
            "cmd must not carry the token pair ['--max-num-seqs', '1']; "
            "offending tokens found: {!r}".format(values),
        )

    def test_cmd_has_max_num_seqs_exactly_once(self):
        """cmd must contain the flag '--max-num-seqs' exactly once (duplicates are last-wins in vLLM)."""
        tokens = self._cmd_tokens()
        count = tokens.count("--max-num-seqs")
        self.assertEqual(
            count,
            1,
            "cmd must contain '--max-num-seqs' exactly once, found {} occurrence(s): {!r}".format(
                count,
                [tok for tok in tokens if tok == "--max-num-seqs"],
            ),
        )
