"""Guardrails document builder - one job: build the guardrails document.

``plans/pi-guardrails.md`` behaviour 3 pins the document: the value choices
are manager-settled ledger decisions, not inputs, so ``build_document``
takes no arguments and returns the document as a dict. The target is
``tests/fixtures/golden_pi_guardrails.json``; equality is on parsed
structures (key ordering and whitespace are not part of the contract), and
the document is built by construction here, never read from the fixture at
runtime. The schema source of truth is
``doc/external/pi-guardrails/schema.md``.

One exception type: ``GuardrailsError``. This cycle builds only the fixed
document; behaviour 9 (unknown-key rejection) and behaviour 10 (emitted-keys
drift guard) extend ``_validate`` in their later red/green cycles.
"""

from typing import Any, Dict


class GuardrailsError(Exception):
    """Any refusal to build the guardrails document.

    A single exception type covers every refusal, so the caller
    (``render.guardrails_settings``, behaviour 11) needs one ``except``
    clause and translates to ``RenderError``. The message names the
    offending value so the caller knows which key to fix.
    """


def _validate(document: Dict[str, Any]) -> None:
    """Check the built document before it is returned.

    A no-op this cycle: behaviour 3 builds the fixed document and
    ``_validate`` exists as the explicit seam where behaviour 9 (unknown-key
    rejection) and behaviour 10 (schema drift guard) will check key sets,
    so ``build_document`` does not grow in those cycles.
    """


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
