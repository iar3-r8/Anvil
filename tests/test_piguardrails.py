"""Tests for anvilkit.pi.piguardrails - the guardrails document builder.

Written before the implementation (TDD, ``plans/pi-guardrails.md``;
behaviours 3 "guardrails-document-golden-parity", 4
"features-toggles-are-the-four-schema-booleans", 5
"autodeny-blocks-the-four-git-subcommands" and 6
"secret-policy-rule-refuses-env-pem-key"). Module and attribute
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
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import render  # noqa: E402

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

    def _get_package_source(self):
        """Fetch ``anvilkit.pi.piguardrails.PACKAGE_SOURCE``, failing clearly if absent.

        The module "owns the pinned package source" (``plans/
        pi-guardrails.md``, Scope): the constant is the exact pinned
        source string for ``@aliou/pi-guardrails``. Fetching it here -
        not at module level - keeps a missing attribute a named-test
        failure (behaviour 13's red), never a collection error.
        """
        piguardrails = self._piguardrails()
        package_source = getattr(piguardrails, "PACKAGE_SOURCE", None)
        self.assertIsNotNone(
            package_source,
            "anvilkit.pi.piguardrails.PACKAGE_SOURCE is missing; the "
            "module must own the pinned package source (behaviour 13, "
            "plans/pi-guardrails.md)",
        )
        return package_source

    def _get_validate_document(self):
        """Fetch ``anvilkit.pi.piguardrails.validate_document``, failing clearly if absent.

        The manager-pinned document validator (behaviour 4 seam,
        ``plans/pi-guardrails.md`` ledger): it raises
        ``GuardrailsError`` naming the offending key and is called by
        ``build_document``. Because ``build_document`` takes no
        arguments its error case is unreachable through it, so the
        error-clause tests (behaviours 4 and 5) call it directly with
        malformed documents. Fetching it here - not at module level -
        keeps a missing attribute a named-test failure.
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

    def _get_guardrails_settings(self):
        """Fetch ``anvilkit.render.guardrails_settings``, failing clearly if absent.

        The manager-pinned render seam (behaviour 11, ``plans/
        pi-guardrails.md`` ledger): ``render.guardrails_settings() -> str``,
        no arguments, delegates to ``build_document``, calls
        ``validate_document`` on the result and returns the rendered string
        (the dict + ``json.dumps`` path mirroring the other renderers in
        ``anvilkit/render.py``). ``anvilkit.render`` exists, so the module is
        imported at module level above; the function itself is fetched
        inside the test body so its absence is a named-test failure, never
        a collection error.
        """
        guardrails_settings = getattr(render, "guardrails_settings", None)
        self.assertTrue(
            callable(guardrails_settings),
            "anvilkit.render.guardrails_settings is not callable; the "
            "render seam for the guardrails document (behaviour 11, "
            "plans/pi-guardrails.md ledger) has not been implemented yet",
        )
        return guardrails_settings

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


def _matches(pattern, command):
    """Manager-settled substring rule (plans/pi-guardrails.md ledger).

    A pattern matches a command iff the command equals the pattern, or
    starts with the pattern followed by whitespace. The package matches
    command strings, not ASTs, so the boundary is on the caller side;
    this helper pins that rule so the negative tests are precise (a raw
    substring match would let ``git reset`` match ``git push --reset-author``).
    """
    return command == pattern or command.startswith(pattern + " ")


class TestAutoDenyBlocksTheFourGitSubcommands(PiguardrailsTestCase):
    """Behaviour 5: autodeny-blocks-the-four-git-subcommands.

    Given: the commands ``git commit -m x``, ``git push``,
    ``git reset --hard``, ``git rebase -i``. When: each is matched
    against ``permissionGate.autoDenyPatterns`` by the documented
    substring rule. Then: every one matches an entry; ``git status``
    and ``git diff`` match none. The ledger's added negative pins the
    rule itself: ``git reset`` must NOT match ``git push
    --reset-author`` (the false positive a raw substring rule would
    produce), while ``git push`` still matches that command.
    Error: an entry missing its required ``pattern`` key raises
    ``GuardrailsError`` via ``validate_document`` (the seam behaviour 4
    established; the manager-settled ledger note pins the matching rule).

    The matching-rule tests pass today against the existing golden -
    they pin the rule. The error-clause test is the red: it fails
    because ``validate_document`` does not check ``permissionGate``
    yet (assertRaises catches nothing -> AssertionError).
    """

    _REQUIRED_PATTERNS = frozenset(
        ["git commit", "git push", "git reset", "git rebase"]
    )

    def _auto_deny_patterns(self):
        """The built document's ``permissionGate.autoDenyPatterns`` list."""
        built = self._get_build_document()()
        gate = built.get("permissionGate")
        self.assertIsInstance(
            gate,
            dict,
            "the built document must carry a permissionGate object",
        )
        patterns = gate.get("autoDenyPatterns")
        self.assertIsInstance(
            patterns,
            list,
            "permissionGate must carry an autoDenyPatterns list",
        )
        return patterns

    def test_auto_deny_patterns_are_exactly_the_four_git_patterns(self):
        """The entries are pattern-only objects carrying exactly the four patterns."""
        patterns = self._auto_deny_patterns()
        for entry in patterns:
            self.assertIsInstance(
                entry,
                dict,
                "each autoDenyPatterns entry must be an object "
                "(schema: PatternConfig), not a bare string",
            )
            self.assertEqual(
                set(entry),
                {"pattern"},
                "each autoDenyPatterns entry must carry only the "
                "required 'pattern' key (manager decision note)",
            )
        self.assertEqual(
            {entry["pattern"] for entry in patterns},
            set(self._REQUIRED_PATTERNS),
            "autoDenyPatterns must be exactly {git commit, git push, "
            "git reset, git rebase} - no extra, none missing",
        )

    def test_each_of_the_four_git_subcommands_matches_an_entry(self):
        """git commit -m x / git push / git reset --hard / git rebase -i all match."""
        patterns = [entry["pattern"] for entry in self._auto_deny_patterns()]
        for command in [
            "git commit -m x",
            "git push",
            "git reset --hard",
            "git rebase -i",
        ]:
            self.assertTrue(
                any(_matches(pattern, command) for pattern in patterns),
                "%r must match an autoDenyPatterns entry under the "
                "documented substring rule" % command,
            )

    def test_git_status_and_git_diff_match_no_entry(self):
        """git status / git diff (the plan's own negatives) match no entry."""
        patterns = [entry["pattern"] for entry in self._auto_deny_patterns()]
        for command in ["git status", "git diff"]:
            self.assertFalse(
                any(_matches(pattern, command) for pattern in patterns),
                "%r must match no autoDenyPatterns entry" % command,
            )

    def test_git_reset_does_not_match_git_push_with_reset_author_flag(self):
        """git reset (the ledger's added negative) must not match git push --reset-author.

        Raw substring has a false positive inside our own set: ``git reset``
        is a substring of ``git push --reset-author``. The package matches
        command strings, not ASTs, so the boundary is on the caller side -
        the manager-settled rule (equal, or pattern + whitespace) is what
        pins it. ``git push`` must still match the same command.
        """
        self.assertFalse(
            _matches("git reset", "git push --reset-author"),
            "under the manager-settled rule, 'git reset' must not match "
            "'git push --reset-author' - a naive substring rule would",
        )
        self.assertTrue(
            _matches("git push", "git push --reset-author"),
            "'git push' must still match 'git push --reset-author' "
            "under the manager-settled rule",
        )
        patterns = [entry["pattern"] for entry in self._auto_deny_patterns()]
        self.assertTrue(
            any(_matches(pattern, "git push --reset-author")
                for pattern in patterns),
            "git push --reset-author must match an entry (git push), "
            "so the gate blocks it for the right reason",
        )

    def test_validate_document_rejects_entry_missing_pattern_key(self):
        """An entry without its required 'pattern' key raises GuardrailsError.

        The red: validate_document currently checks only the features
        level, so it does not reject a pattern-less entry - assertRaises
        catches nothing and this fails with AssertionError.
        """
        validate_document = self._get_validate_document()

        def mutate(document):
            document["permissionGate"]["autoDenyPatterns"][0] = {
                "description": "commits",
            }

        bad = self._mutated(mutate)
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (autoDenyPatterns[0] without a pattern key)",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ) as ctx:
            validate_document(bad)
        self.assertIn(
            "autoDenyPatterns",
            str(ctx.exception),
            "GuardrailsError must name the offending section "
            "(autoDenyPatterns) or its index/entry",
        )


def _glob_match(pattern, path):
    """Manager-settled glob semantics for policy-rule file paths.

    ``plans/pi-guardrails.md`` ledger (behaviour 6 note): a glob ``*``
    matches any run of characters that does not cross a path separator,
    ``?`` matches one character that is not a separator, and a bare-name
    pattern (``.env`` - no glob characters, no separator) matches the
    basename at any depth, so ``.env`` also refuses ``.env.local`` and
    ``secrets/.env``. This is the same "glob for files" default the
    package applies to tool-call paths (doc/external/pi-guardrails/
    schema.md, doc/external/pi-guardrails/readme.md), made precise by the
    manager so the red pins one rule instead of any regex the coder
    could satisfy.
    """
    candidate = path.rsplit("/", 1)[-1] if "/" not in pattern else path
    if "/" not in pattern and "*" not in pattern and "?" not in pattern:
        # A bare-name pattern matches the basename at any depth.
        return candidate.startswith(pattern)
    regex = ""
    for char in pattern:
        if char == "*":
            regex += r"[^/]*"
        elif char == "?":
            regex += r"[^/]"
        else:
            regex += re.escape(char)
    return re.match(regex + r"$", candidate) is not None


class TestSecretPolicyRuleRefusesEnvPemKey(PiguardrailsTestCase):
    """Behaviour 6: secret-policy-rule-refuses-env-pem-key.

    Given: the paths ``.env``, ``server.pem``, ``id_rsa.key`` and
    ``README.md``. When: the ``noAccess`` rule's globs are applied.
    Then: the first three match and ``README.md`` does not; the rule
    carries ``id``, ``patterns`` and ``protection`` as the schema
    requires (doc/external/pi-guardrails/schema.md: ``PolicyRule``).
    Error: a rule missing any required key raises ``GuardrailsError``
    naming the rule id via ``validate_document`` (the seam behaviours 4
    and 5 established; the manager-settled ledger note pins the glob
    semantics).

    The rule-shape and glob-coverage tests pass today against the
    existing golden - they pin the patterns plus the settled semantics.
    The three error-clause tests are the red: ``validate_document`` does
    not check ``policies.rules`` yet, so ``assertRaises`` catches nothing
    and each fails with AssertionError ("not raised"), never a
    collection error.
    """

    _SECRET_GLOBS = frozenset([".env", "*.pem", "*.key"])

    def _secrets_rule(self):
        """The built document's ``policies.rules`` entry with id ``secrets``."""
        built = self._get_build_document()()
        policies = built.get("policies")
        self.assertIsInstance(
            policies,
            dict,
            "the built document must carry a policies object",
        )
        rules = policies.get("rules")
        self.assertIsInstance(
            rules,
            list,
            "policies must carry a rules list",
        )
        for rule in rules:
            if isinstance(rule, dict) and rule.get("id") == "secrets":
                return rule
        self.fail("policies.rules must carry a rule with id 'secrets'")

    def _secrets_patterns(self):
        """The secrets rule's pattern strings, in document order."""
        rule = self._secrets_rule()
        patterns = rule.get("patterns")
        self.assertIsInstance(
            patterns,
            list,
            "the secrets rule must carry a patterns list",
        )
        return [entry["pattern"] for entry in patterns]

    def _delete_secrets_rule_key(self, key):
        """A mutation deleting ``key`` from the secrets rule (for ``_mutated``)."""
        def mutate(document):
            for rule in document["policies"]["rules"]:
                if isinstance(rule, dict) and rule.get("id") == "secrets":
                    del rule[key]
                    return
            raise AssertionError("secrets rule not found in the built document")
        return mutate

    def test_secrets_rule_carries_required_keys_and_exactly_the_three_globs(self):
        """id 'secrets', protection 'noAccess', patterns exactly {.env, *.pem, *.key}."""
        rule = self._secrets_rule()
        self.assertEqual(
            rule.get("id"),
            "secrets",
            "the noAccess rule must carry id 'secrets' (schema: PolicyRule.id)",
        )
        self.assertEqual(
            rule.get("protection"),
            "noAccess",
            "the secrets rule's protection must be noAccess (schema: PolicyRule)",
        )
        patterns = rule.get("patterns")
        self.assertIsInstance(
            patterns,
            list,
            "the secrets rule must carry a patterns list "
            "(schema: PolicyRule.patterns)",
        )
        for entry in patterns:
            self.assertIsInstance(
                entry,
                dict,
                "each secrets patterns entry must be an object "
                "(schema: PatternConfig), not a bare string",
            )
            self.assertIn(
                "pattern",
                entry,
                "each secrets patterns entry must carry the required "
                "'pattern' key",
            )
        self.assertEqual(
            {entry["pattern"] for entry in patterns},
            set(self._SECRET_GLOBS),
            "the secrets rule's globs must be exactly "
            "{.env, *.pem, *.key} - no extra, none missing",
        )

    def test_env_glob_refuses_env_files_at_any_depth(self):
        """.env refuses .env, .env.local and secrets/.env (ledger note)."""
        patterns = self._secrets_patterns()
        for path in [".env", ".env.local", "secrets/.env"]:
            self.assertTrue(
                any(_glob_match(pattern, path) for pattern in patterns),
                "%r must be refused by a secrets glob under the "
                "manager-settled semantics" % path,
            )

    def test_pem_glob_refuses_pem_files_at_any_depth(self):
        """*.pem refuses server.pem and keys/server.pem (ledger note)."""
        patterns = self._secrets_patterns()
        for path in ["server.pem", "keys/server.pem"]:
            self.assertTrue(
                any(_glob_match(pattern, path) for pattern in patterns),
                "%r must be refused by a secrets glob under the "
                "manager-settled semantics" % path,
            )

    def test_key_glob_refuses_key_files_at_any_depth(self):
        """*.key refuses id_rsa.key and secrets/id_rsa.key (ledger note)."""
        patterns = self._secrets_patterns()
        for path in ["id_rsa.key", "secrets/id_rsa.key"]:
            self.assertTrue(
                any(_glob_match(pattern, path) for pattern in patterns),
                "%r must be refused by a secrets glob under the "
                "manager-settled semantics" % path,
            )

    def test_readme_matches_no_secret_glob(self):
        """None of the three globs matches README.md (the plan's negative)."""
        patterns = self._secrets_patterns()
        self.assertFalse(
            any(_glob_match(pattern, "README.md") for pattern in patterns),
            "README.md must be refused by none of the secrets globs",
        )

    def test_validate_document_rejects_secrets_rule_missing_patterns_naming_the_rule(self):
        """A secrets rule without 'patterns' raises GuardrailsError naming the rule.

        The red: validate_document currently checks only the features
        level and permissionGate.autoDenyPatterns, so it does not check
        policies.rules - assertRaises catches nothing and this fails
        with AssertionError ("not raised").
        """
        validate_document = self._get_validate_document()
        bad = self._mutated(self._delete_secrets_rule_key("patterns"))
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (secrets rule without 'patterns')",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ) as ctx:
            validate_document(bad)
        self.assertIn(
            "secrets",
            str(ctx.exception),
            "GuardrailsError must name the rule id (secrets)",
        )

    def test_validate_document_rejects_secrets_rule_missing_protection_naming_the_rule(self):
        """A secrets rule without 'protection' raises GuardrailsError naming the rule.

        The red: validate_document does not check policies.rules yet -
        assertRaises catches nothing and this fails with AssertionError
        ("not raised").
        """
        validate_document = self._get_validate_document()
        bad = self._mutated(self._delete_secrets_rule_key("protection"))
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (secrets rule without 'protection')",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ) as ctx:
            validate_document(bad)
        self.assertIn(
            "secrets",
            str(ctx.exception),
            "GuardrailsError must name the rule id (secrets)",
        )

    def test_validate_document_rejects_secrets_rule_missing_id(self):
        """A secrets rule without 'id' raises GuardrailsError.

        There is no id left to name in the message, so only the error
        type is asserted. The red: validate_document does not check
        policies.rules yet - assertRaises catches nothing and this
        fails with AssertionError ("not raised").
        """
        validate_document = self._get_validate_document()
        bad = self._mutated(self._delete_secrets_rule_key("id"))
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (secrets rule without 'id')",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ):
            validate_document(bad)


class TestUnknownKeyRaisesRenderError(PiguardrailsTestCase):
    """Behaviour 9: unknown-key-raises-render-error.

    Given: a document carrying a key outside the schema's allowed set, at
    top level and nested inside ``features``. When: the builder validates
    it. Then: nothing is returned and nothing is written. Error:
    ``GuardrailsError`` naming the offending key and its level - never
    silently emitted.

    The two levels of the schema's ``additionalProperties: false`` are
    asserted separately so each clause of behaviour 9 is named:

    - the top level is THIS red: ``validate_document`` does not check
      top-level keys yet, so ``assertRaises`` catches nothing and the
      top-level test fails with AssertionError ("not raised") - a
      named-test failure, never a collection error.
    - the ``features`` level is a passing cross-reference: behaviour 4's
      green already enforces it (an unlisted fifth feature key raises),
      and this test proves behaviour 9's features clause is covered by
      an explicitly named test.

    "Nothing is returned and nothing is written" is exercised through
    the manager-pinned seam: ``build_document`` is fixed by construction,
    so the tests assert the raise through ``validate_document`` on a
    mutated deep copy (the seam behaviours 4-6 established); the module
    is render-only - it has no disk writes, so the "nothing written"
    clause is a non-goal here (plan: no provisioning or CLI wiring
    this slice).
    """

    # The schema's allowed top-level keys (doc/external/pi-guardrails/
    # schema.md: GuardrailsConfig is additionalProperties: false, allowed
    # top-level keys are exactly these). The built document uses a subset
    # (enabled, features, permissionGate, policies); the test mutates the
    # built document to add an unlisted key.
    _SCHEMA_TOP_LEVEL_KEYS = frozenset(
        [
            "$schema",
            "version",
            "enabled",
            "applyBuiltinDefaults",
            "onboarding",
            "features",
            "policies",
            "pathAccess",
            "envFiles",
            "permissionGate",
        ]
    )

    def _guardrails_config_rule(self):
        """The built document's ``policies.rules`` entry for the gate config.

        The rule whose patterns cover ``.pi/extensions/guardrails.json``
        (the schema's own project-config path, doc/external/pi-guardrails/
        readme.md Configuration) - the ledger pins it by id
        ``guardrails-config``.
        """
        built = self._get_build_document()()
        policies = built.get("policies")
        self.assertIsInstance(
            policies,
            dict,
            "the built document must carry a policies object",
        )
        rules = policies.get("rules")
        self.assertIsInstance(
            rules,
            list,
            "policies must carry a rules list",
        )
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            patterns = rule.get("patterns")
            if not isinstance(patterns, list):
                continue
            for entry in patterns:
                if (
                    isinstance(entry, dict)
                    and entry.get("pattern") == ".pi/extensions/guardrails.json"
                ):
                    return rule
        self.fail(
            "policies.rules must carry a rule whose patterns include "
            "'.pi/extensions/guardrails.json' (the golden's "
            "'guardrails-config' rule)"
        )

    def test_validate_document_rejects_unlisted_top_level_key_naming_the_key(self):
        """A top-level key outside the schema's allowed set raises GuardrailsError.

        THE RED of behaviour 9: validate_document currently checks the
        features level, permissionGate.autoDenyPatterns and policies.rules
        only - it has no top-level key check, so assertRaises catches
        nothing and this fails with AssertionError ("not raised"), for the
        right reason (the check does not exist yet), never a collection
        error. The message, once raised, must name the offending key and
        its level (top level).
        """
        validate_document = self._get_validate_document()
        self.assertNotIn(
            "shellGuard",
            self._SCHEMA_TOP_LEVEL_KEYS,
            "the test key must be unlisted in the schema's allowed "
            "top-level set, or it tests nothing",
        )

        def mutate(document):
            document["shellGuard"] = {}

        bad = self._mutated(mutate)
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (an unlisted top-level key: shellGuard)",
        )
        with self.assertRaises(
            self._piguardrails().GuardrailsError,
        ) as ctx:
            validate_document(bad)
        self.assertIn(
            "shellGuard",
            str(ctx.exception),
            "GuardrailsError must name the offending key (shellGuard)",
        )

    def test_validate_document_rejects_unlisted_features_key_naming_the_key(self):
        """A key nested inside features outside the allowed set raises GuardrailsError.

        The cross-reference proving behaviour 9's second clause (the
        features level): behaviour 4's green already enforces it, so this
        PASSES today - a failing result here would mean behaviour 4's
        enforcement regressed, not that behaviour 9's red is wrong.
        """
        validate_document = self._get_validate_document()

        def mutate(document):
            document["features"]["shell"] = True

        bad = self._mutated(mutate)
        self.assertNotEqual(
            bad,
            self._get_build_document()(),
            "the malformed document must differ from the built document "
            "in exactly one place (a fifth features key: shell)",
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

    def test_guardrails_config_rule_protects_its_own_gate_config(self):
        """Behaviour 8 boundary pin: the gate config is covered by its own policy.

        Given: the path ``.pi/extensions/guardrails.json``. When: the
        policy rules are applied to it. Then: it matches a rule whose
        ``protection`` is not ``none``, so the agent cannot quietly
        weaken its own gate. The ledger pins the rule's protection to
        ``readOnly`` (blocks the edit without blocking reads) - pin it
        exactly.

        BOUNDARY PIN - no production change: the golden already carries
        the ``guardrails-config`` rule with ``protection: readOnly``, so
        this passes today and must keep passing.
        """
        rule = self._guardrails_config_rule()
        self.assertEqual(
            rule.get("id"),
            "guardrails-config",
            "the gate-config rule must carry the golden's id "
            "'guardrails-config'",
        )
        self.assertNotEqual(
            rule.get("protection"),
            "none",
            "the gate-config rule's protection must not be 'none' - "
            "the agent must not be able to quietly weaken its own gate",
        )
        self.assertEqual(
            rule.get("protection"),
            "readOnly",
            "the gate-config rule's protection must be 'readOnly' "
            "(manager decision note: blocks the edit without blocking "
            "reads)",
        )


class TestRenderDelegatesAndTranslates(PiguardrailsTestCase):
    """Behaviour 11: render-delegates-and-translates.

    Given: the same inputs to ``render.guardrails_settings()`` and the
    delegate. When: both are compared, then the delegate is made to
    fail. Then: the rendered string parses to exactly the delegate's
    document. Error: ``GuardrailsError`` surfaces as ``RenderError``;
    the two types are unrelated, so no delegate error leaks.

    The seam is manager-pinned by the ledger: ``render.guardrails_settings()
    -> str``, no arguments, delegates to ``piguardrails.build_document()``
    (fetched as a module attribute, the same seam ``render.pi_models_settings``
    uses for ``piargv.models_document``), calls ``validate_document`` on the
    result, and returns the rendered string — the dict + ``json.dumps`` path
    mirroring the other renderers in ``anvilkit/render.py``.

    The delegate is made to fail by patching ``piguardrails.build_document``
    (the module attribute the render module looks up at call time, so the
    patch sits at exactly the seam the production code goes through) to
    raise ``GuardrailsError``.

    Both tests FAIL today for the right reason: ``render.guardrails_settings``
    does not exist, so the lazy fetch inside each test body fails with a
    named AssertionError, never a collection error.
    """

    def test_rendered_string_parses_to_exactly_the_delegate_document(self):
        """The rendered string parses to exactly build_document()'s output.

        The comparison is on parsed structures (full parsed equality —
        key ordering and whitespace are not part of the contract, per
        tests/fixtures/README.md), and the parse result's ``enabled``
        must be the boolean ``True`` (behaviour 3's settled value,
        carried through the seam unchanged).
        """
        guardrails_settings = self._get_guardrails_settings()
        build_document = self._get_build_document()

        rendered = guardrails_settings()
        self.assertIsInstance(
            rendered,
            str,
            "render.guardrails_settings must return the rendered "
            "document as a string (the dict + json.dumps path the "
            "other renderers use)",
        )
        parsed = json.loads(rendered)
        self.assertEqual(
            parsed,
            build_document(),
            "the rendered guardrails document must parse to exactly "
            "the delegate's (build_document's) document",
        )
        self.assertIs(
            True,
            parsed.get("enabled"),
            "the parse result's enabled must be the boolean True "
            "(the golden's settled value, carried through the seam)",
        )

    def test_guardrails_error_surfaces_as_render_error_and_never_leaks(self):
        """A delegate GuardrailsError surfaces as RenderError; no leak.

        ``GuardrailsError`` is translated to ``RenderError`` at the seam
        — the two types are unrelated (neither subclasses the other),
        so ``assertRaises(RenderError)`` proves the delegate's error was
        translated rather than leaked past.
        """
        guardrails_settings = self._get_guardrails_settings()
        piguardrails = self._piguardrails()

        self.assertFalse(
            issubclass(render.RenderError, piguardrails.GuardrailsError),
            "the leak guard is only meaningful because the two exception "
            "types are unrelated",
        )
        self.assertFalse(
            issubclass(piguardrails.GuardrailsError, render.RenderError),
            "the leak guard is only meaningful because the two exception "
            "types are unrelated",
        )

        def boom():
            raise piguardrails.GuardrailsError("delegate refused")

        with mock.patch.object(piguardrails, "build_document", boom):
            with self.assertRaises(render.RenderError) as ctx:
                guardrails_settings()
        self.assertNotIsInstance(
            ctx.exception,
            piguardrails.GuardrailsError,
            "the surfaced error must be a RenderError, never a leaked "
            "GuardrailsError",
        )


class TestHostilePatternSurvivesJsonDumps(PiguardrailsTestCase):
    """Behaviour 12: hostile-pattern-survives-json-dumps.

    Given: a pattern containing a quote, a backslash and a newline.
    When: the rendered string is parsed back. Then: the value is
    byte-identical — valid by construction via ``json.dumps``, never
    string substitution. Error: none.

    Because ``render.guardrails_settings()`` takes no arguments, the
    hostile value is injected through the manager-pinned ``overrides``
    argument on ``build_document`` (behaviour 12 ledger note):
    ``build_document(overrides={"autoDenyPatterns": [...]})``. The
    no-argument call is unchanged, so behaviour 3's golden parity stays
    green.

    The red is split by the manager, because the seam cannot carry the
    hostile value directly (no arguments):

    - (a) ``test_hostile_pattern_round_trips_through_json_dumps`` pins
      the round-trip itself: a document whose ``autoDenyPatterns``
      carries the hostile pattern, serialized with ``json.dumps`` (any
      style — whitespace is not part of the contract) and parsed back,
      carries the pattern byte-identical. This PASSES today — it pins
      ``json.dumps``'s validity-by-construction for this value (the
      injection into the document is test-side for now; the green's
      ``overrides`` parameter is the production path for the same
      value).
    - (b) ``test_build_document_respects_the_overrides_argument`` pins
      the injection path: ``build_document`` accepts the optional
      ``overrides`` keyword and respects it (the overridden
      ``autoDenyPatterns`` appears in the built document). This FAILS
      today with ``TypeError`` — the ``overrides`` parameter does not
      exist yet. That is the named red: the injection path does not
      exist.

    Once the green lands (the ``overrides`` parameter implemented),
    both assertions pass in one step.
    """

    # A pattern containing a double quote, a backslash and a newline —
    # the value the plan names. As a real Python string, ``x"\\y\nz``
    # carries all three characters.
    _HOSTILE_PATTERN = 'x"\\y\nz'

    def _document_with_hostile_pattern(self):
        """A deep copy of the built document carrying the hostile pattern.

        The copy differs from the built document in exactly one place
        (``permissionGate.autoDenyPatterns`` now carries the hostile
        pattern), so the round-trip assertion targets exactly the
        hostile value. Test-side injection: once the green lands,
        ``build_document(overrides=...)`` is the production path for
        the same value.
        """
        built = self._get_build_document()()
        document = copy.deepcopy(built)
        document["permissionGate"]["autoDenyPatterns"] = [
            {"pattern": self._HOSTILE_PATTERN},
        ]
        return document

    def test_build_document_respects_the_overrides_argument(self):
        """build_document(overrides=...) is accepted and respected.

        THE RED of behaviour 12: ``build_document`` takes no arguments
        today, so the keyword call raises ``TypeError`` — the injection
        path does not exist yet. When the green lands (the optional
        ``overrides`` keyword, default ``None``, implemented), the
        built document must carry exactly the overridden
        ``autoDenyPatterns`` list, and the no-argument call (behaviour
        3's golden parity) must be unaffected.
        """
        build_document = self._get_build_document()
        overridden = build_document(
            overrides={
                "autoDenyPatterns": [{"pattern": self._HOSTILE_PATTERN}],
            }
        )
        self.assertEqual(
            overridden.get("permissionGate", {}).get("autoDenyPatterns"),
            [{"pattern": self._HOSTILE_PATTERN}],
            "build_document must respect the overrides argument: the "
            "built document must carry exactly the overridden "
            "autoDenyPatterns list",
        )
        # The no-argument call is unchanged: behaviour 3's golden parity
        # must stay green (the overrides argument must default to None,
        # not mutate the fixed document).
        self.assertEqual(
            build_document(),
            self._get_build_document()(),
            "the no-argument call must be unchanged when the overrides "
            "argument is absent (behaviour 3's golden parity)",
        )

    def test_hostile_pattern_round_trips_through_json_dumps(self):
        """The hostile pattern survives json.dumps -> json.loads byte-identical.

        (a) of the manager's split: a document carrying the hostile
        pattern is serialized with ``json.dumps`` (the same dict +
        ``json.dumps`` path the seam will use — any style, whitespace
        is not part of the contract) and parsed back; the hostile
        pattern value must be byte-identical in the parsed result.
        This PASSES today: ``json.dumps`` is valid by construction, so
        a value containing a quote, a backslash and a newline
        round-trips exactly. It stays green once the green lands,
        pinning the property the whole behaviour exists for — never
        string substitution.
        """
        document = self._document_with_hostile_pattern()
        rendered = json.dumps(document, indent=2)
        parsed = json.loads(rendered)
        patterns = parsed.get("permissionGate", {}).get("autoDenyPatterns")
        self.assertIsInstance(
            patterns,
            list,
            "the parsed document must carry the overridden "
            "autoDenyPatterns list",
        )
        self.assertEqual(
            [entry.get("pattern") for entry in patterns],
            [self._HOSTILE_PATTERN],
            "a pattern containing a quote, a backslash and a newline "
            "must parse back byte-identical - valid by construction "
            "via json.dumps, never string substitution",
        )
        self.assertIsInstance(
            parsed.get("enabled"),
            bool,
            "the round-trip must keep the document's booleans real "
            "booleans (json validity by construction)",
        )


class TestPackagePinIsExact(PiguardrailsTestCase):
    """Behaviour 13: package-pin-is-exact.

    Given: the module's package source constant. When: it is read.
    Then: it is exactly ``npm:@aliou/pi-guardrails@0.21.0`` — a pinned
    version, never a range or a bare name. Error: a bare or
    range-pinned spelling fails the test.

    The shape ``npm:<name>@<version>`` is the Pi package source form
    and "Versioned npm specifications are pinned" (doc/external/
    pi-dev/packages.md, "Choose a source"); the adopted pin 0.21.0 is
    manager-settled (0.20.0 fixed upstream #123, ``plans/
    pi-guardrails.md`` Reuse check).

    Red: the module has no ``PACKAGE_SOURCE`` constant yet, so both
    tests fail at the ``assertIsNotNone`` guard inside the fetch
    helper — a named-test failure on the missing attribute, never a
    collection error.
    """

    _EXPECTED_PIN = "npm:@aliou/pi-guardrails@0.21.0"

    # Range operators that would turn the pin into a range. The
    # leading ``=`` covers ``>=``/``<=``/``=``; ``*`` is the bare
    # wildcard.
    _RANGE_OPERATORS = ("^", "~", ">=", "<=", ">", "<", "=", "*")

    def test_package_source_is_exactly_the_pinned_version(self):
        package_source = self._get_package_source()
        self.assertEqual(
            package_source,
            self._EXPECTED_PIN,
            "PACKAGE_SOURCE must be exactly the pinned source "
            "npm:@aliou/pi-guardrails@0.21.0 - a pinned version, "
            "never a range or a bare name",
        )

    def test_package_source_is_not_bare_or_range(self):
        package_source = self._get_package_source()
        self.assertEqual(
            package_source,
            self._EXPECTED_PIN,
            "PACKAGE_SOURCE must match the exact pinned shape "
            "npm:@aliou/pi-guardrails@0.21.0",
        )
        # A bare name carries nothing after the last ``@``; the version
        # part must be present.
        version = package_source.rsplit("@", 1)[-1]
        self.assertNotEqual(
            version,
            "",
            "PACKAGE_SOURCE must carry a version after the last @; a "
            "bare name (no version) is not a pin",
        )
        # A range operator anywhere in the version part is a drift to a
        # range, not an exact pin.
        for operator in self._RANGE_OPERATORS:
            self.assertNotIn(
                operator,
                version,
                "PACKAGE_SOURCE must be a pinned version; %r is a range "
                "operator, never an exact pin" % operator,
            )


if __name__ == "__main__":
    unittest.main()
