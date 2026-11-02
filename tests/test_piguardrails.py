"""Tests for anvilkit.pi.piguardrails - the guardrails document builder.

Written before the implementation (TDD, ``plans/pi-guardrails.md``,
behaviour 3: "guardrails-document-golden-parity"). The production module
``anvilkit.pi.piguardrails`` does not exist yet, so the test loads it
through ``_piguardrails``, which fetches the module and the
``build_document`` attribute **inside the test method** - the file never
fails collection, and the suite is red with a named-test error (the
module's own ``ModuleNotFoundError``) rather than a collection error.
The precedent is the red for behaviour 2 in ``tests/test_picrew.py``.

Pinned signature::

    build_document() -> dict

No arguments: the document is fixed by construction (the issue's value
choices are manager-settled ledger decisions, not inputs). The returned
dict must equal ``tests/fixtures/golden_pi_guardrails.json`` parsed, and
``enabled`` must be the boolean ``True``.

Golden-value rationale (manager decision notes, ``plans/pi-guardrails.md``
ledger; schema source of truth ``doc/external/pi-guardrails/schema.md``):

- ``features.protectEnvFiles`` is explicitly ``false``: the issue enables
  only ``policies`` + ``permissionGate``, the ``secrets`` rule already
  covers env files, and the package built-in env layer is partly
  ``fd``-dependent per the source review.
- The ``guardrails-config`` rule is ``readOnly``: the threat is an agent
  editing its own gate - ``readOnly`` blocks the edit without blocking
  reads.
- ``autoDenyPatterns`` entries carry only the required ``pattern`` key:
  the documented match is substring unless ``regex: true``.
- ``onlyIfExists`` is explicit ``true`` (schema: "Block only when file
  exists on disk. Default true.") so behaviour 7 can assert presence.
- No ``$schema``/``version`` keys: ``version`` is "stamped by migrations".
"""

import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES = REPO_ROOT / "tests" / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class PiguardrailsTestCase(unittest.TestCase):
    """Shared lazy import for the guardrails module (red-safe)."""

    def _piguardrails(self):
        """Import anvilkit.pi.piguardrails, failing clearly if the module is absent.

        Called inside the test body so a missing module surfaces as this
        named test's error, never as a collection error.
        """
        spec = importlib.util.find_spec("anvilkit.pi.piguardrails")
        self.assertIsNotNone(
            spec,
            "anvilkit.pi.piguardrails cannot be imported; the guardrails "
            "document builder has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pi.piguardrails")

    def _get_build_document(self):
        """Fetch ``anvilkit.pi.piguardrails.build_document``, failing clearly if absent."""
        piguardrails = self._piguardrails()
        build_document = getattr(piguardrails, "build_document", None)
        self.assertTrue(
            callable(build_document),
            "anvilkit.pi.piguardrails.build_document is not callable; the "
            "no-argument guardrails document builder has not been "
            "implemented yet",
        )
        return build_document


class TestBuildDocumentGoldenParity(PiguardrailsTestCase):
    """Behaviour 3: guardrails-document-golden-parity.

    Given: no arguments (the document is fixed by construction). When: the
    built document is parsed. Then: it equals
    ``tests/fixtures/golden_pi_guardrails.json``, and ``enabled`` is
    ``true``. Error: none.

    The comparison is on parsed structures, not raw strings, per
    ``tests/fixtures/README.md`` - key ordering and whitespace are not
    part of the contract.
    """

    def test_build_document_equals_golden_fixture(self):
        build_document = self._get_build_document()
        built = build_document()
        self.assertIsInstance(
            built,
            dict,
            "build_document must return the document as a dict, "
            "never a hand-built JSON string",
        )
        self.assertEqual(
            built,
            load_fixture("golden_pi_guardrails.json"),
            "the built guardrails document must equal the golden "
            "fixture exactly (full parsed equality)",
        )

    def test_build_document_enabled_is_boolean_true(self):
        build_document = self._get_build_document()
        built = build_document()
        self.assertIs(
            True,
            built.get("enabled"),
            "enabled must be the boolean True, not a truthy "
            "non-boolean",
        )


if __name__ == "__main__":
    unittest.main()
