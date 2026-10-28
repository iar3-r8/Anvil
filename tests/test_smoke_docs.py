"""Tests for the smoke-test operator documentation,
``doc/pi-smoke-test/README.md`` (behaviour 20 of ``plans/smoke-test.md``).

The README is data under test: the assertions pin key phrases -- the six
layer names exactly as the report prints them, the ``anvil smoke-test``
command, the "run it occasionally" framing, the statement that CI never runs
it, and each of the five pitfalls -- never raw bytes, so a reworded README
still matches as long as the load-bearing operator facts survive.

The file does not exist yet; until it is added every test here fails from
the missing-file guard in :attr:`SmokeDocsCase.text` with exactly
``doc/pi-smoke-test/README.md does not exist`` -- never from a bare
``FileNotFoundError`` leaking out.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

README = REPO_ROOT / "doc" / "pi-smoke-test" / "README.md"

# The six layer names, exactly as the report prints them (``LAYER_NAMES`` in
# tests/test_smoke.py); the operator doc must name the layers by these names.
LAYER_NAMES = (
    "docker-daemon",
    "gateway",
    "sandbox-agent-volume",
    "role-prompt",
    "coder-run",
    "failure-paths",
)

COMMAND = "anvil smoke-test"

# The in-network port and the host-side override the README must contrast.
IN_NETWORK_PORT = "8080"
HOST_PORT_VAR = "LLM_PORT"

# The coder model id from config.yaml: it carries a slash, and the README
# must say that slash must not be "fixed".
CODER_MODEL_ID = "Qwen/Qwen3.8-27B-FP8"

# The first-run stderr line the README must quote as noise.
FIRST_RUN_NOISE = "No project session found"

# Words that frame a line as harmless noise rather than a failure.
NOISE_WORDS = ("noise", "harmless", "expected", "ignore", "benign")

# Negations carrying the "CI never runs it" and "must not be fixed" pins.
NEGATIONS = ("never", "not", "don't", "do not", "no")


def _word_present(text, name):
    """True if *name* appears as a standalone word (not fused into a longer
    word or a hyphenated neighbour)."""
    return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text) is not None


def _paragraphs(text):
    """The non-empty paragraphs of *text* as single space-joined strings."""
    paragraphs, current = [], []
    for line in text.splitlines():
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def _contexts(text, name):
    """Every line and every paragraph of *text* that contains *name*.

    A fact and its pin may sit on one line (a list item, a table row) or
    across a short paragraph; both granularities are returned so a reworded
    layout still matches.
    """
    contexts = [line for line in text.splitlines() if name in line]
    contexts.extend(p for p in _paragraphs(text) if name in p)
    return contexts


class SmokeDocsCase(unittest.TestCase):
    """Shared access to the smoke-test README text, guarded so a missing
    file reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not README.is_file():
            self.fail("doc/pi-smoke-test/README.md does not exist")
        return README.read_text(encoding="utf-8")


class TestSmokeOperatorDocs(SmokeDocsCase):
    """The load-bearing operator facts ``doc/pi-smoke-test/README.md`` must
    state: the six layer names, the command, the occasional framing, the CI
    exclusion, and the five pitfalls."""

    def test_readme_names_all_six_layers(self):
        text = self.text
        missing = [name for name in LAYER_NAMES if name not in text]

        self.assertEqual(
            missing,
            [],
            "doc/pi-smoke-test/README.md must name all six layers %r, the "
            "names the report prints; missing: %r" % (LAYER_NAMES, missing),
        )

    def test_readme_names_the_smoke_test_command(self):
        text = self.text

        self.assertIn(
            COMMAND,
            text,
            "doc/pi-smoke-test/README.md must name the %r command" % COMMAND,
        )

    def test_readme_frames_the_smoke_test_as_occasional(self):
        text = self.text

        self.assertIn(
            "occasionally",
            text,
            "doc/pi-smoke-test/README.md must carry the 'run it occasionally' "
            "framing of the smoke test",
        )

    def test_readme_states_ci_never_runs_the_smoke_test(self):
        text = self.text

        self.assertTrue(
            _word_present(text, "CI"),
            "doc/pi-smoke-test/README.md must address CI explicitly",
        )
        candidates = [
            c for c in _contexts(text, "CI") if "smoke" in c.lower()
        ]
        self.assertTrue(
            candidates,
            "the README must tie CI to the smoke test; CI contexts: %r"
            % _contexts(text, "CI"),
        )
        self.assertTrue(
            any(neg in c.lower() for c in candidates for neg in NEGATIONS),
            "the CI statement must say CI never runs the smoke test; "
            "contexts: %r" % candidates,
        )

    def test_pitfall_root_owned_models_json_eacces_is_pinned(self):
        text = self.text

        self.assertIn(
            "models.json",
            text,
            "doc/pi-smoke-test/README.md must name models.json in the "
            "root-owned/EACCES pitfall",
        )
        self.assertIn(
            "EACCES",
            text,
            "doc/pi-smoke-test/README.md must pin the EACCES error in the "
            "root-owned models.json pitfall",
        )
        contexts = [
            c
            for c in _contexts(text, "EACCES")
            if "models.json" in c
            or "root" in c.lower()
            or "chown" in c.lower()
        ]
        self.assertTrue(
            contexts,
            "the EACCES pitfall must tie the error to the root-owned "
            "models.json or the chown repair; EACCES contexts: %r"
            % _contexts(text, "EACCES"),
        )

    def test_pitfall_in_network_8080_vs_llm_port_is_pinned(self):
        text = self.text

        self.assertIn(
            IN_NETWORK_PORT,
            text,
            "doc/pi-smoke-test/README.md must name the in-network port %s"
            % IN_NETWORK_PORT,
        )
        contexts = [
            c for c in _contexts(text, IN_NETWORK_PORT) if HOST_PORT_VAR in c
        ]
        self.assertTrue(
            contexts,
            "the README must contrast the in-network port %s with the "
            "host-side %s on a shared line or paragraph; %s contexts: %r"
            % (IN_NETWORK_PORT, HOST_PORT_VAR, IN_NETWORK_PORT,
               _contexts(text, IN_NETWORK_PORT)),
        )

    def test_pitfall_pre_existing_empty_volume_is_pinned(self):
        text = self.text

        contexts = [
            c
            for c in _contexts(text, "sandbox-agent")
            if "empty" in c.lower()
        ]
        self.assertTrue(
            contexts,
            "the README must state the sandbox-agent volume is empty; "
            "contexts: %r" % _contexts(text, "sandbox-agent"),
        )
        self.assertTrue(
            any(
                word in text.lower()
                for word in ("pre-existing", "first run", "already")
            ),
            "the volume's emptiness must be framed as pre-existing "
            "(created before the smoke test runs, still empty)",
        )

    def test_pitfall_slash_carrying_coder_id_must_not_be_fixed(self):
        text = self.text

        contexts = _contexts(text, CODER_MODEL_ID)
        self.assertTrue(
            contexts,
            "the README must name the coder model id %s" % CODER_MODEL_ID,
        )
        self.assertTrue(
            any(
                "fix" in c.lower()
                and any(neg in c.lower() for neg in NEGATIONS)
                for c in contexts
            ),
            "the README must state the slash-carrying coder id %s must not "
            "be 'fixed'; contexts: %r" % (CODER_MODEL_ID, contexts),
        )

    def test_pitfall_first_run_no_project_session_noise_is_pinned(self):
        text = self.text

        self.assertIn(
            FIRST_RUN_NOISE,
            text,
            "the README must quote the first-run stderr line %r"
            % FIRST_RUN_NOISE,
        )
        contexts = _contexts(text, FIRST_RUN_NOISE)
        self.assertTrue(
            any(
                word in c.lower() for c in contexts for word in NOISE_WORDS
            ),
            "the README must frame %r as expected first-run noise, not a "
            "failure; contexts: %r" % (FIRST_RUN_NOISE, contexts),
        )


if __name__ == "__main__":
    unittest.main()
