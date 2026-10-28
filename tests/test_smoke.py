"""Tests for anvilkit.smoke, behaviours 1–7 of plans/smoke-test.md.

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
"""

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


if __name__ == "__main__":
   unittest.main()
