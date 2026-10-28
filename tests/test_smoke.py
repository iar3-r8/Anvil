"""Tests for anvilkit.smoke, behaviours 1 and 2 of plans/smoke-test.md.

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
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


if __name__ == "__main__":
    unittest.main()
