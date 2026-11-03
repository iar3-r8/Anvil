"""Guardrails document builder - one job: build the guardrails document.

``plans/pi-guardrails.md`` behaviour 3 pins the document: the value choices
are manager-settled ledger decisions, not inputs, so ``build_document``
takes no arguments and returns the document as a dict. The target is
``tests/fixtures/golden_pi_guardrails.json``; equality is on parsed
structures (key ordering and whitespace are not part of the contract), and
the document is built by construction here, never read from the fixture at
runtime. The schema source of truth is
``doc/external/pi-guardrails/schema.md``.

One exception type: ``GuardrailsError``. ``build_document`` calls the
public ``validate_document`` seam (behaviour 4 ledger decision); the
seam validates the top-level key set (behaviour 9), the ``features``
level (behaviour 4), the ``permissionGate.autoDenyPatterns`` entries
(behaviour 5) and the ``policies.rules`` entries (behaviour 6).
Behaviour 10 (emitted-keys drift guard) is pin-skip per the ledger: the
per-level allowed-key constants (``TOP_LEVEL_KEYS``, ``FEATURE_KEYS``,
``PROTECTION_VALUES``) and the golden parity already constrain every
emitted key at its level.
"""

from typing import Any, Dict, FrozenSet, List, Optional

# The pinned npm source for the Pi runtime to install
# (doc/external/pi-dev/packages.md — "Versioned npm specifications
# are pinned"); 0.21.0 because 0.20.0 fixed upstream #123 (a
# path-extraction false positive); source-reviewed per Pi's package
# warning (verdict on issue #67).
PACKAGE_SOURCE = "npm:@aliou/pi-guardrails@0.21.0"

# The schema's exact feature-key set (``doc/external/pi-guardrails/schema.md``:
# ``features`` allows exactly these four booleans, ``additionalProperties:
# false``). Behaviour 4 checks this level; behaviour 9's top-level check
# follows this pattern with ``TOP_LEVEL_KEYS``.
FEATURE_KEYS: FrozenSet[str] = frozenset(
    ["pathAccess", "permissionGate", "policies", "protectEnvFiles"]
)

# The schema's exact top-level key set (``doc/external/pi-guardrails/
# schema.md``: ``GuardrailsConfig`` is ``additionalProperties: false``,
# allowing exactly these ten keys). Behaviour 9 checks this level; the
# built document uses a subset (``enabled``, ``features``,
# ``permissionGate``, ``policies``), and the check is one-way - it
# rejects unlisted keys, it does not require the allowed ones
# (behaviour 10's drift guard is pin-skip per the ledger).
TOP_LEVEL_KEYS: FrozenSet[str] = frozenset(
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

# The schema's ``Protection`` enum values (``doc/external/pi-guardrails/
# schema.md``: ``Protection`` is exactly ``none | readOnly | noAccess``).
# Behaviour 6 checks every ``PolicyRule.protection`` against this set.
PROTECTION_VALUES: FrozenSet[str] = frozenset(
    ["none", "readOnly", "noAccess"]
)

class GuardrailsError(Exception):
    """Any refusal to build the guardrails document.

    A single exception type covers every refusal, so the caller
    (``render.guardrails_settings``, behaviour 11) needs one ``except``
    clause and translates to ``RenderError``. The message names the
    offending value so the caller knows which key to fix.
    """


def _validate_top_level(document: Dict[str, Any]) -> None:
    """Check the top-level key set against the schema (behaviour 9).

    Every top-level key must be in ``TOP_LEVEL_KEYS`` (schema
    ``GuardrailsConfig``, ``additionalProperties: false``). The check
    is one-way: unlisted keys are rejected, missing allowed keys are
    not - the built document uses a subset of the allowed keys and
    must stay valid. The ``features`` level is not re-checked here;
    ``_validate_features`` owns it (behaviour 4), so behaviour 9's
    nested clause is enforced exactly once. Raises
    ``GuardrailsError`` naming the offending key and its level.
    """
    for key in sorted(document):
        if key not in TOP_LEVEL_KEYS:
            raise GuardrailsError(
                "guardrails has unlisted top-level key %r; allowed: %s"
                % (key, sorted(TOP_LEVEL_KEYS))
            )


def _validate_features(features: Dict[str, Any]) -> None:
    """Check the ``features`` level against the schema (behaviour 4).

    Every value must be a real boolean - ``type(value) is bool`` rejects
    the truthy non-booleans JSON can carry - and the key set must be
    exactly ``FEATURE_KEYS`` (schema ``additionalProperties: false``).
    Raises ``GuardrailsError`` naming the offending key, checking unlisted
    keys before type errors so a single mutation surfaces a single cause.
    """
    for key in sorted(features):
        if key not in FEATURE_KEYS:
            raise GuardrailsError(
                "guardrails features has unlisted key %r; allowed: %s"
                % (key, sorted(FEATURE_KEYS))
            )
    for key in sorted(features):
        if type(features[key]) is not bool:
            raise GuardrailsError(
                "guardrails features.%s must be a boolean, got %r"
                % (key, type(features[key]).__name__)
            )


def _validate_pattern_config(entry: Any, where: str) -> None:
    """Check one ``PatternConfig`` entry against the schema.

    Shared by ``_validate_auto_deny_patterns`` (behaviour 5) and
    ``_validate_policy_rules`` (behaviour 6): every entry must be an
    object carrying a non-empty ``pattern`` string - the required key
    of the schema. ``regex``/``description``/``terminate`` are optional
    and out of scope here. ``where`` is the caller-supplied location,
    named in the error message. Raises ``GuardrailsError`` naming the
    offending entry.
    """
    if not isinstance(entry, dict):
        raise GuardrailsError(
            "guardrails %s must be an object (PatternConfig), got %s"
            % (where, type(entry).__name__)
        )
    pattern = entry.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise GuardrailsError(
            "guardrails %s must carry a non-empty 'pattern' string, got %r"
            % (where, pattern)
        )


def _validate_auto_deny_patterns(auto_deny: List[Dict[str, Any]]) -> None:
    """Check ``permissionGate.autoDenyPatterns`` (behaviour 5).

    Every entry must be a ``PatternConfig`` (schema) - see
    ``_validate_pattern_config``. The other ``permissionGate`` keys are
    not checked (behaviour 10's emitted-key drift guard owns the
    breadth). Raises ``GuardrailsError`` naming the offending entry.
    """
    for index, entry in enumerate(auto_deny):
        _validate_pattern_config(
            entry, "permissionGate.autoDenyPatterns[%d]" % index
        )


def _validate_policy_rules(rules: List[Dict[str, Any]]) -> None:
    """Check ``policies.rules`` (behaviour 6).

    Every rule must be an object (schema: ``PolicyRule``) carrying the
    three schema-required keys: a non-empty ``id`` string, a
    ``patterns`` list whose entries are ``PatternConfig`` objects, and
    a ``protection`` value from the schema's ``Protection`` enum. The
    optional ``PolicyRule`` keys (``allowedPatterns``, ``blockMessage``,
    ``description``, ``enabled``, ``name``, ``onlyIfExists``,
    ``respectCwd``) are not checked - behaviour 10's emitted-key drift
    guard owns the breadth. Raises ``GuardrailsError`` naming the rule
    by id when one is available, by index otherwise.
    """
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise GuardrailsError(
                "guardrails policies.rules[%d] must be an object "
                "(PolicyRule), got %s" % (index, type(rule).__name__)
            )
        rule_id = rule.get("id")
        if isinstance(rule_id, str) and rule_id:
            label = "policies.rules[%r]" % rule_id
        else:
            label = "policies.rules[%d]" % index
        if not isinstance(rule_id, str) or not rule_id:
            raise GuardrailsError(
                "guardrails %s must carry a non-empty 'id' string, got %r"
                % (label, rule_id)
            )
        patterns = rule.get("patterns")
        if not isinstance(patterns, list):
            raise GuardrailsError(
                "guardrails %s must carry a 'patterns' list, got %r"
                % (label, patterns)
            )
        for pindex, entry in enumerate(patterns):
            _validate_pattern_config(
                entry, "%s.patterns[%d]" % (label, pindex)
            )
        protection = rule.get("protection")
        if not isinstance(protection, str) or protection not in PROTECTION_VALUES:
            raise GuardrailsError(
                "guardrails %s must carry 'protection' one of %s, got %r"
                % (label, sorted(PROTECTION_VALUES), protection)
            )


def _validate(document: Dict[str, Any]) -> None:
    """Check the built document before it is returned.

    Called by ``build_document``; validates the top-level key set
    (behaviour 9), the ``features`` level (behaviour 4), the
    ``permissionGate.autoDenyPatterns`` entries (behaviour 5) and the
    ``policies.rules`` entries (behaviour 6). Behaviour 10 (emitted-keys
    drift guard) is pin-skip per the ledger.
    """
    _validate_top_level(document)
    _validate_features(document["features"])
    _validate_auto_deny_patterns(
        document["permissionGate"]["autoDenyPatterns"]
    )
    _validate_policy_rules(document["policies"]["rules"])


def validate_document(document: Dict[str, Any]) -> None:
    """Public validation seam (behaviour 4, manager-pinned by the ledger).

    Raises ``GuardrailsError`` naming the offending key when the document
    violates the schema; returns ``None`` when it passes. ``build_document``
    calls it on every built document, and behaviours 4 and 5's
    error-clause tests call it directly with malformed deep copies -
    their error cases are unreachable through the no-argument builder.
    """
    _validate(document)


def build_document(
    overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """The guardrails document, fixed by construction (behaviour 3).

    Returns a dict that equals ``tests/fixtures/golden_pi_guardrails.json``
    exactly under parsed equality. The value choices are the plan's ledger
    decisions: ``protectEnvFiles`` is explicitly ``false`` (the issue
    enables only ``policies`` + ``permissionGate``; the ``secrets`` rule
    already covers env files, and the package's built-in env layer is
    partly ``fd``-dependent); ``guardrails-config`` is ``readOnly`` (the
    threat is an agent editing its own gate - ``readOnly`` blocks the edit
    without blocking reads); ``autoDenyPatterns`` entries carry only the
    required ``pattern`` key (documented default is substring match);
    ``onlyIfExists`` is an explicit ``true``; no ``$schema``/``version``
    keys (``version`` is "stamped by migrations").

    ``overrides`` (behaviour 12, manager-pinned) is an optional dict whose
    ``autoDenyPatterns`` key - the only override surface - replaces the
    built ``permissionGate.autoDenyPatterns`` list before validation runs.
    The no-argument call is unchanged, so behaviour 3's golden parity is
    unaffected. ``validate_document`` still runs on the result, so an
    invalid override (e.g. a pattern-less entry) is refused, not emitted.
    """
    document: Dict[str, Any] = {
        "enabled": True,
        "features": {
            # pathAccess stays off: the gate fails closed with no TTY
            # (upstream #123, #136) - a hard block, not a hang, so a blocked
            # call must not be confused with a prompt that waits - and the
            # open upstream path-extraction false positives (#89:
            # 2>/dev/null, #90: 2>&1, #136: node -e arithmetic) would kill
            # ordinary runs instead of raising a dismissable prompt; the
            # sandbox container (#51) is already the path boundary.
            "pathAccess": False,
            "permissionGate": True,
            "policies": True,
            "protectEnvFiles": False,
        },
        "permissionGate": {
            "autoDenyPatterns": [
                {"pattern": "git commit"},
                {"pattern": "git push"},
                {"pattern": "git reset"},
                {"pattern": "git rebase"},
            ],
        },
        "policies": {
            "rules": [
                {
                    "id": "secrets",
                    "onlyIfExists": True,
                    "patterns": [
                        {"pattern": ".env"},
                        {"pattern": "*.pem"},
                        {"pattern": "*.key"},
                    ],
                    "protection": "noAccess",
                },
                {
                    "id": "guardrails-config",
                    "patterns": [{"pattern": ".pi/extensions/guardrails.json"}],
                    "protection": "readOnly",
                },
            ],
        },
    }
    if overrides is not None and "autoDenyPatterns" in overrides:
        document["permissionGate"]["autoDenyPatterns"] = overrides[
            "autoDenyPatterns"
        ]
    _validate(document)
    return document
