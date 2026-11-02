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
seam currently validates the ``features`` level (behaviour 4) and the
``permissionGate.autoDenyPatterns`` entries (behaviour 5). Behaviour 9
(unknown-key rejection) and behaviour 10 (emitted-keys drift guard)
extend the per-level allowed-key checks in their later red/green
cycles, following the ``FEATURE_KEYS`` module-constant pattern.
"""

from typing import Any, Dict, FrozenSet, List

# The schema's exact feature-key set (``doc/external/pi-guardrails/schema.md``:
# ``features`` allows exactly these four booleans, ``additionalProperties:
# false``). Behaviour 4 checks this level; behaviours 9/10 add their own
# per-level constants (top level, then the emitted-key drift guard) that
# follow this pattern.
FEATURE_KEYS: FrozenSet[str] = frozenset(
    ["pathAccess", "permissionGate", "policies", "protectEnvFiles"]
)

class GuardrailsError(Exception):
    """Any refusal to build the guardrails document.

    A single exception type covers every refusal, so the caller
    (``render.guardrails_settings``, behaviour 11) needs one ``except``
    clause and translates to ``RenderError``. The message names the
    offending value so the caller knows which key to fix.
    """


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


def _validate_auto_deny_patterns(auto_deny: List[Dict[str, Any]]) -> None:
    """Check ``permissionGate.autoDenyPatterns`` (behaviour 5).

    Every entry must be an object (schema: ``PatternConfig``) carrying
    a non-empty ``pattern`` string - the required key of the schema.
    ``regex``/``description``/``terminate`` are optional and out of
    scope here; the other ``permissionGate`` keys are not checked
    either (behaviour 10's emitted-key drift guard owns the breadth).
    Raises ``GuardrailsError`` naming the offending entry.
    """
    for index, entry in enumerate(auto_deny):
        if not isinstance(entry, dict):
            raise GuardrailsError(
                "guardrails permissionGate.autoDenyPatterns[%d] must be "
                "an object (PatternConfig), got %s"
                % (index, type(entry).__name__)
            )
        pattern = entry.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise GuardrailsError(
                "guardrails permissionGate.autoDenyPatterns[%d] must carry "
                "a non-empty 'pattern' string, got %r" % (index, pattern)
            )


def _validate(document: Dict[str, Any]) -> None:
    """Check the built document before it is returned.

    Called by ``build_document``; currently validates the ``features``
    level (behaviour 4) and the ``permissionGate.autoDenyPatterns``
    entries (behaviour 5). Behaviour 9 (unknown-key rejection at the
    top level) and behaviour 10 (emitted-keys drift guard) add their
    per-level checks here in their later red/green cycles.
    """
    _validate_features(document["features"])
    _validate_auto_deny_patterns(
        document["permissionGate"]["autoDenyPatterns"]
    )


def validate_document(document: Dict[str, Any]) -> None:
    """Public validation seam (behaviour 4, manager-pinned by the ledger).

    Raises ``GuardrailsError`` naming the offending key when the document
    violates the schema; returns ``None`` when it passes. ``build_document``
    calls it on every built document, and behaviours 4 and 5's
    error-clause tests call it directly with malformed deep copies -
    their error cases are unreachable through the no-argument builder.
    """
    _validate(document)


def build_document() -> Dict[str, Any]:
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
    _validate(document)
    return document
