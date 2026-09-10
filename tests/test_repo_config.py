"""Tests for the real config.yaml — model blocks that Anvil parses.

Written before the implementation (TDD step 1, Behaviour 1).

These tests load the *actual* config.yaml with ``yamlio.load()``, so the folded
scalar (YAML logical single-line value) is what we assert on — not raw file
text.  This is where the "missing space before --" bug hides: two flags get
silently concatenated in the folded value.

2026-09-10: the Qwen3.8 A/B pair is retired. The single coder block
``Qwen/Qwen3.8-27B-FP8`` now runs with continuous batching
(``--max-num-seqs 64``), which was stress-tested and measured as much more
efficient than the old ``--max-num-seqs 1`` control
(plans/qwen38-concurrency-second-setup.md, round-three decision). The isolated
``-batch`` block and its ``--served-model-name`` bridge are gone; the
isolation and control-pinning behaviours below them no longer apply.
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
    """The Qwen3.8-27B-FP8 model block exists, is batched, and is the coder."""

    MODEL_ID = "Qwen/Qwen3.8-27B-FP8"

    def _load_config(self):
        """Load config.yaml via yamlio.load() and return the ``models`` dict."""
        data = yamlio.load(CONFIG_YAML)
        self.assertIn("models", data, "config.yaml must contain a 'models' key")
        return data["models"]

    def _load_coder_block(self):
        """Return the coder model block, failing with a message naming the key."""
        models = self._load_config()
        self.assertIn(
            self.MODEL_ID,
            models,
            "models dict must contain key {!r}".format(self.MODEL_ID),
        )
        return models[self.MODEL_ID]

    def _cmd_tokens(self):
        """Return the folded ``cmd`` of the coder block split into tokens.

        Token-level checks are the only airtight form: "--max-num-seqs 1" is a
        substring prefix of "--max-num-seqs 16" and of "--max-num-seqs 64", so
        substring asserts could pass or fail by accident.
        """
        block = self._load_coder_block()
        cmd = block.get("cmd")
        self.assertIsInstance(
            cmd,
            str,
            "cmd in models[ {!r} ] must be a string, got {}".format(
                self.MODEL_ID, type(cmd).__name__
            ),
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

    def test_model_key_exists(self):
        """The models dict must contain the key 'Qwen/Qwen3.8-27B-FP8'."""
        self._load_coder_block()

    def test_batch_variant_block_is_retired(self):
        """The old A/B variant id must be gone from models.

        The -batch block existed only to compare --max-num-seqs 64 against the
        --max-num-seqs 1 control (plans/qwen38-concurrency-second-setup.md).
        That comparison is over: the batched scheduler won and now sits on the
        plain id, so a resurrected -batch key would be dead config.
        """
        models = self._load_config()
        self.assertNotIn(
            "Qwen/Qwen3.8-27B-FP8-batch",
            models,
            "models dict must not contain key 'Qwen/Qwen3.8-27B-FP8-batch': the "
            "A/B pair is retired and the batched scheduler now runs on the plain "
            "id (plan round-three decision)",
        )

    def test_cmd_contains_required_tokens(self):
        """The folded ``cmd`` value must contain all required flag tokens."""
        cmd = self._load_coder_block().get("cmd", "")
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
        model = self._load_coder_block()
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

    def test_no_served_model_name_bridge(self):
        """The coder cmd must not carry --served-model-name.

        The bridge existed because the -batch gateway id differed from the
        weights path. With one block whose models key equals the Hugging Face
        path, vLLM's default served name is already correct; a stray bridge
        would be the A/B pair half-retired.
        """
        tokens = self._cmd_tokens()
        self.assertNotIn(
            "--served-model-name",
            tokens,
            "cmd must not carry '--served-model-name': the models key equals the "
            "weights path, so vLLM's default served name is already correct",
        )

    # -- The batched scheduler flags -------------------------------------------

    def test_cmd_has_max_num_seqs_64_exactly_once(self):
        """cmd must carry the token pair ['--max-num-seqs', '64'] exactly once.

        This is the load-bearing invariant: the batched scheduler (stress-tested
        and measured as much more efficient than --max-num-seqs 1) is what makes
        this the production coder. Drift back to 1 silently reverts the A/B
        result.
        """
        tokens = self._cmd_tokens()
        count = tokens.count("--max-num-seqs")
        self.assertEqual(
            count,
            1,
            "cmd must contain '--max-num-seqs' exactly once, found {} "
            "occurrence(s): {!r}".format(
                count,
                [tok for tok in tokens if tok == "--max-num-seqs"],
            ),
        )
        values = self._flag_values(tokens, "--max-num-seqs")
        self.assertEqual(
            values,
            ["64"],
            "cmd must carry the token pair ['--max-num-seqs', '64'] (the "
            "batched scheduler); value token(s) found: {!r}".format(values),
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

    def test_cmd_model_is_weights_path(self):
        """cmd must carry exactly ['--model', <Hugging Face path>] once."""
        tokens = self._cmd_tokens()
        values = self._flag_values(tokens, "--model")
        self.assertEqual(
            values,
            [self.MODEL_ID],
            "cmd must carry exactly ['--model', {!r}]; --model value token(s) "
            "found: {!r}".format(self.MODEL_ID, values),
        )

    def test_proxy_points_at_vllm_container(self):
        """proxy must be 'http://vllm-${PORT}:${PORT}'."""
        block = self._load_coder_block()
        self.assertEqual(
            block.get("proxy"),
            "http://vllm-${PORT}:${PORT}",
            "proxy in models[ {!r} ] must be 'http://vllm-${{PORT}}:{{PORT}}', got {!r}".format(
                self.MODEL_ID, block.get("proxy")
            ),
        )

    def test_cmd_stop_stops_vllm_container(self):
        """cmdStop must be 'docker stop vllm-${PORT} || true'."""
        block = self._load_coder_block()
        self.assertEqual(
            block.get("cmdStop"),
            "docker stop vllm-${PORT} || true",
            "cmdStop in models[ {!r} ] must be 'docker stop vllm-${{PORT}} || true', got {!r}".format(
                self.MODEL_ID, block.get("cmdStop")
            ),
        )

    # -- The gateway concurrency cap --------------------------------------------
    # llama-swap caps in-flight requests per model at an internal default of 10;
    # concurrencyLimit "any number greater than 0 will override the internal
    # default value of 10" and requests beyond the limit receive HTTP 429
    # (doc/external/llama-swap/configuration-reference.md). The stress ramp
    # doubles (1, 2, 4, 8, 16, 32, ...), so without an explicit cap every level
    # above 10 is refused by the gateway before vLLM sees it.

    _GATEWAY_CAP_EXPLANATION = (
        "llama-swap would then return HTTP 429 Too Many Requests above the cap, and the "
        "stress report would measure the gateway rather than vLLM (anvilkit.stress "
        "concurrency_levels() ramps 1, 2, 4, 8, 16, 32, ...)"
    )

    @classmethod
    def _concurrency_limit_of(cls, block, model_id):
        """Return block['concurrencyLimit'] or None if absent or not a true int.

        ``bool`` is a subclass of ``int`` in Python, so it is rejected explicitly:
        ``true``/``false`` are not valid gateway caps.
        """
        if not isinstance(block, dict):
            return None
        value = block.get("concurrencyLimit")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    def test_coder_block_has_concurrency_limit_at_least_64(self):
        """The coder block must carry concurrencyLimit as a true int >= 64.

        With no limit greater than 0, llama-swap falls back to its internal
        default of 10 and the gateway becomes the binding constraint on the
        batched scheduler.
        """
        block = self._load_coder_block()
        value = self._concurrency_limit_of(block, self.MODEL_ID)
        self.assertIsNotNone(
            value,
            "concurrencyLimit is absent or not a true int in models[ {!r} ] (got {!r}); "
            "with no limit greater than 0, llama-swap falls back to its internal "
            "default of 10 and {}".format(
                self.MODEL_ID, block.get("concurrencyLimit"), self._GATEWAY_CAP_EXPLANATION
            ),
        )
        self.assertGreaterEqual(
            value,
            64,
            "concurrencyLimit in models[ {!r} ] is {}; the stress ramp doubles to 16 "
            "and 32, so a cap below 64 makes {} and the report would reflect the "
            "gateway, not the engine".format(
                self.MODEL_ID, value, self._GATEWAY_CAP_EXPLANATION
            ),
        )

    # -- The coder wiring ---------------------------------------------------------

    def test_matrix_vars_coder_points_to_batched_model(self):
        """matrix.vars.coder must equal 'Qwen/Qwen3.8-27B-FP8' and config.read_models() agrees."""
        from anvilkit.config import read_models  # noqa: E402

        data = yamlio.load(CONFIG_YAML)
        coder_id = (data.get("matrix") or {}).get("vars", {}).get("coder")
        self.assertEqual(coder_id, self.MODEL_ID)

        # Also verify read_models() returns the same coder_id and context_window
        topology = read_models(CONFIG_YAML)
        self.assertEqual(topology.coder_id, self.MODEL_ID)
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

    def test_preload_names_batched_model_excludes_old(self):
        """hooks.on_startup.preload contains Qwen3.8-27B-FP8 and must NOT contain Qwen3.6."""
        data = yamlio.load(CONFIG_YAML)
        preload = (data.get("hooks") or {}).get("on_startup", {}).get("preload", [])

        self.assertIn(
            self.MODEL_ID,
            preload,
            "preload must include the batched coder model",
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


if __name__ == "__main__":
    unittest.main()
