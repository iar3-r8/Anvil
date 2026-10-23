"""GitHub ruleset builder (``plans/ruleset-write.md``).

This module builds the dict for Anvil's importable main-branch guard
ruleset: the five-rule shape reproducing issue #50 (``non_fast_forward``,
``deletion``, ``update``, ``pull_request``, ``file_path_restriction``),
scoped to ``~DEFAULT_BRANCH``. It renders the dict to import-ready JSON
and writes the rendered text to disk, and renders the manual import
steps.

``build_ruleset()`` returns a fresh dict on every call — no module-level
dict is ever returned by reference — so a caller that mutates one result
cannot poison the next call.

Stdlib only. One exception type: ``RulesetError`` (used by the
behaviours that touch the filesystem; the CLI maps it to ``EXIT_CONFIG``).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def default_output_path(target: Path) -> Path:
    """Return the default output path for the written ruleset.

    A pure path join: ``target / ".github-ruleset.json"``. Nothing
    here touches the filesystem, so a ``target`` that is a file rather
    than a directory is not rejected — the write is the only place the
    filesystem is touched.
    """
    return target / ".github-ruleset.json"


def write_ruleset(path: Path, text: str, force: bool = False) -> Path:
    """Write the rendered ruleset text to ``path`` and return ``path``.

    The file holds ``text`` verbatim, encoded UTF-8. If the parent
    directory does not exist, a :class:`RulesetError` is raised naming
    the absent directory and nothing partial is created: no file at any
    level, and the parent tree is not created either.

    An existing path is never silently clobbered:

    - ``force=False`` and a file at ``path`` raises a
      :class:`RulesetError` naming the path and the ``--force`` flag,
      leaving the file's bytes untouched;
    - ``force=True`` and a file at ``path`` overwrites it and returns
      ``path``;
    - ``path`` is a directory — with or without ``force`` — raises a
      :class:`RulesetError`: a write to a directory must never silently
      succeed, and ``force`` cannot turn a directory into a write
      target.
    """
    if not path.parent.is_dir():
        raise RulesetError(
            "cannot write ruleset to {path}: its parent directory "
            "{parent} does not exist".format(path=path, parent=path.parent)
        )
    if path.is_dir():
        raise RulesetError(
            "cannot write ruleset to {path}: it is a directory".format(
                path=path
            )
        )
    if path.exists() and not force:
        raise RulesetError(
            "refusing to overwrite {path}: an existing file is present; "
            "pass --force to overwrite it".format(path=path)
        )
    path.write_text(text, encoding="utf-8")
    return path


def import_steps(
    repository: Optional[Tuple[str, str]],
    output_path: Path,
) -> List[str]:
    """Return the documented manual import sequence as readable lines.

    Follows the "Importing a ruleset" sequence in
    ``doc/external/github/managing-rulesets-for-a-repository.md``:
    Settings, the Rulesets settings page, the "New ruleset" dropdown,
    "Import a ruleset", open the exported JSON file, then review and
    Create. Every line is an actual step from that sequence — none are
    invented.

    When ``repository`` is an ``(owner, name)`` pair, the first line is
    the direct ``https://github.com/{owner}/{repo}/settings/rules``
    URL — the documented shortcut of adding ``/rules`` to the
    repository's URL. When ``repository`` is ``None`` (a target with
    no GitHub origin), the navigation steps are given instead and no
    line contains a guessed GitHub URL.

    ``output_path`` is rendered into the text and its name is stated in
    the open step; this function never opens the file and never touches
    git or GitHub.
    """
    file_name = output_path.name
    if repository is not None:
        owner, repo = repository
        steps: List[str] = [
            "Open the repository's Rulesets settings page: "
            "https://github.com/{owner}/{repo}/settings/rules".format(
                owner=owner, repo=repo
            ),
        ]
    else:
        steps = [
            "On GitHub, navigate to the main page of the repository.",
            "Under the repository name, click Settings. If you cannot "
            "see the 'Settings' tab, select the dropdown menu, then "
            "click Settings.",
            "In the left sidebar, under 'Code, planning, and "
            "automation', click Rulesets, then click Rulesets.",
        ]
    steps.extend(
        [
            "Select the New ruleset dropdown, then click Import a "
            "ruleset.",
            "Open the exported JSON file {path} ({name}).".format(
                path=output_path, name=file_name
            ),
            "Review the imported ruleset and click Create.",
        ]
    )
    return steps
