"""Build the pre-filled fine-grained personal access token creation URL.

One job: half 2 of issue #75 — the token *recipe*. ``build_recipe_url``
returns a creation URL whose query pre-fills the exact grant the loop
needs and nothing else. The URL is a specified artifact: the token text
itself is shown by GitHub's UI once and never passes through Anvil. The
value of the recipe is that the withholding is visible by absence — a
reader of the URL (and of the [PIN] test on its query) can see that
``administration``, ``workflows`` and ``metadata`` were never granted.

Parameter names are GitHub's, not invented: the saved page
``doc/external/github/fine-grained-personal-access-tokens.md`` (section
"Pre-filling fine-grained personal access token details using URL
parameters") documents ``target_name`` plus one ``<permission>``
parameter per grant, with ``write`` implying ``read``. ``actions=read``
is the read the agent needs to inspect its own PR's CI — read-only, and
the CI edit path stays closed behind the ``workflows`` withholding; and
since that same page documents a fine-grained PAT cannot call the Checks
API, "read the CI logs" means Actions run/job logs, not Check Runs.
"""

import urllib.parse

#: The creation page every recipe URL points at.
_BASE_URL = "https://github.com/settings/personal-access-tokens/new"


class TokenRecipeError(Exception):
    """A recipe input that cannot be turned into a creation URL."""


def build_recipe_url(owner: str, repo: str) -> str:
    """Return the pre-filled fine-grained token creation URL for ``owner``.

    The query carries exactly ``target_name`` (the owner) and the four
    grants ``contents=write``, ``pull_requests=write``, ``issues=write``
    and ``actions=read``, built with :func:`urllib.parse.urlencode` —
    never string substitution, so an owner containing ``&`` or ``+``
    round-trips through the query.

    ``repo`` is not a query parameter: the saved page documents no
    parameter for the specific repository — choosing "Only select
    repositories" and naming the target is a UI step. It is carried in
    the signature because the caller resolves owner and repo together,
    and it belongs in the recipe steps (behaviour 14), not the URL.

    Raises :class:`TokenRecipeError` if ``owner`` is empty or
    whitespace-only — the owner is the ``target_name`` and is never
    guessed. ``repo`` is not validated here.
    """
    if not owner or not owner.strip():
        raise TokenRecipeError(
            "refusing to build a recipe URL without an owner: "
            "target_name is the resource owner and is never guessed"
        )
    # Deliberately absent from this dict: administration (the repo could
    # be deleted or reconfigured), workflows (CI could be edited) and
    # metadata (implicit and read-only). The recipe's value is that the
    # withholding is visible by absence — a convenience edit adding
    # administration=read must break behaviour 13's [PIN] on the query.
    query = {
        "target_name": owner,
        "contents": "write",
        "pull_requests": "write",
        "issues": "write",
        "actions": "read",
    }
    return _BASE_URL + "?" + urllib.parse.urlencode(query)
