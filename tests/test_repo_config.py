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

    # -- Behaviour 3: the identity bridge is present and correctly oriented -----
    # llama-swap uses the models key as the model id in API requests and forwards
    # that id upstream to vLLM; vLLM matches the incoming model field against its
    # served name, which defaults to the --model argument. The bridge is
    # --model <real Hugging Face path> + --served-model-name <gateway id>.
    # A missing or swapped bridge makes every request to this block 404 at the
    # vLLM worker (plan §1.5).

    WEIGHTS_PATH = "Qwen/Qwen3.8-27B-FP8"

    def test_cmd_model_is_weights_path(self):
        """cmd must carry the token pair ['--model', <Hugging Face path>] — the real weights."""
        tokens = self._cmd_tokens()
        values = self._flag_values(tokens, "--model")
        self.assertEqual(
            values,
            [self.WEIGHTS_PATH],
            "cmd must carry exactly ['--model', {!r}] (the real Hugging Face path, not the "
            "-batch gateway id); --model value token(s) found: {!r}".format(
                self.WEIGHTS_PATH, values
            ),
        )

    def test_cmd_served_model_name_is_gateway_id(self):
        """cmd must carry ['--served-model-name', <models key>]; its absence 404s every request.

        The value must equal the models key exactly, because llama-swap forwards
        that id upstream and vLLM serves under --model by default.
        """
        tokens = self._cmd_tokens()
        values = self._flag_values(tokens, "--served-model-name")
        if not values:
            self.fail(
                "cmd must carry ['--served-model-name', {!r}]; the flag is absent, so every "
                "request to this block would 404 at the vLLM worker, which serves {!r} by "
                "default while llama-swap forwards {!r}".format(
                    self.MODEL_ID, self.WEIGHTS_PATH, self.MODEL_ID
                )
            )
        self.assertEqual(
            values,
            [self.MODEL_ID],
            "cmd must carry exactly ['--served-model-name', {!r}] (the models key); "
            "--served-model-name value token(s) found: {!r}".format(self.MODEL_ID, values),
        )

    def test_cmd_identity_flags_not_swapped(self):
        """--model and --served-model-name must be correctly oriented — each asserted individually.

        The two values are different strings, so a transposed pair fails this test
        and both of the single-flag tests above; the value of each flag is checked
        against its own expected token.
        """
        tokens = self._cmd_tokens()
        model_values = self._flag_values(tokens, "--model")
        served_values = self._flag_values(tokens, "--served-model-name")
        self.assertNotEqual(
            model_values,
            served_values,
            "--model and --served-model-name carry the same value token(s) {!r}; the identity "
            "bridge is transposed (expected --model {!r} and --served-model-name {!r})".format(
                model_values, self.WEIGHTS_PATH, self.MODEL_ID
            ),
        )
        self.assertEqual(
            model_values,
            [self.WEIGHTS_PATH],
            "--model must be {!r} (not the gateway id); found {!r}".format(self.WEIGHTS_PATH, model_values),
        )
        self.assertEqual(
            served_values,
            [self.MODEL_ID],
            "--served-model-name must be {!r} (not the Hugging Face path); found {!r}".format(
                self.MODEL_ID, served_values
            ),
        )

    def test_cmd_identity_flags_appear_exactly_once(self):
        """--model and --served-model-name must each appear exactly once (duplicates are last-wins)."""
        tokens = self._cmd_tokens()
        for flag in ("--model", "--served-model-name"):
            count = tokens.count(flag)
            self.assertEqual(
                count,
                1,
                "cmd must contain {!r} exactly once, found {} occurrence(s); values: {!r}".format(
                    flag, count, self._flag_values(tokens, flag)
                ),
            )

    # -- Behaviour 4: the gateway concurrency cap is lifted identically on both --
    # llama-swap caps in-flight requests per model at an internal default of 10;
    # concurrencyLimit "any number greater than 0 will override the internal
    # default value of 10" and requests beyond the limit receive HTTP 429
    # (doc/external/llama-swap/configuration-reference.md). The stress ramp
    # doubles (1, 2, 4, 8, 16, 32, ...), so without an explicit cap every level
    # above 10 is refused by the gateway before vLLM sees it. The cap is a
    # measurement-harness property, so it must be present, integer, > 0 and
    # IDENTICAL on both blocks, or the A/B comparison is invalid.

    BASELINE_ID = "Qwen/Qwen3.8-27B-FP8"

    _GATEWAY_CAP_EXPLANATION = (
        "llama-swap would then return HTTP 429 Too Many Requests above the cap, and the "
        "stress report would measure the gateway rather than vLLM (anvilkit.stress "
        "concurrency_levels() ramps 1, 2, 4, 8, 16, 32, ...)"
    )

    def _load_baseline_block(self):
        """Return the baseline model block, failing with a message naming the key."""
        models = self._load_config()
        self.assertIn(
            self.BASELINE_ID,
            models,
            "models dict must contain key {!r} (the baseline vLLM setup is missing)".format(
                self.BASELINE_ID
            ),
        )
        return models[self.BASELINE_ID]

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

    def test_batch_block_has_concurrency_limit(self):
        """The batch block must carry concurrencyLimit as a true int (> 0)."""
        block = self._load_batch_block()
        value = self._concurrency_limit_of(block, self.MODEL_ID)
        self.assertIsNotNone(
            value,
            "concurrencyLimit is absent or not a true int in models[ {!r} ] (got {!r}); "
            "with no limit greater than 0, llama-swap falls back to its internal default "
            "of 10 and {}, invalidating the stress run on this setup".format(
                self.MODEL_ID, block.get("concurrencyLimit"), self._GATEWAY_CAP_EXPLANATION
            ),
        )
        self.assertGreater(
            value,
            0,
            "concurrencyLimit in models[ {!r} ] is {} (not > 0); a zero limit falls back "
            "to the internal default of 10, so {}".format(
                self.MODEL_ID, value, self._GATEWAY_CAP_EXPLANATION
            ),
        )

    def test_baseline_block_has_concurrency_limit(self):
        """The baseline block must carry concurrencyLimit as a true int (> 0)."""
        block = self._load_baseline_block()
        value = self._concurrency_limit_of(block, self.BASELINE_ID)
        self.assertIsNotNone(
            value,
            "concurrencyLimit is absent or not a true int in models[ {!r} ] (got {!r}); "
            "with no limit greater than 0, llama-swap falls back to its internal default "
            "of 10 and {}, so the control side of the comparison would be refused above 10 "
            "while the batch side is not".format(
                self.BASELINE_ID, block.get("concurrencyLimit"), self._GATEWAY_CAP_EXPLANATION
            ),
        )
        self.assertGreater(
            value,
            0,
            "concurrencyLimit in models[ {!r} ] is {} (not > 0); a zero limit falls back "
            "to the internal default of 10, so {}".format(
                self.BASELINE_ID, value, self._GATEWAY_CAP_EXPLANATION
            ),
        )

    def test_concurrency_limits_equal_on_both_blocks(self):
        """Both blocks must carry the SAME concurrencyLimit.

        The cap is a measurement-harness property, not the variable under test:
        an asymmetric cap invalidates the A/B comparison, because one side of the
        ramp would then be refused by the gateway while the other is not.
        """
        batch_value = self._concurrency_limit_of(self._load_batch_block(), self.MODEL_ID)
        baseline_value = self._concurrency_limit_of(self._load_baseline_block(), self.BASELINE_ID)
        self.assertIsNotNone(
            batch_value,
            "concurrencyLimit is absent or not a true int in models[ {!r} ] (got {!r}); it "
            "must be present on both blocks or the harness is asymmetric".format(
                self.MODEL_ID, self._load_batch_block().get("concurrencyLimit")
            ),
        )
        self.assertIsNotNone(
            baseline_value,
            "concurrencyLimit is absent or not a true int in models[ {!r} ] (got {!r}); it "
            "must be present on both blocks or the harness is asymmetric".format(
                self.BASELINE_ID, self._load_baseline_block().get("concurrencyLimit")
            ),
        )
        self.assertEqual(
            batch_value,
            baseline_value,
            "concurrencyLimit is {!r} on {!r} but {!r} on {!r}; the cap is a "
            "measurement-harness property and must be identical on both blocks, "
            "otherwise {} and one side of the comparison is refused above its cap".format(
                batch_value,
                self.MODEL_ID,
                baseline_value,
                self.BASELINE_ID,
                self._GATEWAY_CAP_EXPLANATION,
            ),
        )

    def test_concurrency_limit_at_least_64(self):
        """The shared concurrencyLimit must be >= 64, above the stress ramp's useful range."""
        batch_block = self._load_batch_block()
        baseline_block = self._load_baseline_block()
        for model_id, block in ((self.MODEL_ID, batch_block), (self.BASELINE_ID, baseline_block)):
            value = self._concurrency_limit_of(block, model_id)
            self.assertIsNotNone(
                value,
                "concurrencyLimit is absent or not a true int in models[ {!r} ] (got {!r}); "
                "it must be an integer >= 64 so the gateway is never the binding "
                "constraint — otherwise {}".format(
                    model_id, block.get("concurrencyLimit"), self._GATEWAY_CAP_EXPLANATION
                ),
            )
            self.assertGreaterEqual(
                value,
                64,
                "concurrencyLimit in models[ {!r} ] is {}; the stress ramp doubles to 16 "
                "and 32, so a cap below 64 makes {} and the report would reflect the "
                "gateway, not the engine".format(
                    model_id, value, self._GATEWAY_CAP_EXPLANATION
                ),
            )

    # -- Behaviour 5: the new setup is isolated from the running system ----------
    # The two setups must never coexist. llama-swap's matrix solver gives the
    # isolation for free: "A model that appears in no set can only run on its own"
    # (doc/external/llama-swap/configuration-reference.md). Leaving the new id out
    # of matrix.vars, matrix.sets and hooks.on_startup.preload is therefore the
    # MECHANISM that guarantees requesting it evicts the baseline, and vice versa
    # (plan §1.6). The block is brought up on demand by the first stress request,
    # by design — it must not be preloaded.

    def test_batch_id_absent_from_preload(self):
        """hooks.on_startup.preload must NOT contain the new id.

        Preloading it would start the second vLLM container at gateway boot and
        the two setups would be co-resident, which the experiment forbids.
        """
        data = yamlio.load(CONFIG_YAML)
        preload = (data.get("hooks") or {}).get("on_startup", {}).get("preload", [])
        self.assertNotIn(
            self.MODEL_ID,
            preload,
            "hooks.on_startup.preload must not contain {!r} (found in {!r}): the two "
            "setups must never be co-resident — the user runs them independently, one "
            "at a time, so the batch block must be brought up on demand by the first "
            "request, not preloaded at startup (plan §1.6)".format(self.MODEL_ID, preload),
        )

    def test_batch_id_absent_from_matrix_vars_values(self):
        """The new id must be absent from every VALUE in matrix.vars.

        A var that names the new id would fold it into the running set, so the
        matrix solver could schedule it alongside the baseline.
        """
        data = yamlio.load(CONFIG_YAML)
        matrix_vars = (data.get("matrix") or {}).get("vars", {})
        self.assertIsInstance(
            matrix_vars,
            dict,
            "matrix.vars must be a mapping, got {}".format(type(matrix_vars).__name__),
        )
        for var_name, var_value in matrix_vars.items():
            self.assertNotEqual(
                var_value,
                self.MODEL_ID,
                "matrix.vars.{0} names {1!r}: the two setups must never be co-resident "
                "— a var that references the batch id would schedule it inside the "
                "running set (plan §1.6)".format(var_name, var_value),
            )

    def test_batch_id_absent_from_matrix_sets_expressions(self):
        """The new id must not appear in any matrix.sets expression.

        The sets values are DSL strings ("generic & coder & nomic"), so this is a
        substring search across every set expression, not a list membership test.
        A model that appears in some set is schedulable with the others — the
        whole point is that this one appears in none.
        """
        data = yamlio.load(CONFIG_YAML)
        matrix_sets = (data.get("matrix") or {}).get("sets", {})
        self.assertIsInstance(
            matrix_sets,
            dict,
            "matrix.sets must be a mapping, got {}".format(type(matrix_sets).__name__),
        )
        for set_name, expression in matrix_sets.items():
            self.assertIsInstance(
                expression,
                str,
                "matrix.sets.{} must be a DSL expression string, got {!r}".format(
                    set_name, expression
                ),
            )
            self.assertNotIn(
                self.MODEL_ID,
                expression,
                "matrix.sets.{0} expression {1!r} references {2!r}: a model in a set "
                "can run with the set's other models, but the two setups must never be "
                "co-resident — the batch id must appear in no set (plan §1.6)".format(
                    set_name, expression, self.MODEL_ID
                ),
            )

    def test_matrix_vars_coder_unchanged(self):
        """matrix.vars.coder must still equal the baseline id, not the new one.

        If the coder var pointed at the batch id, the day-to-day setup would be
        the stress-test setup and the A/B comparison would have no control.
        """
        data = yamlio.load(CONFIG_YAML)
        coder_id = (data.get("matrix") or {}).get("vars", {}).get("coder")
        self.assertEqual(
            coder_id,
            self.BASELINE_ID,
            "matrix.vars.coder must still be {!r}, got {!r}: the running system's "
            "coder is the baseline, and the batch block is the isolated stress "
            "target only (plan §1.6)".format(self.BASELINE_ID, coder_id),
        )

    def test_read_models_coder_topology_unchanged(self):
        """config.read_models() must still report the baseline coder id and 262144 window.

        Anvil's rendered Zoo Code settings depend on both values, so either one
        drifting would corrupt every provisioned repo even though the vLLM side
        would keep working.
        """
        from anvilkit.config import read_models  # noqa: E402

        topology = read_models(CONFIG_YAML)
        self.assertEqual(
            topology.coder_id,
            self.BASELINE_ID,
            "read_models().coder_id must be {!r}, got {!r}: Anvil's rendered Zoo "
            "Code settings depend on it, so the batch id must not leak into the "
            "running system's topology".format(self.BASELINE_ID, topology.coder_id),
        )
        self.assertEqual(
            topology.coder_context_window,
            262144,
            "read_models().coder_context_window must be 262144, got {!r}: Anvil's "
            "rendered Zoo Code settings depend on it".format(
                topology.coder_context_window
            ),
        )

    def test_preload_ids_all_exist_in_models(self):
        """Every id in hooks.on_startup.preload must still be a key in models.

        A preload id that no longer exists is a startup-time config break: the
        gateway would try to boot a model it cannot find.
        """
        data = yamlio.load(CONFIG_YAML)
        models = data.get("models", {})
        preload = (data.get("hooks") or {}).get("on_startup", {}).get("preload", [])
        for model_id in preload:
            self.assertIn(
                model_id,
                models,
                "preloaded id {!r} is not a key in models: llama-swap requires preload "
                "ids to match keys in the models section, so this would break startup".format(
                    model_id
                ),
            )
