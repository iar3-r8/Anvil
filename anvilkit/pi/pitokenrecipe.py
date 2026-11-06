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
from typing import List

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
    # administration, workflows and metadata are deliberately absent from
    # this dict: administration could delete or reconfigure the repository
    # and workflows could edit CI, and the withholding is the value - a
    # "tidying" edit that grants administration=read re-opens the exact
    # hole the token-scope probes exist to catch. The pin over the query
    # parameters in tests/test_pitokenrecipe.py is what turns that edit
    # red.
    query = {
        "target_name": owner,
        "contents": "write",
        "pull_requests": "write",
        "issues": "write",
        "actions": "read",
    }
    return _BASE_URL + "?" + urllib.parse.urlencode(query)


def recipe_steps(owner: str, repo: str, url: str) -> List[str]:
    """Return the ordered UI steps for creating the token from ``url``.

    Display text for a human, following the saved page
    ``doc/external/github/fine-grained-personal-access-tokens.md``, section
    "Creating a fine-grained personal access token" (source URL:
    https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/
    managing-your-personal-access-tokens): the creation page, the resource
    owner, Repository access with "Only select repositories", the selected
    repository, then the four Repository permissions. The ``repo`` name
    appears only here — it is not a URL parameter (behaviour 12). The last
    three steps are the plan's recorded caveats, each also on the saved
    page: a fine-grained PAT cannot call the Checks API; tokens always
    include read-only access to all public repositories; and the token is
    kept on the host driver outside the container, so the agent cannot
    read it. No step instructs pasting the token anywhere Anvil reads.

    The raw ``url`` is shown in its own step *after* the permission steps,
    not in the first: its query text contains the literal parameter names
    (``contents=write``, …, ``actions=read``) and the owner, and the
    behaviour-14 ordering pins the first mentions of the target, the repo
    and each permission to the documented sequence — the URL step would
    jump ahead of them.
    """
    return [
        "Open the pre-filled creation page: use the recipe URL printed "
        "with these steps; it opens GitHub's 'Generate new token' page "
        "with the target and the four grants already filled in.",
        "Under Resource owner, keep the resource owner set to {} "
        "(the URL pre-fills it as target_name).".format(owner),
        "Under Repository access, choose Only select repositories.",
        "Under the Selected repositories dropdown, select {} "
        "and nothing else.".format(repo),
        "Under Repository permissions, set Contents to Read and write "
        "(pre-filled by the URL).",
        "Set Pull requests to Read and write (pre-filled).",
        "Set Issues to Read and write (pre-filled).",
        "Set Actions to Read only (pre-filled); the CI edit path stays "
        "closed behind the workflows withholding.",
        "The recipe URL, which pre-fills exactly the grants above and "
        "nothing else — administration, workflows and metadata are "
        "withheld and visible by absence in its query: {}".format(url),
        "Caveat: a fine-grained PAT cannot call the Checks API, so CI is "
        "read as Actions runs and jobs, not Check Runs.",
        "Caveat: every fine-grained token keeps read-only access to all "
        "public repositories on GitHub — only this token's reach beyond "
        "public repos is scoped to {}.".format(repo),
        "Caveat: the token lives on the host driver outside the container, "
        "so the agent cannot read it; GitHub's UI shows it once and Anvil "
        "never takes it.",
    ]
