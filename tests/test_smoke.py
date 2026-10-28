"""Tests for anvilkit.smoke, behaviours 1–10 of plans/smoke-test.md.

Written before the implementation (TDD red): ``anvilkit/smoke.py`` does not
exist yet, so the guarded import below turns the missing module into a clear,
named failure in each test instead of an import-time crash.

Contract under test (from the plan): ``LayerResult`` is a small value type
carrying ``name`` (str), ``ok`` (a state string: ``"ok"``, ``"failed"`` or
``"skipped"``), ``detail`` (str) and ``fix_lines`` (sequence of str, default
empty). ``format_report(results)`` renders a per-layer verdict for a human:
one ``✅`` line per passing layer and one ``❌`` line per failing layer, each
carrying the layer name and its detail; fix lines print indented (at least
two spaces) under a failing layer only; a passing or skipped result never
prints its fix lines, and a skipped result prints neither verdict glyph; an
empty result list renders only the stable header ``"Anvil smoke test"`` and
no layer lines.

Behaviour 2: ``summarize(results)`` returns a process exit code — 0 when
nothing failed, 4 (the docker class, ``EXIT_DOCKER`` in ``anvilkit/cli.py``)
when any of layers 1–4 failed, 1 (the internal class, ``EXIT_ERROR``) when
only layer 5 or 6 failed. The seam these tests pin: the layer number is the
1-based position in the list, position 1 being layer 1 and position 6 layer
6. A layer whose state is neither ``"ok"`` nor ``"skipped"`` counts as
failed; a skipped layer never contributes to a non-zero exit.

Behaviour 3 (PIN): ``smoke.py`` must adopt the four pinned names -- the
named volume, the internal network, the image uid and the agent home -- as
module-level constants taken from ``anvilkit.pi.pisandbox``; each must equal
the corresponding private ``pisandbox`` attribute, and the raw source of
``anvilkit/smoke.py`` must contain none of the four literal spellings.

Behaviour 4: ``check_docker_daemon(docker_runner)`` is layer 1's daemon
check, taking the plan's single injected docker seam --
``docker_runner(argv) -> (exit_code, stdout, stderr)``, list-form argv,
never ``shell=True``. It runs ``["docker", "version", "--format",
"{{.Server.Version}}"]`` and returns a ``LayerResult`` named
``"docker-daemon"``: exit 0 is the pass state with the trimmed server
version in the detail; a non-zero exit is the fail state with the stderr in
the detail; a ``FileNotFoundError`` from the runner is a fail saying docker
is not on PATH -- never a traceback.

Behaviour 5: ``check_sandbox_image(docker_runner, tag=...)`` is layer
1's image-presence check, over the same injected seam, with the image
tag defaulting to the plan's pinned ``pi-sandbox``. It runs
``["docker", "image", "inspect", <tag>]`` and returns a ``LayerResult``:
exit 0 is the pass state; a non-zero exit is the fail state whose fix
lines are exactly ``[" ".join(pisandbox.build_argv(tag))]`` -- the fix
line is derived from ``anvilkit.pi.pisandbox.build_argv``, never
hand-typed, so a Dockerfile-path change cannot leave it stale.

Behaviour 6: ``check_sandbox_network(docker_runner)`` is layer 1's
internal-network-presence check, over the same injected seam. It runs
``["docker", "network", "inspect", <name>]`` where ``<name>`` is the
module's ``INTERNAL_NETWORK`` constant adopted from
``anvilkit.pi.pisandbox._INTERNAL_NETWORK`` -- never a re-spelled literal,
so a rename cannot desynchronise the check from the run. Exit 0 is the
pass state; a non-zero exit is the fail state whose fix line carries the
compose-up command ``docker compose --profile coder up -d`` and names
that compose creates the network; a ``FileNotFoundError`` from the runner
is a not-on-PATH fail, never a traceback.

Behaviour 7: ``check_gateway_container(docker_runner)`` is layer 2's
gateway container check, over the same injected seam. The container name
is the module constant ``GATEWAY_CONTAINER`` -- the ``container_name``
from ``docker-compose.yml`` (``llama-swap-service``); ``llama-swap`` is
the service/DNS name only and must never be the match. It runs
``["docker", "ps", "--filter", "name=<container>", "--format",
"{{.Names}}"]`` and returns a ``LayerResult`` named
``"gateway-container"``: exit 0 with a line that equals the container
name exactly (after stripping) is the pass state; a non-zero exit, or an
output with no such exact line (including empty output), is the fail
state whose fix line carries the compose-up command
``docker compose --profile coder up -d``. The match is exact per line,
never a substring -- ``llama-swap-service-old`` alone is a fail; a
``FileNotFoundError`` from the runner is a not-on-PATH fail, never a
traceback.

Behaviour 8: ``check_gateway_model(port, config_path,
check_gateway=..., read_models=...)`` is layer 2's
coder-model-registered-and-hot check. It reuses two in-repo
collaborators that the plan names -- ``health.check_gateway`` and
``config.read_models`` -- both injectable so the tests run without a
network or a file. The coder id comes from
``read_models(config_path).coder_id`` (``matrix.vars.coder``) and is
never hard-coded. The gateway is online, the id present in
``status.models`` and that entry's ``hot`` is ``True`` -- that is the
pass state, named ``"gateway-model"``. The report always states the
in-network port is 8080 regardless of the host ``LLM_PORT``, on the
pass detail too. Offline, id absent, and id present-but-cold are three
distinct details, each carrying the 8080 fact; a ``ConfigError`` from
``read_models`` fails the layer naming the file -- never a traceback.

Behaviour 9: ``check_agent_volume(docker_runner)`` is layer 3's
agent-volume-presence check, over the same injected seam. It runs
``["docker", "volume", "inspect", <name>]`` where ``<name>`` is the
module's ``NAMED_VOLUME`` constant adopted from
``anvilkit.pi.pisandbox._NAMED_VOLUME`` -- never a re-spelled literal,
so a rename cannot desynchronise the check from the run. Exit 0 is the
pass state, named ``"agent-volume"``; a non-zero exit is the fail state
whose detail says the volume is created on first run and stays empty
until seeded (one of the issue's known pitfalls); a
``FileNotFoundError`` from the runner is a not-on-PATH fail, never a
traceback.

Behaviour 10: ``check_models_json(docker_runner, tag=...)`` is layer
3's models.json-readability check, over the same injected seam, with
the image tag defaulting to the module's ``DEFAULT_IMAGE_TAG``. It runs
``["docker", "run", "--rm", "-v", <NAMED_VOLUME>:<AGENT_HOME>, "--user",
<IMAGE_UID>, <tag>, "cat", <AGENT_HOME> + "/models.json"]`` -- every
name from the adopted constants -- and returns a
``(LayerResult, Optional[str])`` tuple: the ``LayerResult`` is named
``"models-json"``, and the second element is the exact stdout the
in-container cat printed on a pass -- the text behaviour 11 parses for
the coder id -- or ``None`` on every fail. Exit 0 with non-empty stdout
is the pass state; exit 0 with empty or whitespace-only stdout fails as
unseeded, a distinct detail; a non-zero exit whose stderr carries a
permission marker fails with the chown one-liner as its fix line, and
one whose stderr carries a no-such-file marker fails with the seed
instruction and no chown line; a ``FileNotFoundError`` from the runner
is a not-on-PATH fail, never a traceback.

Behaviour 11: ``check_coder_id(models_json_text, config_path,
read_models=...)`` is layer 3's coder-id-match check. It takes the
models.json text -- the exact stdout behaviour 10 exposed -- and the
config path, reading the coder id from
``read_models(config_path).coder_id`` (``matrix.vars.coder``) through
an injectable ``read_models`` seam defaulting to the real
``config.read_models`` -- the same pattern behaviour 8 pins, so
neither id is hard-coded. It collects every
``providers.<name>.models[].id``: the coder id present passes, the
layer named ``"coder-id-match"``, the detail naming the provider
carrying it; the id absent fails, printing both the expected coder id
and the seeded ids found. Malformed JSON fails naming the parse
error; a missing ``providers`` key or a provider with no ``models``
list (or a ``models`` that is not a list) fails saying so -- never a
``KeyError`` or ``TypeError`` escaping.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
   sys.path.insert(0, str(REPO_ROOT))

from anvilkit.pi import pisandbox  # noqa: E402

# Behaviour 3 (PIN): the public names ``smoke.py`` must expose for the four
# pinned names, each mapped to the private ``pisandbox`` attribute it adopts.
PINNED_CONSTANTS = (
   ("NAMED_VOLUME", "_NAMED_VOLUME"),
   ("INTERNAL_NETWORK", "_INTERNAL_NETWORK"),
   ("IMAGE_UID", "_IMAGE_UID"),
   ("AGENT_HOME", "_AGENT_HOME"),
)

# The literal spellings that must never appear in ``anvilkit/smoke.py``'s
# source: the names are imported from ``anvilkit.pi.pisandbox``, not
# re-spelled (a comment re-typing one counts -- the pin is deliberately raw).
PINNED_LITERALS = (
   "sandbox-agent",
   "sandbox-internal",
   "1001",
   "/home/sandbox/.pi/agent",
)

# Behaviour 1 (TDD red): this does not exist yet, so the import is guarded.
# The tests below turn the missing import into a clear, named failure
# instead of an import-time crash that would error every test in this module.
_smoke_import_error = None
try:  # noqa: E402
    from anvilkit import smoke
except ImportError as _err:
    # ``except ... as`` deletes the exception variable when the block ends,
    # so the message is copied out into a module-level name first.
    _smoke_import_error = str(_err)
    smoke = None

# The stable header ``format_report`` renders when the result list is empty
# (behaviour 1, error case). Later behaviours assert this same string.
HEADER = "Anvil smoke test"

# ``LayerResult.ok`` state values.
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"

PASS_GLYPH = "✅"
FAIL_GLYPH = "❌"


def _require_smoke():
    """Return the ``smoke`` module, or fail naming what is missing."""
    if smoke is None:
        raise AssertionError(
            "anvilkit.smoke is not implemented yet: "
            + (_smoke_import_error or "missing")
        )
    return smoke


def _layer(name, state, detail, fix_lines=None):
    """A ``LayerResult`` for the given name, state, detail and fix lines."""
    return _require_smoke().LayerResult(
        name=name,
        ok=state,
        detail=detail,
        fix_lines=tuple(fix_lines or ()),
    )


def _render(results):
    """Render ``results`` with ``smoke.format_report``."""
    return _require_smoke().format_report(results)


def _summarize(results):
    """Return ``smoke.summarize(results)``."""
    return _require_smoke().summarize(results)


# The six layer names in layer order (behaviours 4-17 of the plan), used to
# build full six-layer result lists; the list position is the layer number.
LAYER_NAMES = (
    "docker-daemon",       # layer 1: docker
    "gateway",             # layer 2: gateway
    "sandbox-agent-volume",  # layer 3: agent volume
    "role-prompt",         # layer 4: role prompt
    "coder-run",           # layer 5: the run
    "failure-paths",       # layer 6: the failure paths
)


def _layers(states):
    """Six ``LayerResult``s in layer order, one per state in ``states``."""
    return [
        _layer(name, state, "detail for %s" % name)
        for name, state in zip(LAYER_NAMES, states)
    ]


class TestFormatReportPassingLayer(unittest.TestCase):
    """Behaviour 1: one ✅ line per passing layer, carrying name and detail."""

    def test_format_report_single_passing_layer_prints_one_check_line_with_name_and_detail(self):
        # Arrange: a single passing layer whose detail is distinct text.
        results = [_layer("docker-daemon", STATE_OK, "server 27.1.1")]

        # Act.
        text = _render(results)

        # Assert: exactly one ✅ line, no ❌, and that line carries both
        # the layer name and its detail.
        self.assertIsInstance(text, str)
        self.assertEqual(text.count(PASS_GLYPH), 1)
        self.assertNotIn(FAIL_GLYPH, text)
        check_lines = [ln for ln in text.splitlines() if PASS_GLYPH in ln]
        self.assertEqual(len(check_lines), 1)
        self.assertIn("docker-daemon", check_lines[0])
        self.assertIn("server 27.1.1", check_lines[0])

    def test_format_report_two_passing_layers_prints_one_check_line_each_in_order(self):
        # Arrange: two passing layers with distinct names and details.
        results = [
            _layer("docker-daemon", STATE_OK, "server 27.1.1"),
            _layer("gateway", STATE_OK, "coder model hot"),
        ]

        # Act.
        text = _render(results)

        # Assert: one ✅ line per layer, in order, each carrying its own
        # name and detail (not the other layer's).
        self.assertEqual(text.count(PASS_GLYPH), 2)
        self.assertNotIn(FAIL_GLYPH, text)
        check_lines = [ln for ln in text.splitlines() if PASS_GLYPH in ln]
        self.assertEqual(len(check_lines), 2)
        self.assertIn("docker-daemon", check_lines[0])
        self.assertIn("server 27.1.1", check_lines[0])
        self.assertNotIn("gateway", check_lines[0])
        self.assertIn("gateway", check_lines[1])
        self.assertIn("coder model hot", check_lines[1])
        self.assertNotIn("server 27.1.1", check_lines[1])


class TestFormatReportFailingLayer(unittest.TestCase):
    """Behaviour 1: one ❌ line per failing layer, with its fix lines
    indented beneath it."""

    def test_format_report_single_failing_layer_prints_one_cross_line_with_name_and_detail(self):
        # Arrange: a single failing layer, no fix lines.
        results = [_layer("gateway", STATE_FAILED, "coder model not hot")]

        # Act.
        text = _render(results)

        # Assert: exactly one ❌ line, no ✅, carrying name and detail.
        self.assertEqual(text.count(FAIL_GLYPH), 1)
        self.assertNotIn(PASS_GLYPH, text)
        cross_lines = [ln for ln in text.splitlines() if FAIL_GLYPH in ln]
        self.assertEqual(len(cross_lines), 1)
        self.assertIn("gateway", cross_lines[0])
        self.assertIn("coder model not hot", cross_lines[0])

    def test_format_report_failing_layer_prints_fix_lines_indented_beneath_it(self):
        # Arrange: a failing layer with two distinct fix lines.
        fix_lines = [
            "docker build -f docker/Dockerfile.sandbox -t pi-sandbox docker/",
            "docker compose --profile coder up -d",
        ]
        results = [
            _layer("pi-sandbox-image", STATE_FAILED, "image missing",
                   fix_lines=fix_lines),
        ]

        # Act.
        text = _render(results)

        # Assert: every fix line is present, on its own line, below the
        # layer's ❌ line and indented by at least two characters.
        lines = text.splitlines()
        cross_idx = next(
            i for i, ln in enumerate(lines) if FAIL_GLYPH in ln
        )
        for fix in fix_lines:
            fix_idxs = [i for i, ln in enumerate(lines) if fix in ln]
            self.assertTrue(fix_idxs, "fix line %r missing from report" % fix)
            fix_line = lines[fix_idxs[0]]
            self.assertGreater(
                fix_idxs[0],
                cross_idx,
                "fix line %r must appear below the ❌ layer line" % fix,
            )
            indent = len(fix_line) - len(fix_line.lstrip(" \t"))
            self.assertGreaterEqual(
                indent,
                2,
                "fix line %r is not indented: %r" % (fix, fix_line),
            )


class TestFormatReportPassingLayerWithFixLines(unittest.TestCase):
    """Behaviour 1 (error): a passing result with fix_lines prints none of
    them."""

    def test_format_report_passing_layer_with_fix_lines_prints_none_of_them(self):
        # Arrange: a passing layer that carries fix lines it must not show.
        results = [
            _layer("sandbox-agent-volume", STATE_OK, "volume present",
                   fix_lines=["must-not-appear-1", "must-not-appear-2"]),
        ]

        # Act.
        text = _render(results)

        # Assert: the layer still passes, and neither fix line leaks out.
        self.assertEqual(text.count(PASS_GLYPH), 1)
        self.assertNotIn("must-not-appear-1", text)
        self.assertNotIn("must-not-appear-2", text)


class TestFormatReportSkippedLayer(unittest.TestCase):
    """Behaviour 1 (design intent): a skipped result renders distinctly —
    neither verdict glyph, and never its fix lines."""

    def test_format_report_skipped_layer_prints_no_fix_lines_and_no_verdict_glyph(self):
        # Arrange: a skipped layer (earlier layers failed) with a fix line.
        results = [
            _layer("coder-run", STATE_SKIPPED, "earlier layer failed",
                   fix_lines=["skipped-fix-must-not-show"]),
        ]

        # Act.
        text = _render(results)

        # Assert: no ✅ (not passed), no ❌ (not failed), no fix line;
        # the layer is still named with its detail.
        self.assertNotIn(PASS_GLYPH, text)
        self.assertNotIn(FAIL_GLYPH, text)
        self.assertNotIn("skipped-fix-must-not-show", text)
        self.assertIn("coder-run", text)
        self.assertIn("earlier layer failed", text)


class TestFormatReportOrdering(unittest.TestCase):
    """Behaviour 1: one glyph line per layer, in result order, fix lines
    only under failures."""

    def test_format_report_mixed_layers_prints_one_glyph_line_each_in_order(self):
        # Arrange: pass, fail (with a fix line), pass.
        results = [
            _layer("docker-daemon", STATE_OK, "server 27.1.1"),
            _layer("gateway", STATE_FAILED, "coder model not hot",
                   fix_lines=["gw-fix-line"]),
            _layer("role-prompt", STATE_OK, ".pi/roles/coder.md present"),
        ]

        # Act.
        text = _render(results)

        # Assert: exactly two ✅ lines and one ❌ line; the layer lines keep
        # result order; the fix line sits below its failing layer only.
        self.assertEqual(text.count(PASS_GLYPH), 2)
        self.assertEqual(text.count(FAIL_GLYPH), 1)
        lines = text.splitlines()
        idx_daemon = next(i for i, ln in enumerate(lines)
                          if "docker-daemon" in ln)
        idx_gateway = next(i for i, ln in enumerate(lines)
                           if "gateway" in ln)
        idx_prompt = next(i for i, ln in enumerate(lines)
                          if "role-prompt" in ln)
        self.assertLess(idx_daemon, idx_gateway)
        self.assertLess(idx_gateway, idx_prompt)
        fix_idx = next(i for i, ln in enumerate(lines)
                       if "gw-fix-line" in ln)
        self.assertGreater(fix_idx, idx_gateway)


class TestFormatReportEmptyList(unittest.TestCase):
    """Behaviour 1 (error): an empty result list renders a header and no
    layer lines."""

    def test_format_report_empty_list_renders_header_and_no_layer_lines(self):
        # Act: no results at all.
        text = _render([])

        # Assert: the output is exactly the stable header — no ✅, no ❌,
        # no layer lines.
        self.assertEqual(text.strip().splitlines(), [HEADER])
        self.assertNotIn(PASS_GLYPH, text)
        self.assertNotIn(FAIL_GLYPH, text)


class TestSummarizeAllPassed(unittest.TestCase):
    """Behaviour 2: nothing failed yields exit 0, including an empty list."""

    def test_summarize_all_six_layers_ok_returns_zero(self):
        # Arrange: every layer passed.
        results = _layers([STATE_OK] * 6)

        # Act + Assert: exit 0.
        self.assertEqual(_summarize(results), 0)

    def test_summarize_empty_list_returns_zero(self):
        # Act + Assert: no results at all is not a failure.
        self.assertEqual(_summarize([]), 0)


class TestSummarizeDockerClassLayers(unittest.TestCase):
    """Behaviour 2: any of layers 1-4 (the docker class) failing alone
    yields 4, the docker exit code (``EXIT_DOCKER`` in ``anvilkit/cli.py``)."""

    def test_summarize_layer_1_failed_alone_returns_four(self):
        # Arrange: only layer 1 (docker) failed.
        results = _layers([STATE_FAILED, STATE_OK, STATE_OK,
                           STATE_OK, STATE_OK, STATE_OK])

        # Act + Assert: docker class wins with exit 4.
        self.assertEqual(_summarize(results), 4)

    def test_summarize_layer_2_failed_alone_returns_four(self):
        # Arrange: only layer 2 (gateway) failed.
        results = _layers([STATE_OK, STATE_FAILED, STATE_OK,
                           STATE_OK, STATE_OK, STATE_OK])

        # Act + Assert.
        self.assertEqual(_summarize(results), 4)

    def test_summarize_layer_3_failed_alone_returns_four(self):
        # Arrange: only layer 3 (agent volume) failed.
        results = _layers([STATE_OK, STATE_OK, STATE_FAILED,
                           STATE_OK, STATE_OK, STATE_OK])

        # Act + Assert.
        self.assertEqual(_summarize(results), 4)

    def test_summarize_layer_4_failed_alone_returns_four(self):
        # Arrange: only layer 4 (role prompt) failed.
        results = _layers([STATE_OK, STATE_OK, STATE_OK, STATE_FAILED,
                           STATE_OK, STATE_OK])

        # Act + Assert.
        self.assertEqual(_summarize(results), 4)


class TestSummarizeInternalClassLayers(unittest.TestCase):
    """Behaviour 2: only layer 5 or 6 (the internal class) failing yields
    1, the internal exit code (``EXIT_ERROR`` in ``anvilkit/cli.py``)."""

    def test_summarize_layer_5_failed_alone_returns_one(self):
        # Arrange: layers 1-4 passed, only layer 5 (the run) failed.
        results = _layers([STATE_OK, STATE_OK, STATE_OK, STATE_OK,
                           STATE_FAILED, STATE_OK])

        # Act + Assert: internal class, exit 1 — not the docker class.
        self.assertEqual(_summarize(results), 1)

    def test_summarize_layer_6_failed_alone_returns_one(self):
        # Arrange: layers 1-4 passed, only layer 6 (failure paths) failed.
        results = _layers([STATE_OK, STATE_OK, STATE_OK, STATE_OK,
                           STATE_OK, STATE_FAILED])

        # Act + Assert.
        self.assertEqual(_summarize(results), 1)


class TestSummarizeDockerClassWins(unittest.TestCase):
    """Behaviour 2 (error): when both classes fail, the docker class (4)
    wins over the internal class (1)."""

    def test_summarize_layers_2_and_5_both_failed_returns_four(self):
        # Arrange: layer 2 (docker class) and layer 5 (internal class) both
        # failed, the rest passed.
        results = _layers([STATE_OK, STATE_FAILED, STATE_OK,
                           STATE_OK, STATE_FAILED, STATE_OK])

        # Act + Assert: 4, never 1.
        self.assertEqual(_summarize(results), 4)


class TestSummarizeSkippedNeverContributes(unittest.TestCase):
    """Behaviour 2 (error): a skipped layer never contributes to a
    non-zero exit — a skipped layer 5 must not push the exit to 1."""

    def test_summarize_earlier_layers_failed_layer_5_skipped_returns_four(self):
        # Arrange: layers 1-4 all failed, so layer 5 is reported skipped
        # (never failed), and layer 6 passed.
        results = _layers([STATE_FAILED, STATE_FAILED, STATE_FAILED,
                           STATE_FAILED, STATE_SKIPPED, STATE_OK])

        # Act + Assert: exit 4 from the docker class, never 1 from the
        # skipped layer 5.
        self.assertEqual(_summarize(results), 4)

    def test_summarize_all_six_layers_skipped_returns_zero(self):
        # Arrange: no layer failed — every one is skipped.
        results = _layers([STATE_SKIPPED] * 6)

        # Act + Assert: skipping is not failing.
        self.assertEqual(_summarize(results), 0)


class TestSummarizeUnknownStateCountsAsFailed(unittest.TestCase):
    """Behaviour 2 (design intent): a state that is neither ``"ok"`` nor
    ``"skipped"`` counts as failed, in whatever class its position holds."""

    def test_summarize_unknown_state_at_layer_1_position_returns_four(self):
        # Arrange: layer 1 in an unrecognised state, the rest passed.
        results = _layers(["error", STATE_OK, STATE_OK,
                           STATE_OK, STATE_OK, STATE_OK])

        # Act + Assert: counts as a layer-1 failure, docker class.
        self.assertEqual(_summarize(results), 4)

    def test_summarize_unknown_state_at_layer_6_position_returns_one(self):
        # Arrange: layer 6 in an unrecognised state, the rest passed.
        results = _layers([STATE_OK, STATE_OK, STATE_OK, STATE_OK,
                           STATE_OK, "error"])

        # Act + Assert: counts as a layer-6 failure, internal class.
        self.assertEqual(_summarize(results), 1)


class TestPinnedNameReuse(unittest.TestCase):
    """Behaviour 3 (PIN): ``smoke.py`` adopts the four pinned names from
    ``anvilkit.pi.pisandbox`` rather than re-spelling them as literals."""

    def test_pinned_constants_are_exposed_at_module_level(self):
        # Act: import smoke and look for the four public constants.
        smoke_mod = _require_smoke()

        # Assert: all four public names exist at module level.
        for smoke_name, _pi_name in PINNED_CONSTANTS:
            self.assertTrue(
                hasattr(smoke_mod, smoke_name),
                "anvilkit/smoke.py must expose module constant %s, the "
                "pinned name from anvilkit/pi/pisandbox.py" % smoke_name,
            )

    def test_pinned_constants_equal_the_pisandbox_attributes(self):
        # Arrange: the public smoke names mapped to the pisandbox attributes
        # they must adopt.
        smoke_mod = _require_smoke()

        # Act + Assert: each public constant is exactly the pisandbox value.
        for smoke_name, pi_name in PINNED_CONSTANTS:
            self.assertTrue(
                hasattr(smoke_mod, smoke_name),
                "anvilkit/smoke.py must expose module constant %s" % smoke_name,
            )
            self.assertEqual(
                getattr(smoke_mod, smoke_name),
                getattr(pisandbox, pi_name),
                "%s must be the value of anvilkit.pi.pisandbox.%s, not a "
                "re-spelled literal" % (smoke_name, pi_name),
            )

    def test_source_never_re_spells_the_pinned_literals(self):
        # Arrange: the raw source of anvilkit/smoke.py, located from the
        # module's ``__file__`` (same source-reading approach as the
        # rules-mirror tests).
        smoke_mod = _require_smoke()
        source = Path(smoke_mod.__file__).read_text(encoding="utf-8")

        # Assert: none of the four literal spellings appears anywhere in the
        # source, not even in a comment.
        for literal in PINNED_LITERALS:
            self.assertNotIn(
                literal,
                source,
                "anvilkit/smoke.py re-spells the pinned literal %r; import "
                "it from anvilkit.pi.pisandbox instead" % literal,
            )
    
    
# Behaviour 4: layer 1's daemon check. The plan's docker seam (recorded in
# its Assumptions) is one injected ``docker_runner(argv) -> (exit_code,
# stdout, stderr)`` with list-form argv; this check must take the runner so
# it is testable without Docker installed. The public seam these tests pin:
# ``smoke.check_docker_daemon(docker_runner)`` returns a ``LayerResult``.
DAEMON_CHECK_NAME = "check_docker_daemon"
DAEMON_ARGV = ["docker", "version", "--format", "{{.Server.Version}}"]


def _daemon_check(runner):
    """Call the behaviour-4 daemon check with ``runner`` as its seam."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, DAEMON_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define %s(docker_runner) yet "
            "(behaviour 4 of plans/smoke-test.md)" % DAEMON_CHECK_NAME
        )
    return check(runner)


def _recording_runner(exit_code, stdout, stderr):
    """A fake ``docker_runner`` returning fixed values and recording argv."""
    calls = []

    def runner(argv):
        calls.append(list(argv))
        return (exit_code, stdout, stderr)

    runner.calls = calls
    return runner


class TestDockerDaemonCheckPass(unittest.TestCase):
    """Behaviour 4: exit 0 passes with the server version in the detail."""

    def test_check_docker_daemon_exit_zero_passes_with_version_in_detail(self):
        # Arrange: the injected runner answers the version probe with exit 0.
        runner = _recording_runner(0, "27.1.1\n", "")

        # Act.
        result = _daemon_check(runner)

        # Assert: the layer is the docker-daemon layer, in the pass state,
        # and the detail carries the (trimmed) server version.
        self.assertEqual(result.name, "docker-daemon")
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn("27.1.1", result.detail)

    def test_check_docker_daemon_runs_the_version_probe_in_list_form(self):
        # Arrange: the injected runner records whatever argv it is handed.
        runner = _recording_runner(0, "27.1.1", "")

        # Act.
        _daemon_check(runner)

        # Assert: the check ran exactly the plan's argv, as a list.
        self.assertEqual(runner.calls, [DAEMON_ARGV])


class TestDockerDaemonCheckNonZeroExit(unittest.TestCase):
    """Behaviour 4: a non-zero exit fails with the stderr in the detail."""

    def test_check_docker_daemon_nonzero_exit_fails_with_stderr_in_detail(self):
        # Arrange: the daemon is up but the probe fails non-zero with a
        # stderr message.
        stderr = "Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
        runner = _recording_runner(1, "", stderr)

        # Act.
        result = _daemon_check(runner)

        # Assert: the layer failed, and its detail carries the stderr —
        # not a bare exit code.
        self.assertEqual(result.name, "docker-daemon")
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(stderr, result.detail)


class TestDockerDaemonCheckNotOnPath(unittest.TestCase):
    """Behaviour 4 (error): ``FileNotFoundError`` from the runner is a fail
    saying docker is not on PATH — never a traceback."""

    def test_check_docker_daemon_runner_not_found_fails_saying_not_on_path(self):
        # Arrange: the runner raises ``FileNotFoundError`` as when docker is
        # missing from PATH.
        def runner(argv):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'docker'")

        # Act: the exception must not escape the check — a traceback here
        # fails the test.
        result = _daemon_check(runner)

        # Assert: the layer failed, and its detail says docker is not on PATH.
        self.assertEqual(result.name, "docker-daemon")
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("path", result.detail.lower())


# Behaviour 5: layer 1's pi-sandbox image check. It takes the same
# injected docker seam as behaviour 4 plus an image tag whose default is
# the plan's pinned default ``pi-sandbox``. The public seam these tests
# pin: ``smoke.check_sandbox_image(docker_runner, tag=...)`` returns a
# ``LayerResult``. Its fail fix line is derived as
# ``" ".join(pisandbox.build_argv(tag))`` -- never hand-typed -- so a
# Dockerfile-path change cannot leave the fix stale.
IMAGE_CHECK_NAME = "check_sandbox_image"
DEFAULT_IMAGE_TAG = "pi-sandbox"


def _image_check():
    """Return the behaviour-5 image check, or fail naming what is missing."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, IMAGE_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define %s(docker_runner, tag=...) yet "
            "(behaviour 5 of plans/smoke-test.md)" % IMAGE_CHECK_NAME
        )
    return check


def _inspect_argv(tag):
    """The list-form argv layer 1 uses to inspect the image for ``tag``."""
    return ["docker", "image", "inspect", tag]


def _derived_fix_line(tag):
    """The fix line computed from ``pisandbox.build_argv``.

    The test derives the expected fix line from the same public builder
    the implementation must call, which is what proves the
    derived-not-hand-typed rule rather than pinning a string that a
    Dockerfile-path change could leave stale.
    """
    return " ".join(pisandbox.build_argv(tag))


class TestSandboxImageCheckPass(unittest.TestCase):
    """Behaviour 5: exit 0 from the image inspect is the pass state."""

    def test_check_sandbox_image_exit_zero_passes(self):
        # Arrange: the injected runner answers the image inspect with
        # exit 0.
        runner = _recording_runner(0, "", "")

        # Act.
        result = _image_check()(runner, "anvil-pi:dev")

        # Assert: the layer is in the pass state.
        self.assertEqual(result.ok, STATE_OK)

    def test_check_sandbox_image_default_tag_inspects_pi_sandbox(self):
        # Arrange: the injected runner records whatever argv it is handed.
        runner = _recording_runner(0, "", "")

        # Act: no tag passed -- the check's default must apply.
        _image_check()(runner)

        # Assert: the default tag is the plan's pinned ``pi-sandbox``,
        # inspected through the plan's list-form argv, exactly once.
        self.assertEqual(runner.calls, [_inspect_argv("pi-sandbox")])


class TestSandboxImageCheckFail(unittest.TestCase):
    """Behaviour 5: a non-zero inspect exit fails with exactly one fix
    line, the derived build argv."""

    def test_check_sandbox_image_nonzero_exit_fails_with_derived_fix_line_explicit_tag(self):
        # Arrange: the image inspect fails for an explicit, non-default
        # tag.
        tag = "anvil-pi:dev"
        runner = _recording_runner(
            1, "", "Error: No such image: %s" % tag
        )

        # Act.
        result = _image_check()(runner, tag)

        # Assert: the layer failed, and its fix lines are exactly the one
        # derived from ``pisandbox.build_argv(tag)`` -- computed here, not
        # hand-typed, so check and fix cannot desynchronise.
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertEqual(tuple(result.fix_lines), (_derived_fix_line(tag),))

    def test_check_sandbox_image_nonzero_exit_fails_with_derived_fix_line_default_tag(self):
        # Arrange: the image inspect fails and no tag is passed, so the
        # default tag must drive the fix line.
        runner = _recording_runner(
            1, "", "Error: No such image: pi-sandbox"
        )

        # Act.
        result = _image_check()(runner)

        # Assert: the fix line is derived from the default tag.
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertEqual(
            tuple(result.fix_lines), (_derived_fix_line(DEFAULT_IMAGE_TAG),)
        )


class TestSandboxImageCheckArgv(unittest.TestCase):
    """Behaviour 5: the check invokes the runner with the list-form
    ``docker image inspect <tag>`` argv, exactly once."""

    def test_check_sandbox_image_invokes_inspect_argv_in_list_form(self):
        # Arrange: the injected runner records whatever argv it is handed.
        tag = "anvil-pi:dev"
        runner = _recording_runner(0, "", "")

        # Act.
        _image_check()(runner, tag)

        # Assert: the check ran exactly the plan's argv, as a list, once.
        self.assertEqual(runner.calls, [_inspect_argv(tag)])


# Behaviour 6: layer 1's internal-network-presence check. It takes the
# same injected docker seam as behaviours 4 and 5. The public seam these
# tests pin: ``smoke.check_sandbox_network(docker_runner)`` returns a
# ``LayerResult``. The network name must come from the module's adopted
# ``INTERNAL_NETWORK`` constant, so a rename in ``pisandbox`` keeps the
# check and the run in step.
NETWORK_CHECK_NAME = "check_sandbox_network"
# The plan's pinned fix command for a missing network: the compose-up that
# creates it. The plan pins the command; the wording that names compose as
# its creator is free, which is why the test asserts the command itself and
# a create-verb reference separately.
NETWORK_FIX_COMMAND = "docker compose --profile coder up -d"


def _network_check():
   """Return the behaviour-6 network check, or fail naming what is missing."""
   smoke_mod = _require_smoke()
   check = getattr(smoke_mod, NETWORK_CHECK_NAME, None)
   if check is None:
       raise AssertionError(
           "anvilkit.smoke does not define %s(docker_runner) yet "
           "(behaviour 6 of plans/smoke-test.md)" % NETWORK_CHECK_NAME
       )
   return check


def _network_argv():
   """The list-form argv layer 1 uses to inspect the internal network.

   The name is read from ``smoke.INTERNAL_NETWORK`` -- the constant
   adopted from ``anvilkit.pi.pisandbox._INTERNAL_NETWORK`` -- so this
   test proves the check inspects the adopted name, not a re-spelled
   literal.
   """
   smoke_mod = _require_smoke()
   return ["docker", "network", "inspect", smoke_mod.INTERNAL_NETWORK]


class TestSandboxNetworkCheckPass(unittest.TestCase):
   """Behaviour 6: exit 0 from the network inspect is the pass state."""

   def test_check_sandbox_network_exit_zero_passes(self):
       # Arrange: the injected runner answers the network inspect with
       # exit 0.
       runner = _recording_runner(0, "", "")

       # Act.
       result = _network_check()(runner)

       # Assert: the layer is the sandbox-network layer, in the pass state.
       self.assertEqual(result.name, "sandbox-network")
       self.assertEqual(result.ok, STATE_OK)


class TestSandboxNetworkCheckArgv(unittest.TestCase):
   """Behaviour 6: the check invokes the runner with the list-form
   ``docker network inspect <name>`` argv, exactly once, where ``<name>``
   is the module's adopted ``INTERNAL_NETWORK`` constant."""

   def test_check_sandbox_network_invokes_inspect_argv_with_adopted_name(self):
       # Arrange: the injected runner records whatever argv it is handed.
       runner = _recording_runner(0, "", "")

       # Act.
       _network_check()(runner)

       # Assert: the check ran exactly the plan's argv, as a list, once,
       # with the name read from the adopted constant.
       self.assertEqual(runner.calls, [_network_argv()])


class TestSandboxNetworkCheckFail(unittest.TestCase):
   """Behaviour 6: a non-zero inspect exit fails with the compose-up fix
   line, which names that compose creates the network."""

   def test_check_sandbox_network_nonzero_exit_fails_with_compose_up_fix_line(self):
       # Arrange: the network inspect fails non-zero with a stderr
       # message.
       runner = _recording_runner(
           1, "", "Error: network \"sandbox-internal\" not found"
       )

       # Act.
       result = _network_check()(runner)

       # Assert: the layer is the sandbox-network layer in the fail state,
       # and one fix line carries the plan's pinned compose-up command.
       self.assertEqual(result.name, "sandbox-network")
       self.assertEqual(result.ok, STATE_FAILED)
       self.assertTrue(
           any(NETWORK_FIX_COMMAND in fix for fix in result.fix_lines),
           "fix lines %r must include the compose-up command %r"
           % (result.fix_lines, NETWORK_FIX_COMMAND),
       )

   def test_check_sandbox_network_fix_lines_name_that_compose_creates_the_network(self):
       # Arrange: the network inspect fails non-zero.
       runner = _recording_runner(1, "", "network not found")

       # Act.
       result = _network_check()(runner)

       # Assert: beyond the pinned command, the fix text says compose
       # creates the network -- a create-verb is the load-bearing word,
       # since the command itself contains no such verb.
       joined = " ".join(result.fix_lines).lower()
       self.assertIn(NETWORK_FIX_COMMAND.lower(), joined)
       self.assertIn(
           "creat",
           joined,
           "fix lines %r must name that compose creates the network"
           % (result.fix_lines,),
       )


class TestSandboxNetworkCheckNotOnPath(unittest.TestCase):
   """Behaviour 6 (error): ``FileNotFoundError`` from the runner is a
   not-on-PATH fail, never a traceback."""

   def test_check_sandbox_network_runner_not_found_fails_saying_not_on_path(self):
       # Arrange: the runner raises ``FileNotFoundError`` as when docker
       # is missing from PATH.
       def runner(argv):
           raise FileNotFoundError("[Errno 2] No such file or directory: 'docker'")

       # Act: the exception must not escape the check -- a traceback here
       # fails the test.
       result = _network_check()(runner)

       # Assert: the layer failed, and its detail says docker is not on
       # PATH.
       self.assertEqual(result.name, "sandbox-network")
       self.assertEqual(result.ok, STATE_FAILED)
       self.assertIn("path", result.detail.lower())


# Behaviour 7: layer 2's gateway container check. It takes the same
# injected docker seam as behaviours 4-6. The public seam these tests
# pin: ``smoke.check_gateway_container(docker_runner)`` returns a
# ``LayerResult`` named ``"gateway-container"``. The container name must
# come from a module-level constant ``GATEWAY_CONTAINER`` equal to the
# ``container_name`` from ``docker-compose.yml`` (``llama-swap-service``);
# ``llama-swap`` is the service/DNS name only and must never be the
# match. The check matches a line of the ``docker ps`` output that equals
# the container name exactly (after stripping surrounding whitespace) --
# never a substring.
GATEWAY_CHECK_NAME = "check_gateway_container"
GATEWAY_LAYER_NAME = "gateway-container"
GATEWAY_CONTAINER_NAME = "llama-swap-service"
# The plan's pinned fix command for a missing gateway container: the
# compose-up that starts it. The test pins the command string itself, not
# any reuse of another module constant.
GATEWAY_FIX_COMMAND = "docker compose --profile coder up -d"


def _gateway_check():
    """Return the behaviour-7 gateway container check, or fail naming what
    is missing."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, GATEWAY_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define %s(docker_runner) yet "
            "(behaviour 7 of plans/smoke-test.md)" % GATEWAY_CHECK_NAME
        )
    return check


def _gateway_container():
    """The container name read from the module's ``GATEWAY_CONTAINER``
    constant, or fail naming the missing constant.

    The argv test builds its expected argv from this constant rather than
    a re-spelled literal, so it proves the check filters on the adopted
    name.
    """
    smoke_mod = _require_smoke()
    container = getattr(smoke_mod, "GATEWAY_CONTAINER", None)
    if container is None:
        raise AssertionError(
            "anvilkit.smoke does not expose module constant GATEWAY_CONTAINER "
            "(behaviour 7 of plans/smoke-test.md)"
        )
    return container


def _gateway_argv(container):
    """The list-form argv layer 2 uses to list the gateway container.

    The filter value is ``name=<container>`` -- never a ``--name`` flag --
    per the plan.
    """
    return [
        "docker",
        "ps",
        "--filter",
        "name=" + container,
        "--format",
        "{{.Names}}",
    ]


class TestGatewayContainerConstant(unittest.TestCase):
    """Behaviour 7 (PIN): the container name is pinned as the module-level
    constant ``GATEWAY_CONTAINER``, the ``container_name`` from
    ``docker-compose.yml`` -- not the service/DNS name."""

    def test_gateway_container_constant_is_the_compose_container_name(self):
        # Act: read the constant from the smoke module.
        smoke_mod = _require_smoke()

        # Assert: the constant exists and is exactly the compose
        # container_name -- never the service/DNS name ``llama-swap``.
        self.assertTrue(
            hasattr(smoke_mod, "GATEWAY_CONTAINER"),
            "anvilkit/smoke.py must expose module constant GATEWAY_CONTAINER, "
            "the container_name from docker-compose.yml",
        )
        self.assertEqual(
            smoke_mod.GATEWAY_CONTAINER,
            GATEWAY_CONTAINER_NAME,
            "GATEWAY_CONTAINER must be the compose container_name %r, not a "
            "re-spelled or service-name literal" % GATEWAY_CONTAINER_NAME,
        )


class TestGatewayContainerCheckPass(unittest.TestCase):
    """Behaviour 7: a ``docker ps`` line that equals the container name
    exactly (after stripping) is the pass state."""

    def test_check_gateway_container_exit_zero_with_exact_line_passes(self):
        # Arrange: the runner answers with a single exact container-name
        # line.
        runner = _recording_runner(0, "llama-swap-service\n", "")

        # Act.
        result = _gateway_check()(runner)

        # Assert: the layer is the gateway-container layer in the pass
        # state.
        self.assertEqual(result.name, GATEWAY_LAYER_NAME)
        self.assertEqual(result.ok, STATE_OK)

    def test_check_gateway_container_exit_zero_with_exact_line_among_others_passes(self):
        # Arrange: the exact container-name line sits among other running
        # container names.
        stdout = "coder_qdrant-service\nllama-swap-service\nother-container\n"
        runner = _recording_runner(0, stdout, "")

        # Act.
        result = _gateway_check()(runner)

        # Assert: the exact line still passes, even with neighbours.
        self.assertEqual(result.name, GATEWAY_LAYER_NAME)
        self.assertEqual(result.ok, STATE_OK)


class TestGatewayContainerCheckExactPerLine(unittest.TestCase):
    """Behaviour 7 (error): the match is exact per line, never a
    substring -- ``llama-swap-service-old`` alone is a fail."""

    def test_check_gateway_container_exit_zero_with_superset_name_only_fails(self):
        # Arrange: the only line is a longer name that contains the
        # container name as a substring.
        runner = _recording_runner(0, "llama-swap-service-old\n", "")

        # Act.
        result = _gateway_check()(runner)

        # Assert: a substring is not a match -- the layer failed.
        self.assertEqual(result.name, GATEWAY_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)


class TestGatewayContainerCheckFail(unittest.TestCase):
    """Behaviour 7: a non-zero exit or an output with no exact line fails
    with the compose-up fix line."""

    def test_check_gateway_container_nonzero_exit_fails_with_compose_up_fix_line(self):
        # Arrange: the ``docker ps`` invocation fails non-zero with a
        # stderr message.
        runner = _recording_runner(1, "", "Error: something went wrong")

        # Act.
        result = _gateway_check()(runner)

        # Assert: the layer is the gateway-container layer in the fail
        # state, and one fix line carries the plan's pinned compose-up
        # command.
        self.assertEqual(result.name, GATEWAY_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertTrue(
            any(GATEWAY_FIX_COMMAND in fix for fix in result.fix_lines),
            "fix lines %r must include the compose-up command %r"
            % (result.fix_lines, GATEWAY_FIX_COMMAND),
        )

    def test_check_gateway_container_exit_zero_empty_output_fails_with_compose_up_fix_line(self):
        # Arrange: the daemon answers but nothing is running.
        runner = _recording_runner(0, "", "")

        # Act.
        result = _gateway_check()(runner)

        # Assert: empty output is a fail, with the compose-up fix line.
        self.assertEqual(result.name, GATEWAY_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertTrue(
            any(GATEWAY_FIX_COMMAND in fix for fix in result.fix_lines),
            "fix lines %r must include the compose-up command %r"
            % (result.fix_lines, GATEWAY_FIX_COMMAND),
        )


class TestGatewayContainerCheckArgv(unittest.TestCase):
    """Behaviour 7: the check invokes the runner with the list-form
    ``docker ps --filter name=<container> --format {{.Names}}`` argv,
    exactly once, where ``<container>`` is the module's
    ``GATEWAY_CONTAINER`` constant."""

    def test_check_gateway_container_invokes_ps_argv_in_list_form(self):
        # Arrange: the injected runner records whatever argv it is handed.
        runner = _recording_runner(0, "llama-swap-service\n", "")

        # Act.
        _gateway_check()(runner)

        # Assert: the check ran exactly the plan's argv, as a list, once,
        # with the filter value read from the adopted constant -- not a
        # ``--name`` flag.
        self.assertEqual(runner.calls, [_gateway_argv(_gateway_container())])


class TestGatewayContainerCheckNotOnPath(unittest.TestCase):
    """Behaviour 7 (error): ``FileNotFoundError`` from the runner is a
    not-on-PATH fail, never a traceback."""

    def test_check_gateway_container_runner_not_found_fails_saying_not_on_path(self):
        # Arrange: the runner raises ``FileNotFoundError`` as when docker
        # is missing from PATH.
        def runner(argv):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'docker'")

        # Act: the exception must not escape the check -- a traceback here
        # fails the test.
        result = _gateway_check()(runner)

        # Assert: the layer is the gateway-container layer in the fail
        # state, and its detail says docker is not on PATH.
        self.assertEqual(result.name, GATEWAY_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("path", result.detail.lower())


# Behaviour 8: layer 2's coder-model-registered-and-hot check. Unlike
# behaviours 4-7 it does not run docker; it reuses two in-repo collaborators
# that the plan names: ``health.check_gateway`` and ``config.read_models``.
# The public seam these tests pin:
#
#     smoke.check_gateway_model(port, config_path,
#                               check_gateway=..., read_models=...)
#
# returns a ``LayerResult`` named ``"gateway-model"``. ``port`` is the resolved
# host port; ``config_path`` is the path to llama-swap's read-only
# ``config.yaml`` whose ``matrix.vars.coder`` supplies the model id. Both
# collaborators are injectable callables defaulting to the real
# ``health.check_gateway`` and ``config.read_models``; the tests inject fakes
# for both so no network and no file is touched.
#
# The plan pins one fact the report always states, on pass and on every fail:
# the in-network port is 8080 regardless of the host ``LLM_PORT``. The exact
# wording is free, so the test pins the load-bearing token ``8080``.
#
# The three failure modes -- offline, id absent, id present-but-cold -- must be
# three distinct details. The test pins one stable marker word each
# (``OFFLINE_MARKER``, ``ABSENT_MARKER``, ``COLD_MARKER``) and asserts all
# three details carry a different marker, so the layer cannot collapse two
# modes into one detail.
MODEL_CHECK_NAME = "check_gateway_model"
MODEL_LAYER_NAME = "gateway-model"
# The plan's pinned in-network fact, asserted as a load-bearing token.
IN_NETWORK_PORT = "8080"
# One stable marker word per failure mode, pinned here so the three fail
# details are asserted to be distinguishable from each other.
OFFLINE_MARKER = "offline"
ABSENT_MARKER = "not registered"
COLD_MARKER = "cold"


def _model_check():
    """Return the behaviour-8 model check, or fail naming what is missing."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, MODEL_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define %s(port, config_path, "
            "check_gateway=..., read_models=...) yet "
            "(behaviour 8 of plans/smoke-test.md)" % MODEL_CHECK_NAME
        )
    return check


class _FakeTopology(object):
    """A stand-in for ``config.ModelTopology``: only ``coder_id`` is read."""

    def __init__(self, coder_id):
        self.coder_id = coder_id


class _FakeModel(object):
    """A stand-in for ``health.ModelStatus``: ``id`` and ``hot``."""

    def __init__(self, id, hot):
        self.id = id
        self.hot = hot


class _FakeGatewayStatus(object):
    """A stand-in for ``health.GatewayStatus``: ``online``, ``models``,
    ``error``."""

    def __init__(self, online, models, error=None):
        self.online = online
        self.models = list(models)
        self.error = error


def _fake_read_models(coder_id):
    """A ``read_models`` fake returning a topology with ``coder_id``.

    Records its calls so a test can assert the check read the config the
    caller named, and that it never hard-coded the id.
    """
    calls = []

    def read_models(path, strict_context_window=False):
        calls.append((path, strict_context_window))
        return _FakeTopology(coder_id)

    read_models.calls = calls
    return read_models


def _fake_check_gateway(status):
    """A ``check_gateway`` fake returning ``status`` and recording its port."""
    calls = []

    def check_gateway(port, timeout=2.0):
        calls.append(port)
        return status

    check_gateway.calls = calls
    return check_gateway


class TestGatewayModelCheckPass(unittest.TestCase):
    """Behaviour 8: the coder id present and hot passes, and the detail
    states the in-network port is 8080."""

    def test_check_gateway_model_id_present_and_hot_passes(self):
        # Arrange: the coder id comes from the fake topology, the gateway is
        # online and that id is hot.
        coder_id = "meta-llama/Llama-3.1-8B-Instruct"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True,
            models=[_FakeModel(coder_id, True)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the layer is the gateway-model layer in the pass state.
        self.assertEqual(result.name, MODEL_LAYER_NAME)
        self.assertEqual(result.ok, STATE_OK)

    def test_check_gateway_model_pass_detail_states_in_network_port_8080(self):
        # Arrange: a passing gateway (id hot).
        coder_id = "some-coder-model"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True, models=[_FakeModel(coder_id, True)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the report always states the in-network port is 8080, on
        # the pass detail too -- pinned to the load-bearing token.
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn(
            IN_NETWORK_PORT,
            result.detail,
            "pass detail %r must state the in-network port is %s"
            % (result.detail, IN_NETWORK_PORT),
        )

    def test_check_gateway_model_pass_detail_names_the_coder_id(self):
        # Arrange: the coder id is supplied by the fake topology, not
        # hard-coded in the check.
        coder_id = "the-supplied-coder-id"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True, models=[_FakeModel(coder_id, True)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the pass detail carries the id the fake read_models
        # supplied, proving the id is derived from config.yaml, not
        # hard-coded.
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn(coder_id, result.detail)


class TestGatewayModelCheckOffline(unittest.TestCase):
    """Behaviour 8 (error): an offline gateway fails with an offline detail
    carrying ``status.error`` when present, plus the in-network fact."""

    def test_check_gateway_model_offline_fails_with_offline_detail(self):
        # Arrange: the gateway reports offline with an error string.
        coder_id = "some-coder-model"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=False, models=[],
            error="Connection refused on port 18080",
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the layer failed with the offline marker, carrying the
        # gateway error and the in-network fact.
        self.assertEqual(result.name, MODEL_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(OFFLINE_MARKER, result.detail.lower())
        self.assertIn("Connection refused", result.detail)
        self.assertIn(IN_NETWORK_PORT, result.detail)


class TestGatewayModelCheckIdAbsent(unittest.TestCase):
    """Behaviour 8 (error): online but the coder id absent from the registry
    fails with an id-absent detail naming the id, plus the in-network fact."""

    def test_check_gateway_model_id_absent_fails_naming_the_id(self):
        # Arrange: the gateway is online but registers a different model,
        # not the coder id the config names.
        coder_id = "the-coder-from-config"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True, models=[_FakeModel("some-other-model", True)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the layer failed with the id-absent marker, naming the
        # coder id from config.yaml, plus the in-network fact.
        self.assertEqual(result.name, MODEL_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(ABSENT_MARKER, result.detail.lower())
        self.assertIn(coder_id, result.detail)
        self.assertIn(IN_NETWORK_PORT, result.detail)


class TestGatewayModelCheckCold(unittest.TestCase):
    """Behaviour 8 (error): online and the id present but not hot fails with
    a cold detail, plus the in-network fact."""

    def test_check_gateway_model_id_present_but_cold_fails(self):
        # Arrange: the gateway is online and registers the coder id, but it
        # is not loaded (cold).
        coder_id = "the-coder-from-config"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True, models=[_FakeModel(coder_id, False)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the layer failed with the cold marker, naming the id, plus
        # the in-network fact.
        self.assertEqual(result.name, MODEL_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(COLD_MARKER, result.detail.lower())
        self.assertIn(coder_id, result.detail)
        self.assertIn(IN_NETWORK_PORT, result.detail)


class TestGatewayModelCheckThreeDistinctDetails(unittest.TestCase):
    """Behaviour 8 (error): the three failure details -- offline, id absent,
    id present-but-cold -- are distinguishable from each other, each carrying
    the in-network port fact."""

    def _detail(self, status):
        read_models = _fake_read_models("the-coder-from-config")
        check_gateway = _fake_check_gateway(status)
        return _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        ).detail

    def test_three_failure_details_are_pairwise_distinct(self):
        # Arrange: one gateway status per failure mode.
        offline = self._detail(_FakeGatewayStatus(
            online=False, models=[], error="conn refused"))
        absent = self._detail(_FakeGatewayStatus(
            online=True, models=[_FakeModel("some-other-model", True)]))
        cold = self._detail(_FakeGatewayStatus(
            online=True,
            models=[_FakeModel("the-coder-from-config", False)]))

        # Assert: each detail carries its own marker, and all three carry the
        # in-network fact.
        self.assertIn(OFFLINE_MARKER, offline.lower())
        self.assertIn(ABSENT_MARKER, absent.lower())
        self.assertIn(COLD_MARKER, cold.lower())
        for detail in (offline, absent, cold):
            self.assertIn(IN_NETWORK_PORT, detail)

    def test_three_failure_details_are_not_all_identical(self):
        # Arrange: the three failure details as above.
        offline = self._detail(_FakeGatewayStatus(
            online=False, models=[], error="conn refused"))
        absent = self._detail(_FakeGatewayStatus(
            online=True, models=[_FakeModel("some-other-model", True)]))
        cold = self._detail(_FakeGatewayStatus(
            online=True,
            models=[_FakeModel("the-coder-from-config", False)]))

        # Assert: no two failure modes collapse into the same detail.
        self.assertNotEqual(offline, absent)
        self.assertNotEqual(offline, cold)
        self.assertNotEqual(absent, cold)


class TestGatewayModelCheckConfigError(unittest.TestCase):
    """Behaviour 8 (error): a ``ConfigError`` from ``read_models`` fails the
    layer naming the file, never a traceback."""

    def test_check_gateway_model_config_error_fails_naming_the_file(self):
        # Arrange: the read_models fake raises ``ConfigError`` for a named
        # file, as when matrix.vars.coder is missing.
        from anvilkit.config import ConfigError

        config_path = "config.yaml"

        def read_models(path, strict_context_window=False):
            raise ConfigError(
                "matrix.vars.coder is not defined in %s" % path
            )

        status = _FakeGatewayStatus(online=True, models=[])
        check_gateway = _fake_check_gateway(status)

        # Act: the exception must not escape the check -- a traceback here
        # fails the test.
        result = _model_check()(
            18080, config_path,
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the layer failed naming the file, with the in-network fact.
        self.assertEqual(result.name, MODEL_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(config_path, result.detail)
        self.assertIn(IN_NETWORK_PORT, result.detail)


class TestGatewayModelCheckSeam(unittest.TestCase):
    """Behaviour 8 (seam): the check calls the injected ``check_gateway``
    with the resolved port and reads the id from the injected
    ``read_models`` -- never a hard-coded id."""

    def test_check_gateway_model_passes_the_resolved_port_to_check_gateway(self):
        # Arrange: a recording check_gateway and a read_models supplying an
        # id that also appears in the gateway.
        coder_id = "the-coder-from-config"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True, models=[_FakeModel(coder_id, True)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the check called check_gateway exactly once, with the
        # resolved port.
        self.assertEqual(check_gateway.calls, [18080])

    def test_check_gateway_model_reads_the_id_from_read_models(self):
        # Arrange: a read_models supplying a slash-carrying id that also
        # appears in the gateway; a second, hard-codeable-looking id that
        # must not be the one matched.
        coder_id = "org/repo/model-v2"
        read_models = _fake_read_models(coder_id)
        status = _FakeGatewayStatus(
            online=True,
            models=[_FakeModel("org/repo/model-v1", True),
                    _FakeModel(coder_id, True)],
        )
        check_gateway = _fake_check_gateway(status)

        # Act.
        result = _model_check()(
            18080, "config.yaml",
            check_gateway=check_gateway, read_models=read_models,
        )

        # Assert: the check matched the id read from config.yaml (the v2 id),
        # not a re-spelled literal, and read the config the caller named.
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn(coder_id, result.detail)
        self.assertEqual(
            read_models.calls, [("config.yaml", False)],
            "read_models must be called with the config path the caller "
            "named",
        )


# Behaviour 9: layer 3's agent-volume-presence check. It takes the same
# injected docker seam as behaviours 4-7. The public seam these tests
# pin: ``smoke.check_agent_volume(docker_runner)`` returns a
# ``LayerResult`` named ``"agent-volume"``. The volume name must come
# from the module's adopted ``NAMED_VOLUME`` constant, so a rename in
# ``pisandbox`` keeps the check and the run in step. Exit 0 is the pass
# state; a non-zero exit is the fail state whose detail says the volume
# is created on first run and stays empty until seeded. The exact
# wording is free, so the test pins two load-bearing marker words:
# ``first run`` and ``empty``.
VOLUME_CHECK_NAME = "check_agent_volume"
VOLUME_LAYER_NAME = "agent-volume"
# The two marker words the plan's fail detail must carry, pinned here so
# the explanation cannot be dropped or reworded into something that no
# longer says "created on first run" and "stays empty until seeded".
FIRST_RUN_MARKER = "first run"
EMPTY_VOLUME_MARKER = "empty"


def _volume_check():
    """Return the behaviour-9 volume check, or fail naming what is missing."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, VOLUME_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define %s(docker_runner) yet "
            "(behaviour 9 of plans/smoke-test.md)" % VOLUME_CHECK_NAME
        )
    return check


def _volume_argv():
    """The list-form argv layer 3 uses to inspect the agent volume.

    The name is read from ``smoke.NAMED_VOLUME`` -- the constant adopted
    from ``anvilkit.pi.pisandbox._NAMED_VOLUME`` -- so this test proves
    the check inspects the adopted name, not a re-spelled literal.
    """
    smoke_mod = _require_smoke()
    return ["docker", "volume", "inspect", smoke_mod.NAMED_VOLUME]


class TestAgentVolumeCheckPass(unittest.TestCase):
    """Behaviour 9: exit 0 from the volume inspect is the pass state."""

    def test_check_agent_volume_exit_zero_passes(self):
        # Arrange: the injected runner answers the volume inspect with
        # exit 0.
        runner = _recording_runner(0, "", "")

        # Act.
        result = _volume_check()(runner)

        # Assert: the layer is the agent-volume layer, in the pass state.
        self.assertEqual(result.name, VOLUME_LAYER_NAME)
        self.assertEqual(result.ok, STATE_OK)


class TestAgentVolumeCheckArgv(unittest.TestCase):
    """Behaviour 9: the check invokes the runner with the list-form
    ``docker volume inspect <name>`` argv, exactly once, where ``<name>``
    is the module's adopted ``NAMED_VOLUME`` constant."""

    def test_check_agent_volume_invokes_inspect_argv_with_adopted_name(self):
        # Arrange: the injected runner records whatever argv it is handed.
        runner = _recording_runner(0, "", "")

        # Act.
        _volume_check()(runner)

        # Assert: the check ran exactly the plan's argv, as a list, once,
        # with the name read from the adopted constant.
        self.assertEqual(runner.calls, [_volume_argv()])


class TestAgentVolumeCheckFail(unittest.TestCase):
    """Behaviour 9: a non-zero inspect exit fails with a detail saying the
    volume is created on first run and stays empty until seeded."""

    def test_check_agent_volume_nonzero_exit_fails_saying_created_on_first_run_and_stays_empty(self):
        # Arrange: the volume inspect fails non-zero.
        runner = _recording_runner(1, "", "Error: No such volume")

        # Act.
        result = _volume_check()(runner)

        # Assert: the layer is the agent-volume layer in the fail state,
        # and its detail carries both pinned marker words -- "created on
        # first run" and "stays empty until seeded".
        self.assertEqual(result.name, VOLUME_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        detail = result.detail.lower()
        self.assertIn(
            FIRST_RUN_MARKER,
            detail,
            "fail detail %r must say the volume is created on first run"
            % (result.detail,),
        )
        self.assertIn(
            EMPTY_VOLUME_MARKER,
            detail,
            "fail detail %r must say the volume stays empty until seeded"
            % (result.detail,),
        )


class TestAgentVolumeCheckNotOnPath(unittest.TestCase):
    """Behaviour 9 (error): ``FileNotFoundError`` from the runner is a
    not-on-PATH fail, never a traceback."""

    def test_check_agent_volume_runner_not_found_fails_saying_not_on_path(self):
        # Arrange: the runner raises ``FileNotFoundError`` as when docker
        # is missing from PATH.
        def runner(argv):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'docker'")

        # Act: the exception must not escape the check -- a traceback here
        # fails the test.
        result = _volume_check()(runner)

        # Assert: the layer failed, and its detail says docker is not on
        # PATH.
        self.assertEqual(result.name, VOLUME_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("path", result.detail.lower())


# Behaviour 10: layer 3's models.json-readability check. It takes the
# same injected docker seam as behaviours 4-7 plus an image tag whose
# default is the module's ``DEFAULT_IMAGE_TAG``. The public seam these
# tests pin:
#
#     smoke.check_models_json(docker_runner, tag=...)
#         -> (LayerResult, Optional[str])
#
# The ``LayerResult`` is named ``"models-json"``; the ``Optional[str]``
# carries the models.json text the in-container cat printed, exposed so
# behaviour 11 can parse it for the coder id -- the exact stdout on a
# pass, ``None`` on every fail. The check runs exactly one list-form
# argv whose names all come from the adopted constants. The two
# non-zero-exit failure modes are told apart by the runner's stderr
# content: a permission marker (``PERMISSION_MARKER``) fails with the
# chown one-liner as its fix line; a no-such-file marker
# (``NO_SUCH_FILE_MARKER``) fails with the seed instruction and no
# chown line. A readable but empty file (exit 0, empty or
# whitespace-only stdout) fails as ``UNSEEDED_MARKER``, a third,
# distinct detail.
MODELS_JSON_CHECK_NAME = "check_models_json"
MODELS_JSON_LAYER_NAME = "models-json"
# The marker the permission-denied stderr must carry, matched
# case-insensitively; the fixture stderr is built to contain it.
PERMISSION_MARKER = "permission"
# The marker the no-such-file stderr must carry, matched
# case-insensitively; the fixture stderr is built to contain it.
NO_SUCH_FILE_MARKER = "no such file"
# The marker word the unseeded (empty-file) fail detail must carry,
# pinned so it cannot collapse into the permission or no-file details.
UNSEEDED_MARKER = "unseeded"
# The marker word the no-such-file fail detail must carry, pinned so
# the missing file is told apart from the misowned one.
SEED_MARKER = "seed"


def _models_json_check():
    """Return the behaviour-10 models.json check, or fail naming what
    is missing."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, MODELS_JSON_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define %s(docker_runner, tag=...) yet "
            "(behaviour 10 of plans/smoke-test.md)" % MODELS_JSON_CHECK_NAME
        )
    return check


def _models_json_argv(tag):
    """The list-form argv layer 3 uses to cat the agent's models.json.

    Every name is read from the adopted smoke constants -- the named
    volume, the agent home and the image uid -- so this test proves the
    check builds its argv from the adopted names, not re-spelled
    literals.
    """
    smoke_mod = _require_smoke()
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        smoke_mod.NAMED_VOLUME + ":" + smoke_mod.AGENT_HOME,
        "--user",
        smoke_mod.IMAGE_UID,
        tag,
        "cat",
        smoke_mod.AGENT_HOME + "/models.json",
    ]


def _chown_one_liner(tag):
    """The chown one-liner the permission fail must offer as a fix.

    Composed from the adopted smoke constants; only the root user id and
    the ``chown`` verb are literals, per the plan.
    """
    smoke_mod = _require_smoke()
    return " ".join([
        "docker",
        "run",
        "--rm",
        "-v",
        smoke_mod.NAMED_VOLUME + ":" + smoke_mod.AGENT_HOME,
        "--user",
        "0",
        tag,
        "chown",
        "-R",
        smoke_mod.IMAGE_UID + ":" + smoke_mod.IMAGE_UID,
        smoke_mod.AGENT_HOME,
    ])


class TestModelsJsonCheckPass(unittest.TestCase):
    """Behaviour 10: exit 0 with non-empty stdout passes, and the read
    text is exposed through the seam for behaviour 11 to parse."""

    def test_check_models_json_exit_zero_non_empty_stdout_passes_and_exposes_content(self):
        # Arrange: the in-container cat answers exit 0 with a seeded file;
        # the trailing newline proves the exposed text is the exact
        # stdout, not a stripped copy.
        models_text = '{"providers": {"a": {"models": [{"id": "x"}]}}}\n'
        runner = _recording_runner(0, models_text, "")

        # Act: the pinned seam returns (LayerResult, Optional[str]).
        result, content = _models_json_check()(runner)

        # Assert: the layer is the models-json layer in the pass state,
        # and the seam exposes the exact stdout for behaviour 11.
        self.assertEqual(result.name, MODELS_JSON_LAYER_NAME)
        self.assertEqual(result.ok, STATE_OK)
        self.assertEqual(content, models_text)


class TestModelsJsonCheckArgv(unittest.TestCase):
    """Behaviour 10: the check invokes the runner with the list-form
    ``docker run --rm -v <volume>:<agent home> --user <uid> <tag> cat
    <agent home>/models.json`` argv, exactly once, every name from the
    adopted constants."""

    def test_check_models_json_default_tag_invokes_cat_argv_in_list_form(self):
        # Arrange: the injected runner records whatever argv it is handed.
        runner = _recording_runner(0, "{}\n", "")

        # Act: no tag passed -- the module's DEFAULT_IMAGE_TAG must apply.
        _models_json_check()(runner)

        # Assert: the check ran exactly the plan's argv, as a list, once,
        # with the names read from the adopted constants and the tag read
        # from the module's own default.
        smoke_mod = _require_smoke()
        self.assertEqual(
            runner.calls, [_models_json_argv(smoke_mod.DEFAULT_IMAGE_TAG)]
        )

    def test_check_models_json_explicit_tag_invokes_cat_argv_with_that_tag(self):
        # Arrange: the injected runner records whatever argv it is handed.
        tag = "anvil-pi:dev"
        runner = _recording_runner(0, "{}\n", "")

        # Act.
        _models_json_check()(runner, tag)

        # Assert: the explicit tag is the image the cat runs in.
        self.assertEqual(runner.calls, [_models_json_argv(tag)])


class TestModelsJsonCheckUnseeded(unittest.TestCase):
    """Behaviour 10 (error): exit 0 with an empty or whitespace-only
    stdout fails as unseeded -- a distinct detail, distinct from the
    permission and no-file fails -- and exposes no content."""

    def test_check_models_json_exit_zero_empty_stdout_fails_as_unseeded(self):
        # Arrange: cat reads a file that exists but is empty.
        runner = _recording_runner(0, "", "")

        # Act.
        result, content = _models_json_check()(runner)

        # Assert: the layer failed as unseeded, exposing no content.
        self.assertEqual(result.name, MODELS_JSON_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(UNSEEDED_MARKER, result.detail.lower())
        self.assertIsNone(content)

    def test_check_models_json_exit_zero_whitespace_only_stdout_fails_as_unseeded(self):
        # Arrange: cat reads a file holding only whitespace.
        runner = _recording_runner(0, "   \n\t\n", "")

        # Act.
        result, content = _models_json_check()(runner)

        # Assert: whitespace-only is still unseeded, not a pass.
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(UNSEEDED_MARKER, result.detail.lower())
        self.assertIsNone(content)


class TestModelsJsonCheckPermissionDenied(unittest.TestCase):
    """Behaviour 10 (error): a permission marker in the non-zero exit's
    stderr fails with the chown one-liner as the fix line, composed
    from the adopted constants."""

    def test_check_models_json_permission_denied_fails_with_chown_one_liner(self):
        # Arrange: cat cannot read the file; the non-zero stderr carries
        # the permission marker.
        smoke_mod = _require_smoke()
        tag = "anvil-pi:dev"
        stderr = "cat: %s/models.json: Permission denied" % smoke_mod.AGENT_HOME
        runner = _recording_runner(1, "", stderr)

        # Act.
        result, content = _models_json_check()(runner, tag)

        # Assert: the layer failed -- not unseeded, the file exists but is
        # unreadable -- and one fix line carries the chown one-liner built
        # from the adopted constants for this tag.
        self.assertEqual(result.name, MODELS_JSON_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(
            PERMISSION_MARKER, stderr.lower(),
            "fixture stderr %r must carry the permission marker" % stderr,
        )
        self.assertNotIn(UNSEEDED_MARKER, result.detail.lower())
        self.assertTrue(
            any(_chown_one_liner(tag) in fix for fix in result.fix_lines),
            "fix lines %r must carry the chown one-liner for tag %r"
            % (result.fix_lines, tag),
        )
        self.assertIsNone(content)


class TestModelsJsonCheckNoSuchFile(unittest.TestCase):
    """Behaviour 10 (error): a no-such-file marker in the non-zero
    stderr fails with the seed instruction and NO chown fix line --
    the file is missing, not misowned."""

    def test_check_models_json_no_such_file_fails_with_seed_instruction_and_no_chown(self):
        # Arrange: cat cannot find the file; the non-zero stderr carries
        # the no-such-file marker.
        smoke_mod = _require_smoke()
        stderr = (
            "cat: %s/models.json: No such file or directory"
            % smoke_mod.AGENT_HOME
        )
        runner = _recording_runner(1, "", stderr)

        # Act.
        result, content = _models_json_check()(runner)

        # Assert: the layer failed with the seed instruction in the
        # detail (not unseeded -- unseeded means present but empty), and
        # no fix line offers a chown.
        self.assertEqual(result.name, MODELS_JSON_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(
            NO_SUCH_FILE_MARKER, stderr.lower(),
            "fixture stderr %r must carry the no-such-file marker" % stderr,
        )
        self.assertIn(SEED_MARKER, result.detail.lower())
        self.assertNotIn(UNSEEDED_MARKER, result.detail.lower())
        self.assertFalse(
            any("chown" in fix for fix in result.fix_lines),
            "fix lines %r must not carry a chown line for a missing file"
            % (result.fix_lines,),
        )
        self.assertIsNone(content)


class TestModelsJsonCheckNotOnPath(unittest.TestCase):
    """Behaviour 10 (error): ``FileNotFoundError`` from the runner is a
    not-on-PATH fail, never a traceback."""

    def test_check_models_json_runner_not_found_fails_saying_not_on_path(self):
        # Arrange: the runner raises ``FileNotFoundError`` as when docker
        # is missing from PATH.
        def runner(argv):
            raise FileNotFoundError("[Errno 2] No such file or directory: 'docker'")

        # Act: the exception must not escape the check -- a traceback here
        # fails the test.
        result, content = _models_json_check()(runner)

        # Assert: the layer failed, its detail says docker is not on
        # PATH, and no content is exposed.
        self.assertEqual(result.name, MODELS_JSON_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("path", result.detail.lower())
        self.assertIsNone(content)


# Behaviour 11: layer 3's coder-id-match check. Unlike behaviour 10 it
# takes no docker seam: the models.json text is the exact stdout
# behaviour 10's seam exposed, and the coder id is read from
# ``read_models(config_path).coder_id`` (``matrix.vars.coder``) through
# an injectable ``read_models`` seam that defaults to the real
# ``config.read_models`` -- the same seam pattern behaviour 8 pins, so
# neither id is hard-coded. The public seam these tests pin:
#
#     smoke.check_coder_id(models_json_text, config_path,
#                          read_models=...) -> LayerResult
#
# The layer is named ``"coder-id-match"``. The models.json shape is the
# one in ``tests/fixtures/golden_pi_models.json``: a top-level
# ``providers`` mapping of provider name to provider object, each
# provider carrying a ``models`` list, each model carrying an ``id``.
# The coder id present as some ``providers.<name>.models[].id`` passes,
# the detail naming the provider carrying it; the id absent fails,
# printing both the expected coder id and the seeded ids found.
# Malformed JSON fails naming the parse error; a missing ``providers``
# key, a provider with no ``models`` key, or a ``models`` that is not a
# list fails saying so -- never a ``KeyError`` or ``TypeError``
# escaping.
CODER_ID_CHECK_NAME = "check_coder_id"
CODER_ID_LAYER_NAME = "coder-id-match"


def _coder_id_check():
    """Return the behaviour-11 coder-id check, or fail naming what is
    missing."""
    smoke_mod = _require_smoke()
    check = getattr(smoke_mod, CODER_ID_CHECK_NAME, None)
    if check is None:
        raise AssertionError(
            "anvilkit.smoke does not define "
            "%s(models_json_text, config_path, read_models=...) yet "
            "(behaviour 11 of plans/smoke-test.md)" % CODER_ID_CHECK_NAME
        )
    return check


def _models_json_text(providers):
    """A models.json document built around the given ``providers``."""
    return json.dumps({"providers": providers})


def _provider(model_ids):
    """A provider object with one model entry per id in ``model_ids``."""
    return {
        "baseUrl": "http://127.0.0.1:8000/v1",
        "api": "openai-completions",
        "models": [{"id": model_id} for model_id in model_ids],
    }


class TestCoderIdCheckPass(unittest.TestCase):
    """Behaviour 11: the coder id present under a provider passes, the
    detail naming that provider."""

    def test_check_coder_id_id_present_under_one_provider_passes_naming_that_provider(self):
        # Arrange: the injected read_models supplies the coder id and the
        # seeded models.json carries it under one provider.
        coder_id = "qwen3-coder"
        text = _models_json_text({
            "llamaswap": _provider([coder_id, "some-other-model"]),
        })
        read_models = _fake_read_models(coder_id)

        # Act.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the layer is the coder-id-match layer in the pass
        # state, naming the provider that carries the id and the id
        # itself.
        self.assertEqual(result.name, CODER_ID_LAYER_NAME)
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn("llamaswap", result.detail)
        self.assertIn(coder_id, result.detail)

    def test_check_coder_id_id_present_under_second_of_two_providers_names_that_provider(self):
        # Arrange: the id sits under the second provider only.
        coder_id = "the-coder-from-config"
        text = _models_json_text({
            "provider-a": _provider(["seeded-only-in-a"]),
            "provider-b": _provider([coder_id]),
        })
        read_models = _fake_read_models(coder_id)

        # Act.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the pass names the provider carrying the id, not the
        # other one.
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn("provider-b", result.detail)

    def test_check_coder_id_reads_the_id_from_read_models_not_a_literal(self):
        # Arrange: a slash-carrying, hard-codeable-looking id supplied by
        # the fake topology; the seeded text carries only that id.
        coder_id = "org/repo/model-v9"
        text = _models_json_text({"llamaswap": _provider([coder_id])})
        read_models = _fake_read_models(coder_id)

        # Act.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the check matched the id read from config.yaml and read
        # the config the caller named.
        self.assertEqual(result.ok, STATE_OK)
        self.assertIn(coder_id, result.detail)
        self.assertEqual(
            read_models.calls, [("config.yaml", False)],
            "read_models must be called with the config path the caller "
            "named",
        )


class TestCoderIdCheckAbsent(unittest.TestCase):
    """Behaviour 11 (error): the coder id absent fails, printing both the
    expected id and the seeded ids found."""

    def test_check_coder_id_id_absent_fails_naming_expected_id_and_seeded_ids(self):
        # Arrange: the seeded text registers two models, neither the coder
        # id the config names.
        coder_id = "the-coder-from-config"
        text = _models_json_text({
            "llamaswap": _provider(["seeded-one", "seeded-two"]),
        })
        read_models = _fake_read_models(coder_id)

        # Act.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the layer failed, printing both the expected coder id
        # and the seeded ids found.
        self.assertEqual(result.name, CODER_ID_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn(coder_id, result.detail)
        self.assertIn("seeded-one", result.detail)
        self.assertIn("seeded-two", result.detail)


class TestCoderIdCheckMalformedJson(unittest.TestCase):
    """Behaviour 11 (error): malformed JSON fails naming the parse error --
    never a ``JSONDecodeError`` traceback escaping."""

    def test_check_coder_id_malformed_json_fails_naming_the_parse_error(self):
        # Arrange: a models.json that does not parse (a truncated object).
        text = '{"providers": {'
        # Derive the parse error text from the stdlib parser itself, so
        # the assertion cites the exact clause the implementation must
        # surface.
        expected_error = None
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            expected_error = str(exc)
        self.assertIsNotNone(
            expected_error, "fixture text must not parse"
        )
        read_models = _fake_read_models("the-coder-from-config")

        # Act: a JSONDecodeError escaping the check would error the test
        # with a traceback; instead the layer must fail.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the layer failed, and its detail names the parse error
        # -- the word "parse" plus the error text the parser produced
        # (its first clause, before the line and column, which the test
        # does not re-derive).
        self.assertEqual(result.name, CODER_ID_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        detail = result.detail.lower()
        self.assertIn("parse", detail)
        clause = expected_error.split(":")[0].lower()
        self.assertIn(
            clause,
            detail,
            "fail detail %r must carry the parse error text %r"
            % (result.detail, clause),
        )
        self.assertNotIn("Traceback", result.detail)


class TestCoderIdCheckMissingProviders(unittest.TestCase):
    """Behaviour 11 (error): a missing ``providers`` key fails saying so --
    never a ``KeyError`` escaping."""

    def test_check_coder_id_missing_providers_key_fails_saying_so(self):
        # Arrange: valid JSON without the top-level providers key.
        text = json.dumps({"models": []})
        read_models = _fake_read_models("the-coder-from-config")

        # Act: a KeyError escaping the check would error the test with a
        # traceback; instead the layer must fail.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the layer failed, and its detail says the providers key
        # is missing.
        self.assertEqual(result.name, CODER_ID_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("providers", result.detail.lower())


class TestCoderIdCheckProviderWithoutModels(unittest.TestCase):
    """Behaviour 11 (error): a provider with no ``models`` key, or a
    ``models`` that is not a list, fails saying so -- never a
    ``KeyError`` or ``TypeError`` escaping."""

    def test_check_coder_id_provider_without_models_key_fails_saying_so(self):
        # Arrange: a provider object without the models key.
        text = json.dumps({
            "providers": {
                "llamaswap": {"baseUrl": "http://127.0.0.1:8000/v1"},
            },
        })
        read_models = _fake_read_models("the-coder-from-config")

        # Act: a KeyError escaping the check would error the test with a
        # traceback; instead the layer must fail.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the layer failed, and its detail says the models list
        # is missing.
        self.assertEqual(result.name, CODER_ID_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("models", result.detail.lower())

    def test_check_coder_id_provider_models_not_a_list_fails_saying_so(self):
        # Arrange: a provider whose models value is not a list.
        text = json.dumps({
            "providers": {"llamaswap": {"models": "not-a-list"}},
        })
        read_models = _fake_read_models("the-coder-from-config")

        # Act: a TypeError escaping the check would error the test with a
        # traceback; instead the layer must fail.
        result = _coder_id_check()(
            text, "config.yaml", read_models=read_models,
        )

        # Assert: the layer failed, and its detail says the models value
        # is not a list.
        self.assertEqual(result.name, CODER_ID_LAYER_NAME)
        self.assertEqual(result.ok, STATE_FAILED)
        self.assertIn("models", result.detail.lower())


if __name__ == "__main__":
   unittest.main()
