"""Tests for the provisioned ``brainstorm-feature.md`` template command.

This module is the home for every behaviour of
``plans/brainstorm-feature-command.md`` that is verified against the
*content* of
``templates/roo_template/commands/brainstorm-feature.md``. It reuses the
frontmatter loader and path constants from
``tests/test_template_commands.py`` rather than redefining them (plan
§Assumptions): every assertion is on the parsed frontmatter structure, never
on raw bytes, so the green step has latitude in the prose.
"""

import unittest

from tests.test_template_commands import (
    COMMANDS_DIR,
    REPO_ROOT,
    load_template_command,
)

#: Behaviour 1 target (plan §Behaviors 1): the new Architect-mode command
#: file, which does not exist yet — creating it is the green step.
BRAINSTORM_COMMAND_PATH = COMMANDS_DIR / "brainstorm-feature.md"


class BrainstormCommandTestCase(unittest.TestCase):
    """Shared loading for the brainstorm-feature command file.

    ``setUp`` asserts the file exists as a regular file and parses it once,
    so every test asserts on the parsed frontmatter and body, and a missing
    or malformed document surfaces at load time naming the path. Later
    behaviours subclass this pointed at the same file and assert on
    ``self.body``.
    """

    command_path = BRAINSTORM_COMMAND_PATH

    def setUp(self):
        self.assertTrue(
            self.command_path.is_file(),
            "command file does not exist or is not a regular file: %s"
            % self.command_path,
        )
        self.frontmatter, self.body = load_template_command(self.command_path)


# --------------------------------------------------------------------------- #
# Behaviour 1 — the command file exists with valid frontmatter
# --------------------------------------------------------------------------- #


class B1FrontmatterTests(BrainstormCommandTestCase):
    """Behaviour 1 (plans/brainstorm-feature-command.md): the command file
    exists with valid frontmatter.

    Expected red reason: ``templates/roo_template/commands/brainstorm-feature.md``
    does not exist yet, so every test fails in ``setUp`` with the
    file-not-found assertion. That is the intended failure mode — the green
    step creates the file, nothing else.
    """

    def test_command_file_is_a_regular_file(self):
        # B1 output: the path is a file, not a directory or a missing path.
        # setUp already asserted this; the explicit test keeps the
        # requirement named in the suite.
        self.assertTrue(
            self.command_path.is_file(),
            "command file does not exist or is not a regular file: %s"
            % self.command_path,
        )

    def test_frontmatter_is_a_mapping(self):
        # B1: the parsed frontmatter is a YAML mapping, not a scalar or a
        # list. The loader would have raised for anything else.
        self.assertIsInstance(
            self.frontmatter,
            dict,
            "frontmatter of %s is not a mapping" % self.command_path,
        )

    def test_frontmatter_has_non_empty_description(self):
        # B1: frontmatter carries a non-empty ``description`` string.
        description = self.frontmatter.get("description")
        self.assertIsInstance(
            description,
            str,
            "frontmatter of %s has no 'description' string" % self.command_path,
        )
        self.assertTrue(
            description.strip(),
            "frontmatter 'description' of %s is empty" % self.command_path,
        )

    def test_frontmatter_mode_is_architect(self):
        # B1: the command runs in Architect mode (the plan's three-phase
        # brainstorming is a planning, not an implementation, session).
        self.assertEqual(
            self.frontmatter.get("mode"),
            "Architect",
            "frontmatter 'mode' of %s is not 'Architect'" % self.command_path,
        )


# --------------------------------------------------------------------------- #
# Behaviour 2 — Phase 1: context then the grill
# --------------------------------------------------------------------------- #


class B2Phase1Tests(BrainstormCommandTestCase):
    """Behaviour 2 (plans/brainstorm-feature-command.md): Phase 1 of the
    brainstorming session — gather context and requirements on launch, then
    grill with exactly one question at a time.

    Expected red reason: the body of
    ``templates/roo_template/commands/brainstorm-feature.md`` is a
    one-line placeholder, so the phrase assertions below fail. The file
    exists and parses (behaviour 1 is green), so this is assertion-level
    red, not a load failure.
    """

    def test_body_directs_context_gathering_before_the_grill(self):
        # B2 assertion 1: gather early context and requirements on launch,
        # THEN dig into them — two-step order, context gathering is not
        # optional and precedes the grill.
        self.assertRegex(
            self.body,
            r"(?i)gather[^.\n]*context",
            "body of %s does not direct gathering early context and "
            "requirements on launch" % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)then (dig|drill)",
            "body of %s does not direct digging into the gathered context "
            "and requirements after the gathering step"
            % self.command_path,
        )

    def test_body_forbids_batched_questions(self):
        # B2 assertion 2: exactly ONE question at a time; a rule forbidding
        # multiple or batched questions in one message.
        self.assertRegex(
            self.body,
            r"(?i)exactly one (question|at a time)|one question at a time",
            "body of %s does not state exactly one question at a time"
            % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)(never|don'?t|do not)[^.\n]*(batch|multiple|several)",
            "body of %s does not forbid multiple or batched questions in "
            "one message" % self.command_path,
        )

    def test_body_requires_short_replies_and_waiting_for_the_answer(self):
        # B2 assertion 3: reply briefly and stop, waiting for the user's
        # answer before the next question.
        self.assertRegex(
            self.body,
            r"(?i)(short|brief) (repl(y|ies)|response|responses|answer|answers)",
            "body of %s does not require short responses" % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)wait[^.\n]*answer",
            "body of %s does not require waiting for the user's answer "
            "before the next question" % self.command_path,
        )

    def test_body_requires_at_least_3_4_iterations(self):
        # B2 assertion 4: at least 3-4 iterations before moving on.
        self.assertRegex(
            self.body,
            r"(?i)(3|three)(\s*[-–]\s*4|\s+to\s+4)(\s+(iterations|rounds|passes))?",
            "body of %s does not require at least 3-4 iterations"
            % self.command_path,
        )

    def test_body_names_all_four_grill_focus_areas(self):
        # B2 assertion 5: the grill's focus areas, all four named — hidden
        # edge cases, single points of failure, scale boundaries /
        # performance trade-offs, data life-cycles (and mutation safety).
        self.assertRegex(
            self.body,
            r"(?i)edge case",
            "body of %s does not name hidden edge cases as a grill focus"
            % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)single point of failure",
            "body of %s does not name single points of failure as a grill "
            "focus" % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)scale (boundar|limit)|performance",
            "body of %s does not name scale boundaries or performance "
            "trade-offs as a grill focus" % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)data (life-?cycle|life cycle|lifecycles?|lifecycle)|mutation",
            "body of %s does not name data life-cycles (and mutation "
            "safety) as a grill focus" % self.command_path,
        )

    def test_body_forbids_implementation_code_during_the_session(self):
        # B2 assertion 6: no implementation code during the session — an
        # explicit prohibition on writing implementation code, boilerplate
        # or complete files while brainstorming.
        self.assertRegex(
            self.body,
            r"(?i)(never|do not|no) [^.\n]*implementation code",
            "body of %s does not explicitly forbid writing "
            "implementation code during the session" % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)boilerplate",
            "body of %s does not forbid boilerplate during the session"
            % self.command_path,
        )


# --------------------------------------------------------------------------- #
# Behaviour 3 — the standing plain-language rule
# --------------------------------------------------------------------------- #


class B3PlainLanguageTests(BrainstormCommandTestCase):
    """Behaviour 3 (plans/brainstorm-feature-command.md): the standing
    plain-language rule — the specifications and behaviours this command
    produces are written in clear, simple, plain language that a
    non-specialist reader can follow.

    Expected red reason: the body of
    ``templates/roo_template/commands/brainstorm-feature.md`` mentions
    "plain language" only incidentally (the intro line and the
    one-question rule); it states no standing rule tying plain language
    to the spec's content and naming a non-specialist audience, so the
    three phrase assertions below fail. The file exists and parses
    (behaviours 1-2 are green), so this is assertion-level red, not a
    load failure.
    """

    def test_body_states_plain_language_requirement_for_the_spec(self):
        # B3 assertion 1: the plain-language requirement is named
        # explicitly — "plain language" or "simple language" in the same
        # sentence as the spec/behaviours it governs, i.e. tied to how
        # the deliverable is written or presented, not an incidental
        # phrase about the session's chat style.
        self.assertRegex(
            self.body,
            r"(?i)\b(specifications?|behaviou?rs?|spec)\b[^.\n]{0,100}(plain|simple) language"
            r"|(plain|simple) language[^.\n]{0,100}\b(specifications?|behaviou?rs?|spec)\b",
            "body of %s does not state a plain-language requirement tied "
            "to how the spec or behaviours are written" % self.command_path,
        )

    def test_body_names_a_non_specialist_reader_as_the_audience(self):
        # B3 assertion 2: the audience of the plain-language rule is named
        # explicitly — a non-specialist reader, or an equivalent no-jargon
        # phrasing that makes the reader, not just the writer, visible.
        self.assertRegex(
            self.body,
            r"(?i)non[- ]specialist|non[- ]expert|without jargon|avoid[s]? (the )?jargon",
            "body of %s does not name a non-specialist reader (or an "
            "equivalent no-jargon audience) for the plain-language rule"
            % self.command_path,
        )

    def test_plain_language_rule_covers_specifications_and_behaviours(self):
        # B3 assertion 3: the rule's scope is the spec's content —
        # "specifications" and/or "behaviours", the deliverable's own
        # words, are the things that must be written plainly (not only
        # the chat replies), in either word order within one sentence.
        self.assertRegex(
            self.body,
            r"(?i)\b(specifications?|behaviou?rs?)\b[^.\n]{0,120}(plain|simple|simply)"
            r"|(plain|simple|simply)[^.\n]{0,120}\b(specifications?|behaviou?rs?)\b",
            "body of %s does not make specifications and behaviours the "
            "content that must be written in plain language"
            % self.command_path,
        )


# --------------------------------------------------------------------------- #
# Behaviour 4 — Phase 2: the report
# --------------------------------------------------------------------------- #


class B4Phase2ReportTests(BrainstormCommandTestCase):
    """Behaviour 4 (plans/brainstorm-feature-command.md): Phase 2 of the
    brainstorming session — compile the collective discoveries into a
    report at ``plans/specs/<feature-slug>.md``, updating that file when
    it already exists, with all four named sections: System Architecture
    Overview, Data Models & State, Edge Cases & Error Handling, Testing
    & Success Criteria.

    Expected red reason: the body of
    ``templates/roo_template/commands/brainstorm-feature.md`` carries the
    Phase 1 protocol and the plain-language rule but no Phase 2 report
    section, so the phrase assertions below fail. The file exists and
    parses (behaviours 1-3 are green), so this is assertion-level red,
    not a load failure.
    """

    def test_body_names_the_report_path(self):
        # B4 assertion 1: the report lands under ``plans/specs/`` as a
        # ``<feature-slug>.md`` file — the directory is named, and the
        # slug placeholder appears in angle brackets or braces (not a
        # bare root ``spec.md``).
        self.assertRegex(
            self.body,
            r"(?i)plans/specs/",
            "body of %s does not name the report directory 'plans/specs/'"
            % self.command_path,
        )
        self.assertRegex(
            self.body,
            r"(?i)[<{]feature-slug[>}]\.md",
            "body of %s does not name the report file shape "
            "'<feature-slug>.md' (slug placeholder in angle brackets or "
            "braces, with the .md extension)"
            % self.command_path,
        )

    def test_body_directs_updating_the_report_when_it_already_exists(self):
        # B4 assertion 2: the report file is updated/reused when it
        # already exists — the update rule, not a create-only rule. One
        # sentence must carry both an update verb and the already-present
        # file, in either order.
        self.assertRegex(
            self.body,
            r"(?i)(updat|revis|append|reus)[^.\n]{0,120}(already (exist|present)|existing)"
            r"|(already (exist|present)|existing)[^.\n]{0,120}(updat|revis|append|reus)",
            "body of %s does not state that the report file is updated "
            "or reused when it already exists (not only created new)"
            % self.command_path,
        )

    def test_body_names_the_system_architecture_overview_section(self):
        # B4 assertion 3: the first report section is named.
        self.assertRegex(
            self.body,
            r"(?i)system architecture overview",
            "body of %s does not name the 'System Architecture Overview' "
            "report section" % self.command_path,
        )

    def test_body_names_the_data_models_section(self):
        # B4 assertion 4: the second report section is named; accept the
        # '&' or 'and' spelling.
        self.assertRegex(
            self.body,
            r"(?i)data model(s)? (&|and) state",
            "body of %s does not name the 'Data Models & State' report "
            "section ('&' or 'and')" % self.command_path,
        )

    def test_body_names_the_edge_cases_section(self):
        # B4 assertion 5: the third report section is named; accept the
        # '&' or 'and' spelling.
        self.assertRegex(
            self.body,
            r"(?i)edge case(s)? (&|and) error handling",
            "body of %s does not name the 'Edge Cases & Error Handling' "
            "report section ('&' or 'and')" % self.command_path,
        )

    def test_body_names_the_testing_and_success_criteria_section(self):
        # B4 assertion 6: the fourth report section is named; accept the
        # '&' or 'and' spelling.
        self.assertRegex(
            self.body,
            r"(?i)testing (&|and) success criteria",
            "body of %s does not name the 'Testing & Success Criteria' "
            "report section ('&' or 'and')" % self.command_path,
        )


if __name__ == "__main__":
    unittest.main()
