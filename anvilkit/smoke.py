"""Host smoke test for the real single-role stack.

Renders per-layer verdicts for a human: one line per layer carrying its name
and detail, a verdict glyph for passed and failed layers, and indented fix
lines beneath a failing layer only. This behaviour is the report renderer
behaviour 1 of ``plans/smoke-test.md``; the layer checks themselves arrive in
later behaviours.
"""

import dataclasses
from typing import Sequence

# The stable header rendered by ``format_report``, even when there is nothing
# else to say. Later behaviours assert this exact string.
HEADER = "Anvil smoke test"

# Canonical layer states.
STATE_OK = "ok"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"

PASS_GLYPH = "\u2705"  # ✅
FAIL_GLYPH = "\u274c"  # ❌
# A skipped layer carries neither verdict glyph, but is not silent either: a
# plain bullet keeps it on its own line without claiming a verdict.
SKIP_MARK = "-"


@dataclasses.dataclass
class LayerResult:
    """The outcome of one smoke-test layer.

    ``ok`` is a state string, one of :data:`STATE_OK`, :data:`STATE_FAILED`
    or :data:`STATE_SKIPPED`; ``detail`` is the one-line human explanation;
    ``fix_lines`` are the remediation commands, shown under a failing layer
    only.
    """

    name: str
    ok: str
    detail: str
    fix_lines: Sequence[str] = ()


def _layer_lines(result: "LayerResult") -> Sequence[str]:
    """The report lines for one layer: its line, plus fix lines for failures."""
    if result.ok == STATE_OK:
        head = "%s %s: %s" % (PASS_GLYPH, result.name, result.detail)
    elif result.ok == STATE_FAILED:
        head = "%s %s: %s" % (FAIL_GLYPH, result.name, result.detail)
    else:  # STATE_SKIPPED — never a verdict glyph, never its fix lines.
        head = "%s %s: %s" % (SKIP_MARK, result.name, result.detail)
    if result.ok == STATE_FAILED:
        return (head,) + tuple("  " + fix for fix in result.fix_lines)
    return (head,)


def format_report(results: Sequence["LayerResult"]) -> str:
    """Render one verdict line per layer, in order, under the stable header.

    A passing layer gets the ✅ line, a failing layer the ❌ line with its
    fix lines indented beneath it, a skipped layer a plain line; fix lines
    never print for passing or skipped results, and an empty list renders
    only :data:`HEADER`.
    """
    lines = [HEADER]
    for result in results:
        lines.extend(_layer_lines(result))
    return "\n".join(lines) + "\n"
