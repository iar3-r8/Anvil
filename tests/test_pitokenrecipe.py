"""Tests for anvilkit.pi.pitokenrecipe - the pre-filled fine-grained token
creation recipe (behaviours 12-14 of plans/verify-guards-token.md).

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
pure string builder and ``recipe_steps`` is a pure display-text builder;
the observable surface of each is exactly what it returns.
"""

import importlib
import importlib.util
import re
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

# Word-boundary matchers for the grant levels, so "writer" or "writeup"
# cannot satisfy a permission assertion (behaviour 14's permission steps).
_READ = re.compile(r"\bread\b", re.IGNORECASE)
_WRITE = re.compile(r"\bwrite\b", re.IGNORECASE)


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


class RecipeStepsTests(TokenRecipeTestCase):
    """Behaviour 14: ``recipe_steps(owner, repo, url)`` -> the creation steps.

    The steps are display text for a human following the saved page's
    "Creating a fine-grained personal access token" sequence
    (``doc/external/github/fine-grained-personal-access-tokens.md``): the
    target (the owner) is named, "Only select repositories" is chosen and
    the repo is named there - the repo is not a URL parameter (behaviour
    12), so the steps are the only place it appears - and the plan's three
    recorded caveats are stated. The assertions pin substance and order,
    not the full string of every step.
    """

    def _get_recipe_steps(self):
        """Fetch ``anvilkit.pi.pitokenrecipe.recipe_steps``, failing clearly if absent."""
        pitokenrecipe = self._pitokenrecipe()
        steps = getattr(pitokenrecipe, "recipe_steps", None)
        self.assertTrue(
            callable(steps),
            "anvilkit.pi.pitokenrecipe.recipe_steps is not callable; "
            "behaviour 14 has not been implemented yet",
        )
        return steps

    def _steps(self, owner="octodemo", repo="my-repo"):
        """The recipe steps for ``owner``/``repo``, with the matching recipe URL."""
        steps = self._get_recipe_steps()
        url = self._get_build_recipe_url()(owner, repo)
        return steps(owner, repo, url)

    @staticmethod
    def _first_index(steps, needle):
        """The index of the first step containing ``needle`` (case-insensitive)."""
        wanted = needle.lower()
        for index, step in enumerate(steps):
            if wanted in step.lower():
                return index
        raise AssertionError(
            "no step mentions {!r}; steps: {!r}".format(needle, steps)
        )

    def test_recipe_steps_returns_a_non_empty_list_of_strings(self):
        steps = self._steps()

        self.assertIsInstance(steps, list, "recipe_steps must return a list")
        self.assertTrue(
            steps,
            "the recipe must have at least one step",
        )
        for step in steps:
            self.assertIsInstance(step, str, "each step must be a str")

    def test_recipe_steps_name_the_target_and_the_repo_under_only_select_repositories(self):
        # The plan: "the documented creation sequence with 'Only select
        # repositories' and the target named"; the repo is not a URL
        # parameter (behaviour 12), so the steps are the only place it is
        # named.
        steps = self._steps()

        self._first_index(steps, "octodemo")
        self._first_index(steps, "Only select repositories")
        self._first_index(steps, "my-repo")

    def test_recipe_steps_follow_the_saved_pages_creation_sequence_in_order(self):
        steps = self._steps()

        # The saved page's numbered sequence: Resource owner (9), Repository
        # access "Only select repositories" (11), the selected repository
        # (12), then the permission grants (13).
        order = (
            self._first_index(steps, "octodemo"),
            self._first_index(steps, "Only select repositories"),
            self._first_index(steps, "my-repo"),
            self._first_index(steps, "Contents"),
            self._first_index(steps, "Pull requests"),
            self._first_index(steps, "Issues"),
            self._first_index(steps, "Actions"),
        )
        self.assertEqual(
            order,
            tuple(sorted(order)),
            "the steps must follow the saved page's creation sequence - "
            "target owner, then repository access, then the permission "
            "grants - got order {!r} for steps: {!r}".format(order, steps),
        )

    def test_recipe_steps_grant_read_and_write_for_contents_pull_requests_and_issues(self):
        steps = self._steps()

        for name in ("Contents", "Pull requests", "Issues"):
            step = steps[self._first_index(steps, name)]
            self.assertTrue(
                _READ.search(step) and _WRITE.search(step),
                "the {} step must grant both read and write; got: {}".format(
                    name, step
                ),
            )

    def test_recipe_steps_grant_actions_read_only_and_never_write(self):
        steps = self._steps()

        step = steps[self._first_index(steps, "Actions")]
        self.assertTrue(
            _READ.search(step),
            "the Actions step must grant read (the loop inspects its own "
            "CI); got: " + step,
        )
        self.assertIsNone(
            _WRITE.search(step),
            "the Actions step must not grant write - the CI edit path stays "
            "closed behind the workflows withholding; got: " + step,
        )

    def test_recipe_steps_carry_the_three_recorded_caveats(self):
        # The plan's three recorded caveats, each traced to the saved page.
        # The same-step pairing keeps the pin from passing on two unrelated
        # steps that happen to share one word.
        steps = self._steps()
        lowered = [step.lower() for step in steps]

        self.assertTrue(
            any("checks api" in step and "actions" in step for step in lowered),
            "a step must record that a fine-grained PAT cannot call the "
            "Checks API, so CI is read as Actions runs and jobs; steps: "
            + repr(steps),
        )
        self.assertTrue(
            any("public" in step and "read" in step for step in lowered),
            "a step must record that every fine-grained token keeps "
            "read-only access to all public repositories; steps: " + repr(steps),
        )
        self.assertTrue(
            any("driver" in step and "container" in step for step in lowered),
            "a step must record that the token lives on the host driver "
            "outside the container, so the agent cannot read it; steps: "
            + repr(steps),
        )

    def test_recipe_steps_interpolate_the_owner_and_repo_verbatim(self):
        owner, repo = "another owner", "other-repo"

        steps = self._steps(owner, repo)

        # The steps are display text, not a URL: the space in the owner is
        # no encoding concern and must appear verbatim.
        self.assertTrue(
            any(owner in step for step in steps),
            "the owner {!r} must appear verbatim in the steps; steps: "
            + repr(steps),
        )
        self.assertTrue(
            any(repo in step for step in steps),
            "the repo {!r} must appear verbatim in the steps; steps: "
            + repr(steps),
        )

    def test_recipe_steps_are_pure_and_deterministic(self):
        steps = self._get_recipe_steps()
        url = self._get_build_recipe_url()("octodemo", "my-repo")

        first = steps("octodemo", "my-repo", url)
        second = steps("octodemo", "my-repo", url)

        self.assertEqual(
            first,
            second,
            "two calls with the same inputs must return equal lists; "
            "recipe_steps is a pure display-text builder with no hidden "
            "state",
        )
