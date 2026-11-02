"""Tests for anvilkit.pi.piguardrails - the guardrails document builder.

Written before the implementation (TDD, ``plans/pi-guardrails.md``;
behaviour 3 "guardrails-document-golden-parity" and behaviour 4
"features-toggles-are-the-four-schema-booleans"). Module and attribute
lookups run **inside the test methods** through the
``PiguardrailsTestCase`` helpers, so a missing module or missing
attribute surfaces as a named-test error rather than a collection error.
The precedent is the red for behaviour 2 in ``tests/test_picrew.py``.

Pinned signatures::

    build_document() -> dict
    validate_document(document: dict) -> None

``build_document`` takes no arguments: the document is fixed by
construction (the issue's value choices are manager-settled ledger
decisions, not inputs). The returned dict must equal
``tests/fixtures/golden_pi_guardrails.json`` parsed, and ``enabled`` must
be the boolean ``True``.

``validate_document`` is the manager-pinned validation seam (behaviour 4
ledger decision): it raises ``GuardrailsError`` naming the offending key
and is called by ``build_document``. Because ``build_document`` takes no
arguments its error case is unreachable through it, so behaviour 4's
error-clause tests call ``validate_document`` directly with malformed
documents - deep copies of the built document with exactly one mutation
applied, so each differs from the valid document in exactly one way.

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

import copy
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


class TestFeaturesTogglesAreTheFourSchemaBooleans(PiguardrailsTestCase):
    """Behaviour 4: features-toggles-are-the-four-schema-booleans.

    Given: the built document. When: ``features`` is read. Then:
    ``permissionGate`` and ``policies`` are ``true``, ``pathAccess`` is
    ``false``, each a JSON boolean, and no fifth key is present.
    Error: a non-boolean or an unlisted feature key raises
    ``GuardrailsError`` naming it.

    The four allowed feature keys and their boolean type are the schema
    facts in ``doc/external/pi-guardrails/schema.md`` (``features`` allows
    exactly ``protectEnvFiles``, ``policies``, ``permissionGate``,
    ``pathAccess``, all booleans, ``additionalProperties: false``).

    The error clause is exercised through the manager-pinned seam:
    ``validate_document(document) -> None``, called by ``build_document``
    and raising ``GuardrailsError`` naming the offending key. The module
    exists with only ``build_document``, so the attribute is fetched
    inside the test body and its absence is asserted with a named message
    - the red is a named-test failure, never a collection error.
    """

    _SCHEMA_FEATURE_KEYS = frozenset(
        ["permissionGate", "policies", "pathAccess", "protectEnvFiles"]
    )

    def _get_validate_document(self):
        """Fetch ``anvilkit.pi.piguardrails.validate_document``, failing clearly if absent.

        Behaviour 4's error clause is unreachable through the no-argument
        ``build_document`` (the document is fixed by construction), so the
        validator is the seam under test. Fetching it here - not at module
        level - keeps a missing attribute a named-test failure.
        """
        piguardrails = self._piguardrails()
        validate_document = getattr(piguardrails, "validate_document", None)
        self.assertTrue(
            callable(validate_document),
            "anvilkit.pi.piguardrails.validate_document is not callable; "
            "the manager-pinned document validator (behaviour 4 seam, "
            "plans/pi-guardrails.md ledger) has not been implemented yet",
        )
        return validate_document

    def _mutated(self, mutate):
        """A deep copy of the built document with exactly one mutation.

        The valid document comes from ``build_document()`` itself, so the
        malformed document differs from the one the validator must accept
        in exactly one way.
        """
        built = self._get_build_document()()
        document = copy.deepcopy(built)
        mutate(document)
        return document

    def test_features_carry_exactly_the_four_schema_keys(self):
        built = self._get_build_document()()
        features = built.get("features")
        self.assertIsInstance(
            features,
            dict,
            "the built document must carry a features object",
        )
        self.assertEqual(
            set(features),
            set(self._SCHEMA_FEATURE_KEYS),
            "features must carry exactly the four schema keys "
            "{permissionGate, policies, pathAccess, protectEnvFiles} - "
            "no fifth key, none missing",
        )

    def test_features_values_are_json_booleans_with_the_settled_values(self):
        built = self._get_build_document()()
        features = built.get("features")
        self.assertIsInstance(features, dict)
        for key, value in features.items():
            self.assertIs(
                type(value),
                bool,
                "features.%s must be a JSON boolean (bool), not a "
                "truthy non-boolean" % key,
            )
        self.assertIs(True, features.get("permissionGate"),
                      "permissionGate must be true")
        self.assertIs(True, features.get("policies"),
                      "policies must be true")
        self.assertIs(False, features.get("pathAccess"),
                      "pathAccess must be false")
        self.assertIs(False, features.get("protectEnvFiles"),
                      "protectEnvFiles must be false (manager decision note)")

    def test_validate_document_rejects_non_boolean_feature_naming_the_key(self):
        validate_document = self._get_validate_document()

        def mutate(document):
            document["features"]["pathAccess"] = "off"

        bad = self._mutated(mutate)
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (features.pathAccess = \"off\")",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ) as ctx:
            validate_document(bad)
        self.assertIn(
            "pathAccess",
            str(ctx.exception),
            "GuardrailsError must name the offending key (pathAccess)",
        )

    def test_validate_document_rejects_unlisted_feature_key_naming_the_key(self):
        validate_document = self._get_validate_document()

        def mutate(document):
            document["features"]["shell"] = True

        bad = self._mutated(mutate)
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (a fifth feature key: shell)",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ) as ctx:
            validate_document(bad)
        self.assertIn(
            "shell",
            str(ctx.exception),
            "GuardrailsError must name the offending key (shell)",
        )


if __name__ == "__main__":
    unittest.main()
