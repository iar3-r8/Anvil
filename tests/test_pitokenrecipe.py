"""Tests for anvilkit.pi.pitokenrecipe - the pre-filled fine-grained token
creation recipe (behaviours 12-13 of plans/verify-guards-token.md).

Written before the implementation (TDD RED step). The production module
``anvilkit.pi.pitokenrecipe`` does not exist yet, so every test loads it
through ``_pitokenrecipe``, which fails with a clear assertion instead of
letting a collection-time ImportError mask the reason the suite is red.

Parameter names asserted here are GitHub's, not invented: the saved page
``doc/external/github/fine-grained-personal-access-tokens.md``, section
"Pre-filling fine-grained personal access token details using URL
parameters" (``target_name``, ``<permission>=read|write|admin``) and its
"Repository permissions" table (``contents``/``pull_requests``/``issues``/
``actions`` support read+write; ``metadata`` is ``read`` only; ``workflows``
is ``write`` only). That page documents no query parameter for the specific
repository - "Only select repositories" is a UI choice, so the repo name
must never appear in the URL.

No test writes a file or makes a network call: ``build_recipe_url`` is a
pure string builder, and its observable surface is the returned string.
"""

import importlib
import importlib.util
import sys
import unittest
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The creation page every recipe URL must point at.
BASE_URL = "https://github.com/settings/personal-access-tokens/new"

# Behaviour 12's grant, exactly: the loop must push (contents, pull_requests,
# issues are write); the loop only reads its own CI (actions is read).
GRANTED = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "actions": "read",
}

# Behaviour 13's withholdings: administration (the repo could be deleted or
# reconfigured), workflows (CI could be edited), metadata (implicit and
# read-only, so it is never spelled out).
WITHHELD = ("administration", "workflows", "metadata")

# Several owners for the pin, including two that are not plain ASCII-safe and
# therefore need percent-encoding in the query.
OWNERS = ("octodemo", "octo&demo+bot", "another owner")


class TokenRecipeTestCase(unittest.TestCase):
    def _pitokenrecipe(self):
        """Import anvilkit.pi.pitokenrecipe, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pi.pitokenrecipe")
        self.assertIsNotNone(
            spec,
            "anvilkit.pi.pitokenrecipe cannot be imported; the pre-filled "
            "token recipe (behaviours 12-13 of plans/verify-guards-token.md) "
            "has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pi.pitokenrecipe")

    def _get_build_recipe_url(self):
        """Fetch ``anvilkit.pi.pitokenrecipe.build_recipe_url``, failing clearly if absent."""
        pitokenrecipe = self._pitokenrecipe()
        build = getattr(pitokenrecipe, "build_recipe_url", None)
        self.assertTrue(
            callable(build),
            "anvilkit.pi.pitokenrecipe.build_recipe_url is not callable; "
            "behaviour 12 has not been implemented yet",
        )
        return build

    def _get_token_recipe_error(self):
        """Fetch the module's one exception type, ``TokenRecipeError``, failing clearly if absent."""
        pitokenrecipe = self._pitokenrecipe()
        token_recipe_error = getattr(pitokenrecipe, "TokenRecipeError", None)
        self.assertTrue(
            isinstance(token_recipe_error, type)
            and issubclass(token_recipe_error, Exception),
            "anvilkit.pi.pitokenrecipe.TokenRecipeError is not an exception "
            "type; the module's single exception type (behaviour 12's "
            "error path) has not been implemented yet",
        )
        return token_recipe_error

    @staticmethod
    def _query(url):
        """The recipe URL's query, parsed to a ``{param: [values]}`` map."""
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


class BuildRecipeUrlTests(TokenRecipeTestCase):
    """Behaviour 12: build_recipe_url(owner, repo) -> the pre-filled creation URL."""

    def test_build_recipe_url_starts_with_the_creation_page_and_a_query(self):
        build = self._get_build_recipe_url()

        url = build("octodemo", "my-repo")

        self.assertIsInstance(url, str, "build_recipe_url must return a str")
        self.assertTrue(
            url.startswith(BASE_URL + "?"),
            "the URL must start with the creation page plus a query, got: "
            + url,
        )

    def test_build_recipe_url_carries_exactly_the_granted_permission_parameters(self):
        build = self._get_build_recipe_url()

        url = build("octodemo", "my-repo")

        query = self._query(url)
        self.assertEqual(
            query.get("target_name"),
            ["octodemo"],
            "target_name must be the owner, per the saved page's supported "
            "query parameters",
        )
        self.assertEqual(
            query.get("contents"),
            ["write"],
            "contents=write: the loop must push",
        )
        self.assertEqual(
            query.get("pull_requests"),
            ["write"],
            "pull_requests=write: the loop must push",
        )
        self.assertEqual(
            query.get("issues"),
            ["write"],
            "issues=write: the loop must push",
        )
        self.assertEqual(
            query.get("actions"),
            ["read"],
            "actions=read: the loop only reads its own CI",
        )

    def test_build_recipe_url_percent_encodes_the_owner_so_the_query_round_trips(self):
        # An owner with '&', '+' and a space cannot survive string
        # concatenation into a query: the '&' would split parameters and the
        # '+' would be misread by parse_qs. urlencode percent-encodes all
        # three, and parse_qs must hand the owner back verbatim.
        build = self._get_build_recipe_url()
        owner = "octo&demo+bot"

        url = build(owner, "my-repo")

        query = self._query(url)
        self.assertEqual(
            query.get("target_name"),
            [owner],
            "the query must be built with urllib.parse.urlencode (never "
            "string substitution), so parse_qs round-trips the owner "
            "verbatim; got: " + repr(query.get("target_name")),
        )

    def test_build_recipe_url_never_carries_the_repo_name_as_a_parameter(self):
        # The saved page documents no query parameter for the specific
        # repository - "Only select repositories" is a UI choice made in the
        # steps (behaviour 14), not a pre-fill parameter.
        build = self._get_build_recipe_url()
        repo = "my-repo"

        url = build("octodemo", repo)

        query = self._query(url)
        self.assertNotIn(
            "repository",
            query,
            "no 'repository' query parameter is documented for fine-grained "
            "token creation",
        )
        self.assertNotIn(
            "repo",
            query,
            "no 'repo' query parameter is documented for fine-grained token "
            "creation",
        )
        self.assertNotIn(
            repo,
            [value for values in query.values() for value in values],
            "the repo name must not appear as any parameter's value; it "
            "belongs in the recipe steps (behaviour 14), not the URL",
        )

    def test_build_recipe_url_is_a_function_of_the_owner_only(self):
        build = self._get_build_recipe_url()

        self.assertEqual(
            build("octodemo", "repo-a"),
            build("octodemo", "repo-b"),
            "the repo name is not a URL parameter, so two repos of the same "
            "owner must yield identical URLs",
        )

    def test_build_recipe_url_empty_owner_raises_token_recipe_error(self):
        build = self._get_build_recipe_url()
        token_recipe_error = self._get_token_recipe_error()

        with self.assertRaises(token_recipe_error):
            build("", "my-repo")

    def test_build_recipe_url_whitespace_owner_raises_token_recipe_error(self):
        build = self._get_build_recipe_url()
        token_recipe_error = self._get_token_recipe_error()

        with self.assertRaises(token_recipe_error):
            build("   ", "my-repo")


class WithholdingsByAbsencePinTests(TokenRecipeTestCase):
    """Behaviour 13: [PIN] the withholdings are visible by absence.

    THIS PIN IS THE SECURITY CLAIM OF HALF 2. The URL grants exactly
    contents/pull_requests/issues=write and actions=read, and the withheld
    permissions (administration, workflows, metadata) must be absent from
    the query entirely - a later convenience edit that adds
    ``administration=read`` (or ``workflows=...`` or ``metadata=...``) must
    break this pin.
    """

    def test_withheld_permissions_are_absent_at_any_value_for_every_owner(self):
        build = self._get_build_recipe_url()

        for owner in OWNERS:
            query = self._query(build(owner, "my-repo"))
            for withheld in WITHHELD:
                self.assertNotIn(
                    withheld,
                    query,
                    "{!r} must be absent from the query at ANY value for "
                    "owner {!r} - the withholding is proven by absence, and "
                    "adding it back breaks half 2's security claim".format(
                        withheld, owner
                    ),
                )

    def test_the_four_granted_permissions_are_present_so_the_pin_is_not_vacuous(self):
        build = self._get_build_recipe_url()

        for owner in OWNERS:
            query = self._query(build(owner, "my-repo"))
            for permission in GRANTED:
                self.assertIsNotNone(
                    query.get(permission),
                    "{} must still be granted for owner {!r}; without the "
                    "four grants the absence pin would be vacuously true".format(
                        permission, owner
                    ),
                )
            self.assertEqual(
                query.get("target_name"),
                [owner],
                "target_name must still be the owner for {!r}".format(owner),
            )

    def test_the_granted_set_is_exactly_the_four_permissions_plus_target_name(self):
        # The strongest form of the pin: the set of query keys is exactly
        # {target_name, contents, pull_requests, issues, actions}. This
        # breaks if anyone adds administration=read (the pin's stated
        # purpose) OR drops a granted permission.
        build = self._get_build_recipe_url()
        expected_keys = {"target_name"} | set(GRANTED)

        for owner in OWNERS:
            query = self._query(build(owner, "my-repo"))
            self.assertEqual(
                set(query),
                expected_keys,
                "the query must carry exactly {!r} for owner {!r} - "
                "anything more (a withheld permission slipping back in) or "
                "anything less (a grant dropped) breaks the pin".format(
                    sorted(expected_keys), owner
                ),
            )
