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
