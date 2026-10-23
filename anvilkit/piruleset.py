"""GitHub ruleset builder (``plans/ruleset-write.md``).

This module builds the dict for Anvil's importable main-branch guard
ruleset: the five-rule shape reproducing issue #50 (``non_fast_forward``,
``deletion``, ``update``, ``pull_request``, ``file_path_restriction``),
scoped to ``~DEFAULT_BRANCH``. Later behaviours render it to JSON,
write it, and render the manual import steps; this behaviour only
builds the dict.

``build_ruleset()`` returns a fresh dict on every call — no module-level
dict is ever returned by reference — so a caller that mutates one result
cannot poison the next call.

Stdlib only. One exception type: ``RulesetError`` (used by the
behaviours that touch the filesystem; the CLI maps it to ``EXIT_CONFIG``).
"""

import json
from typing import Any, Dict


class RulesetError(Exception):
    """Raised when the ruleset cannot be rendered, written or imported."""


def build_ruleset() -> Dict[str, Any]:
    """Return the pinned five-rule main-branch guard ruleset.

    Freshly built on every call: each dict, list and rule in the result
    is a new object, so mutating the returned structure cannot affect a
    later call.
    """
    return {
        "name": "Anvil main guard",
        "target": "branch",
        "source_type": "Repository",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "bypass_actors": [],
        "rules": [
            {"type": "non_fast_forward"},
            {"type": "deletion"},
            {
                "type": "update",
                "parameters": {"update_allows_fetch_and_merge": True},
            },
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 1,
                    "require_code_owner_review": False,
                    "require_last_push_approval": True,
                    "dismiss_stale_reviews_on_push": True,
                    "required_review_thread_resolution": False,
                },
            },
            {
                "type": "file_path_restriction",
                "parameters": {
                    "restricted_file_paths": [".github/workflows/**"]
                },
            },
        ],
    }


def render_ruleset_json(ruleset: Dict[str, Any]) -> str:
    """Render the ruleset dict to import-ready JSON.

    Follows the project convention for structured output: the JSON text
    is produced by ``json.dumps`` on a dict, never by string
    substitution, so a value containing a quote or backslash yields
    valid JSON by construction. The text ends with exactly one
    trailing newline.

    A round-trip through ``json.loads`` returns a dict equal to
    ``ruleset``.
    """
    return json.dumps(ruleset, indent=2) + "\n"
