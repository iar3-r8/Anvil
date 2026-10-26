"""Tests for the Pi sandbox operator documentation,
``doc/pi-sandbox/README.md`` (behaviour 9 of ``plans/pi-sandbox-image.md``).

The README is data under test: the assertions pin key phrases -- the build
command, the run recipe, each of the three env vars with its stated reason,
the verification that host ``~/.pi`` is unreachable, and the
exfiltration-boundary statement -- never raw bytes, so a reworded README
still matches as long as the load-bearing operator facts survive.

The file does not exist yet; until it is added every test here fails from
the missing-file guard in :attr:`SandboxDocsCase.text` with exactly
``doc/pi-sandbox/README.md does not exist`` -- never from a bare
``FileNotFoundError`` leaking out.
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

README = REPO_ROOT / "doc" / "pi-sandbox" / "README.md"

DOCKERFILE_PATH = "docker/Dockerfile.sandbox"
WORKSPACE_BIND = "/workspace"
NAMED_VOLUME = "sandbox-agent"
GATEWAY_VARS = ("PI_GATEWAY_HOST", "PI_GATEWAY_PORT")
AGENT_DIR_VAR = "PI_CODING_AGENT_DIR"

# Phrases that state, in some wording, that a checked path is absent.
ABSENCE_PHRASES = (
    "not exist",
    "must not",
    "no such",
    "unreachable",
    "not present",
    "cannot be seen",
    "absent",
)

# Words that carry the "the network, not the binary set" contrast.
BOUNDARY_NEGATIONS = ("not", "never", "cannot", "can't", "won't", "no")

# Consequence words: mounting the host agent home exposes these.
EXPOSURE_WORDS = ("expose", "credentials", "sessions", "settings")


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

    The variable names and their reasons may sit on one line (a table row, a
    list item) or across a short paragraph; both granularities are returned
    so a reworded layout still matches.
    """
    contexts = [line for line in text.splitlines() if name in line]
    contexts.extend(p for p in _paragraphs(text) if name in p)
    return contexts


class SandboxDocsCase(unittest.TestCase):
    """Shared access to the sandbox README text, guarded so a missing file
    reports itself instead of leaking a bare ``FileNotFoundError``."""

    @property
    def text(self):
        if not README.is_file():
            self.fail("doc/pi-sandbox/README.md does not exist")
        return README.read_text(encoding="utf-8")


class TestSandboxOperatorDocs(SandboxDocsCase):
    """The load-bearing operator facts ``doc/pi-sandbox/README.md`` must
    state: build, run, the three env vars with a reason each, the host
    ``~/.pi`` verification, and the exfiltration boundary."""

    def test_build_command_names_the_sandbox_dockerfile_and_builder(self):
        text = self.text

        self.assertIn(
            DOCKERFILE_PATH,
            text,
            "doc/pi-sandbox/README.md must name the Dockerfile path %s in "
            "its build command" % DOCKERFILE_PATH,
        )
        builder_named = "build_argv" in text or "pisandbox" in text
        command_named = "docker build" in text.lower() and "-f" in text
        self.assertTrue(
            builder_named or command_named,
            "the build recipe must carry a tag with the -f %s path, or name "
            "the builder anvilkit/pi/pisandbox.py build_argv" % DOCKERFILE_PATH,
        )

    def test_run_recipe_binds_workspace_and_the_sandbox_agent_volume(self):
        text = self.text

        self.assertIn(
            WORKSPACE_BIND,
            text,
            "the run recipe must bind the host repo at %s" % WORKSPACE_BIND,
        )
        self.assertIn(
            NAMED_VOLUME,
            text,
            "the run recipe must mount the agent home as the named volume "
            "'%s' (the name anvilkit/pi/pisandbox.py uses, never a host bind)"
            % NAMED_VOLUME,
        )

    def test_gateway_env_vars_named_with_the_reach_llama_swap_reason(self):
        text = self.text
        missing = [var for var in GATEWAY_VARS if var not in text]
        self.assertEqual(
            missing,
            [],
            "doc/pi-sandbox/README.md must name the gateway env vars %r, "
            "each with its stated reason" % (GATEWAY_VARS,),
        )
        contexts = []
        for var in GATEWAY_VARS:
            contexts.extend(_contexts(text, var))
        self.assertTrue(
            any("llama-swap" in c.lower() for c in contexts),
            "the reason stated beside PI_GATEWAY_HOST/PI_GATEWAY_PORT must "
            "be reaching llama-swap in-network; contexts: %r" % contexts,
        )

    def test_agent_dir_env_var_named_with_the_container_local_home_reason(self):
        text = self.text

        self.assertIn(
            AGENT_DIR_VAR,
            text,
            "doc/pi-sandbox/README.md must name %s with its stated reason"
            % AGENT_DIR_VAR,
        )
        contexts = _contexts(text, AGENT_DIR_VAR)
        self.assertTrue(
            any(
                "agent" in c.lower()
                and ("home" in c.lower() or ".pi/agent" in c.lower())
                for c in contexts
            ),
            "the reason stated beside %s must be that it points Pi at the "
            "container-local agent home; contexts: %r" % (AGENT_DIR_VAR, contexts),
        )

    def test_verification_checks_the_host_pi_path_does_not_exist(self):
        text = self.text
        lines = [l for l in text.splitlines() if ".pi" in l]
        paragraphs = [p for p in _paragraphs(text) if ".pi" in p]
        candidates = lines + paragraphs

        self.assertTrue(
            candidates,
            "the README must instruct the host verification around the "
            "host agent home ~/.pi",
        )
        self.assertTrue(
            any(
                any(phrase in c.lower() for phrase in ABSENCE_PHRASES)
                for c in candidates
            ),
            "the verification must run the image with the agent home "
            "mounted, list the host home, and state the path must not "
            "exist from inside; contexts: %r" % candidates,
        )

    def test_mounting_the_host_agent_home_is_never_the_fix(self):
        text = self.text
        lines = [l for l in text.splitlines() if ".pi/agent" in l]
        paragraphs = [p for p in _paragraphs(text) if ".pi/agent" in p]
        candidates = [c for c in lines + paragraphs if "mount" in c.lower()]

        self.assertTrue(
            candidates,
            "the README must address mounting the host ~/.pi/agent; "
            "contexts: %r" % (lines + paragraphs),
        )
        self.assertTrue(
            any(
                ("never" in c.lower() and "fix" in c.lower())
                or any(word in c.lower() for word in EXPOSURE_WORDS)
                for c in candidates
            ),
            "mounting the host ~/.pi/agent must be stated as never the fix "
            "and as exposing credentials/settings/sessions; contexts: %r"
            % candidates,
        )

    def test_curl_and_wget_named_and_the_network_is_the_boundary(self):
        text = self.text

        self.assertTrue(
            _word_present(text, "curl"),
            "the README must name curl as shipped in the base image",
        )
        self.assertTrue(
            _word_present(text, "wget"),
            "the README must name wget as shipped in the base image",
        )
        paragraphs = _paragraphs(text.lower())
        boundary = [
            p
            for p in paragraphs
            if "network" in p
            and ("egress" in p or "internal" in p)
            and "binar" in p
            and any(negation in p for negation in BOUNDARY_NEGATIONS)
        ]
        self.assertTrue(
            boundary,
            "the README must state that curl and wget exist in the base "
            "image, so the network (the internal network, no egress), not "
            "the binary set, is the exfiltration boundary",
        )
