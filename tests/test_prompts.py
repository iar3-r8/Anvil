"""Tests for anvilkit.prompts - interactive input that is always bypassable.

Written before the implementation (TDD step 8).

Replaces the ``read -p`` prompts at ``anvil:34-61``, ``anvil:134``,
``anvil:163-180`` and ``anvil:345``.

``prompts.py`` deliberately owns **only** the bypass logic - "is this value
already known, and may I prompt at all?". The mechanics of asking (re-prompting
on invalid input, choice validation, integer ranges, hidden entry, y/n parsing)
are delegated to ``click``, which already solves them. What is tested here is
therefore our decision logic and the behaviour we promise, not click's internals.

**Why stdin is faked with ``io.StringIO`` rather than ``CliRunner.isolation``:**
click's test harness replaces input with a function that calls
``readline().rstrip()``, which returns ``''`` endlessly once the buffer is
exhausted. A prompt with no default therefore loops forever under
``CliRunner.isolation`` while behaving correctly in production, where ``input()``
raises ``EOFError``. An earlier version of this file used ``isolation`` and hung -
so it simulated a condition that cannot occur. ``StringIO`` reproduces genuine
EOF, which is what a CI runner with closed stdin actually presents.

No test can block: every stdin is finite, and exhausting it raises.

One intentional divergence from bash, asserted below: ``anvil:165`` matched
``^[Yy](es)?$``, so a typo like ``ya`` silently meant "no" and quietly skipped a
feature the user was trying to enable. ``click.confirm`` re-prompts instead.
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anvilkit import prompts  # noqa: E402

ANTHROPIC_MODELS = [
    {"id": "claude-fable-5", "label": "smartest - most expensive"},
    {"id": "claude-opus-5", "label": "balanced"},
    {"id": "claude-sonnet-5", "label": "fast"},
    {"id": "claude-haiku-4-5", "label": "very fast"},
]


class PromptCase(unittest.TestCase):
    """Base class providing stdin injection and output capture."""

    def call(self, func, *args, stdin="", **kwargs):
        """Run ``func`` with ``stdin`` as input, returning (result, output).

        ``stdin`` is a finite StringIO, so an unanswered prompt hits real EOF
        instead of hanging.
        """
        captured = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)):
            with contextlib.redirect_stdout(captured):
                result = func(*args, **kwargs)
        return result, captured.getvalue()

    def call_expecting_no_input(self, func, *args, **kwargs):
        """Run ``func`` with both input seams booby-trapped.

        Proves a bypassed prompt reads nothing at all, rather than merely
        happening to return the right value.
        """
        boom = AssertionError("must not prompt when the value is already known")
        with mock.patch.object(prompts, "_read_line", side_effect=boom):
            with mock.patch.object(
                prompts, "_read_confirmation", side_effect=boom
            ):
                return func(*args, **kwargs)


class AskTests(PromptCase):
    """The primitive text prompt."""

    def test_returns_the_typed_value(self):
        value, _ = self.call(prompts.ask, "Value", default="d", stdin="typed\n")
        self.assertEqual(value, "typed")

    def test_empty_answer_takes_the_default(self):
        value, _ = self.call(prompts.ask, "Value", default="d", stdin="\n")
        self.assertEqual(value, "d")

    def test_prompt_shows_the_default(self):
        _, output = self.call(prompts.ask, "Enter port", default="8000", stdin="\n")
        self.assertIn("8000", output)
        self.assertIn("Enter port", output)

    def test_supplied_value_bypasses_the_prompt_entirely(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask, "Value", default="d", supplied="flagged"
            ),
            "flagged",
        )

    def test_assume_yes_takes_the_default_without_prompting(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask, "Value", default="d", assume_yes=True
            ),
            "d",
        )

    def test_supplied_value_wins_over_assume_yes(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask,
                "Value",
                default="d",
                supplied="flag",
                assume_yes=True,
            ),
            "flag",
        )

    def test_unset_flag_still_prompts(self):
        """An unset flag arrives as None, which must not count as supplied."""
        value, _ = self.call(
            prompts.ask, "Value", default="d", supplied=None, stdin="typed\n"
        )
        self.assertEqual(value, "typed")

    def test_eof_falls_back_to_the_default(self):
        """Closed stdin, as in CI: the default is still a valid answer."""
        value, _ = self.call(prompts.ask, "Value", default="d", stdin="")
        self.assertEqual(value, "d")


def _getpass_from_stdin(prompt=""):
    """Stand in for getpass.getpass, reading the patched sys.stdin.

    getpass ignores sys.stdin and opens /dev/tty, so under a real terminal the
    suite blocks on the keyboard. Reading sys.stdin keeps the hidden-input path
    on the same finite StringIO as every other prompt test.

    Raising EOFError on exhaustion reproduces genuine EOF: click catches it at
    termui.py:141 and raises Abort, which ask_required maps to PromptError. A
    fake returning '' instead would spin click's re-prompt loop forever - the
    exact trap the module docstring above describes.
    """
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.rstrip("\n")


class AskRequiredTests(PromptCase):
    """Values that may not be empty - the API-key loop at anvil:179."""

    def call_hidden(self, *args, stdin="", **kwargs):
        """Run ask_required(hide_input=True), capturing stdout and stderr.

        stderr is captured and asserted empty because the defect this
        guards against announced itself there: getpass.fallback_getpass
        does a raw print to sys.stderr (getpass.py:125) that
        warnings.catch_warnings() cannot suppress.
        """
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            with mock.patch("getpass.getpass", _getpass_from_stdin):
                result, output = self.call(
                    prompts.ask_required,
                    *args,
                    hide_input=True,
                    stdin=stdin,
                    **kwargs,
                )
        return result, output, errors.getvalue()

    def test_reprompts_until_a_value_is_given(self):
        value, _ = self.call(prompts.ask_required, "Key", stdin="\n\nsecret\n")
        self.assertEqual(value, "secret")

    def test_supplied_value_bypasses_the_loop(self):
        self.assertEqual(
            self.call_expecting_no_input(prompts.ask_required, "Key", supplied="k"),
            "k",
        )

    def test_assume_yes_without_a_supplied_value_raises(self):
        """--yes cannot invent a secret, so it must fail loudly, not silently."""
        with self.assertRaises(prompts.PromptError):
            self.call_expecting_no_input(
                prompts.ask_required, "Key", assume_yes=True
            )

    def test_eof_raises_prompt_error_rather_than_looping(self):
        with self.assertRaises(prompts.PromptError):
            self.call(prompts.ask_required, "Key", stdin="")

    def test_prompt_error_names_the_value(self):
        with self.assertRaises(prompts.PromptError) as ctx:
            self.call(prompts.ask_required, "Anthropic API Key", stdin="")

        self.assertIn("Anthropic API Key", str(ctx.exception))

    def test_hidden_input_returns_the_typed_value(self):
        value, _output, _errors = self.call_hidden("Key", stdin="s3cret\n")
        self.assertEqual(value, "s3cret")

    def test_hidden_input_does_not_echo_the_secret(self):
        """The prompt is shown but the secret is never written to stdout.

        Caveat (assumption A1, plan §6): with getpass.getpass faked, this
        proves click does not echo the value back through its prompt-building
        or error paths - not terminal echo suppression, which is a termios
        property only testable against a real PTY.
        """
        _value, output, _errors = self.call_hidden("Key", stdin="s3cret\n")
        self.assertIn("Key", output)
        self.assertNotIn("s3cret", output)

    def test_hidden_input_leaks_nothing_to_stderr(self):
        """The primary RED assertion: captured stderr is exactly empty.

        getpass.fallback_getpass does a raw print to sys.stderr
        (getpass.py:125) that warnings.catch_warnings() cannot suppress, so
        this assertion fails until getpass.getpass is faked in the GREEN step.
        """
        _value, _output, errors = self.call_hidden("Key", stdin="s3cret\n")
        self.assertEqual(errors, "")

    def test_hidden_input_eof_raises_prompt_error_naming_the_key(self):
        """Exhausted stdin raises PromptError promptly, without looping."""
        with self.assertRaises(prompts.PromptError) as ctx:
            self.call_hidden("Key", stdin="")
        self.assertIn("Key", str(ctx.exception))

    def test_hidden_input_empty_line_reprompts(self):
        """A blank answer re-prompts; the value is taken on the next line."""
        value, output, errors = self.call_hidden("Key", stdin="\ns3cret\n")
        self.assertEqual(value, "s3cret")
        self.assertEqual(output.count("Key"), 2)
        self.assertEqual(errors, "")


class ConfirmTests(PromptCase):
    """The (y/N) prompts."""

    def test_y_is_true(self):
        value, _ = self.call(prompts.confirm, "Use it?", stdin="y\n")
        self.assertTrue(value)

    def test_yes_is_true(self):
        value, _ = self.call(prompts.confirm, "Use it?", stdin="yes\n")
        self.assertTrue(value)

    def test_uppercase_is_true(self):
        value, _ = self.call(prompts.confirm, "Use it?", stdin="Y\n")
        self.assertTrue(value)

    def test_n_is_false(self):
        value, _ = self.call(prompts.confirm, "Use it?", stdin="n\n")
        self.assertFalse(value)

    def test_empty_answer_defaults_to_false(self):
        value, _ = self.call(prompts.confirm, "Use it?", stdin="\n")
        self.assertFalse(value)

    def test_default_true_accepts_an_empty_answer(self):
        value, _ = self.call(prompts.confirm, "Use it?", default=True, stdin="\n")
        self.assertTrue(value)

    def test_unrecognised_answer_reprompts_rather_than_silently_declining(self):
        """Documented divergence from anvil:165.

        The bash regex '^[Yy](es)?$' made 'ya' mean "no", silently skipping a
        feature the user was clearly trying to enable. Re-prompting is a fix.
        """
        value, output = self.call(prompts.confirm, "Use it?", stdin="ya\ny\n")
        self.assertTrue(value)
        self.assertEqual(output.count("Use it?"), 2)

    def test_supplied_true_bypasses_the_prompt(self):
        self.assertTrue(
            self.call_expecting_no_input(prompts.confirm, "Use it?", supplied=True)
        )

    def test_supplied_false_bypasses_the_prompt(self):
        self.assertFalse(
            self.call_expecting_no_input(prompts.confirm, "Use it?", supplied=False)
        )

    def test_assume_yes_takes_the_default_not_a_blanket_true(self):
        """--yes means "accept defaults", so a (y/N) question still answers no."""
        self.assertFalse(
            self.call_expecting_no_input(
                prompts.confirm, "Use it?", assume_yes=True
            )
        )
        self.assertTrue(
            self.call_expecting_no_input(
                prompts.confirm, "Use it?", default=True, assume_yes=True
            )
        )

    def test_eof_takes_the_default(self):
        value, _ = self.call(prompts.confirm, "Use it?", stdin="")
        self.assertFalse(value)


class AskPortTests(PromptCase):
    """Port entry, which the bash version never validated."""

    def test_returns_the_typed_port(self):
        value, _ = self.call(prompts.ask_port, "Port", default=8000, stdin="9999\n")
        self.assertEqual(value, 9999)

    def test_result_is_an_integer(self):
        value, _ = self.call(prompts.ask_port, "Port", default=8000, stdin="9999\n")
        self.assertIsInstance(value, int)

    def test_empty_answer_takes_the_default(self):
        value, _ = self.call(prompts.ask_port, "Port", default=8000, stdin="\n")
        self.assertEqual(value, 8000)

    def test_out_of_range_port_reprompts(self):
        """'LLM_PORT=99999' would have been accepted by bash and failed later."""
        value, output = self.call(
            prompts.ask_port, "Port", default=8000, stdin="99999\n8080\n"
        )
        self.assertEqual(value, 8080)
        self.assertEqual(output.count("Port"), 2)

    def test_non_numeric_port_reprompts(self):
        value, _ = self.call(
            prompts.ask_port, "Port", default=8000, stdin="abc\n8080\n"
        )
        self.assertEqual(value, 8080)

    def test_supplied_port_bypasses_the_prompt(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask_port, "Port", default=8000, supplied=7777
            ),
            7777,
        )

    def test_assume_yes_takes_the_default(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask_port, "Port", default=8000, assume_yes=True
            ),
            8000,
        )

    def test_eof_takes_the_default(self):
        value, _ = self.call(prompts.ask_port, "Port", default=8000, stdin="")
        self.assertEqual(value, 8000)


class ChooseTests(PromptCase):
    """The Anthropic model menu from anvil:121, now driven by anvil.yaml data."""

    def _choose(self, stdin, **kwargs):
        params = dict(
            prompt="Select model",
            options=ANTHROPIC_MODELS,
            default="claude-opus-5",
        )
        params.update(kwargs)
        return self.call(prompts.choose, stdin=stdin, **params)

    def test_selecting_the_first_option(self):
        value, _ = self._choose("1\n")
        self.assertEqual(value, "claude-fable-5")

    def test_selecting_a_middle_option(self):
        value, _ = self._choose("3\n")
        self.assertEqual(value, "claude-sonnet-5")

    def test_selecting_the_last_listed_option(self):
        value, _ = self._choose("4\n")
        self.assertEqual(value, "claude-haiku-4-5")

    def test_empty_answer_takes_the_default(self):
        value, _ = self._choose("\n")
        self.assertEqual(value, "claude-opus-5")

    def test_custom_entry_is_the_final_menu_item(self):
        value, _ = self._choose("5\nvendor/my-model\n")
        self.assertEqual(value, "vendor/my-model")

    def test_empty_custom_entry_reprompts(self):
        value, _ = self._choose("5\n\nvendor/my-model\n")
        self.assertEqual(value, "vendor/my-model")

    def test_out_of_range_selection_reprompts(self):
        value, _ = self._choose("9\n2\n")
        self.assertEqual(value, "claude-opus-5")

    def test_non_numeric_selection_reprompts(self):
        value, _ = self._choose("abc\n2\n")
        self.assertEqual(value, "claude-opus-5")

    def test_menu_lists_every_option_with_its_label(self):
        _, output = self._choose("\n")
        for option in ANTHROPIC_MODELS:
            self.assertIn(option["id"], output)
            self.assertIn(option["label"], output)

    def test_menu_offers_a_custom_entry(self):
        _, output = self._choose("\n")
        self.assertIn("Custom", output)

    def test_supplied_id_bypasses_the_menu(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.choose,
                prompt="Select model",
                options=ANTHROPIC_MODELS,
                default="claude-opus-5",
                supplied="claude-sonnet-5",
            ),
            "claude-sonnet-5",
        )

    def test_supplied_id_need_not_appear_in_the_menu(self):
        """--anthropic-model accepts any id, exactly as menu item 5 did."""
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.choose,
                prompt="Select model",
                options=ANTHROPIC_MODELS,
                default="claude-opus-5",
                supplied="vendor/unlisted",
            ),
            "vendor/unlisted",
        )

    def test_assume_yes_takes_the_default(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.choose,
                prompt="Select model",
                options=ANTHROPIC_MODELS,
                default="claude-opus-5",
                assume_yes=True,
            ),
            "claude-opus-5",
        )

    def test_empty_option_list_is_rejected(self):
        with self.assertRaises(prompts.PromptError):
            self.call_expecting_no_input(
                prompts.choose, prompt="Select", options=[], default="x"
            )

    def test_options_missing_an_id_are_rejected(self):
        with self.assertRaises(prompts.PromptError):
            self.call_expecting_no_input(
                prompts.choose,
                prompt="Select",
                options=[{"label": "no id here"}],
                default="x",
            )

    def test_eof_takes_the_default(self):
        value, _ = self._choose("")
        self.assertEqual(value, "claude-opus-5")


class NonInteractiveGuardTests(PromptCase):
    """interactive=False forbids prompting outright, for CI."""

    def test_ask_uses_the_default_when_not_interactive(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask, "Value", default="d", interactive=False
            ),
            "d",
        )

    def test_confirm_uses_the_default_when_not_interactive(self):
        self.assertFalse(
            self.call_expecting_no_input(
                prompts.confirm, "Use it?", interactive=False
            )
        )

    def test_ask_port_uses_the_default_when_not_interactive(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask_port, "Port", default=8000, interactive=False
            ),
            8000,
        )

    def test_choose_uses_the_default_when_not_interactive(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.choose,
                prompt="Select",
                options=ANTHROPIC_MODELS,
                default="claude-opus-5",
                interactive=False,
            ),
            "claude-opus-5",
        )

    def test_ask_required_raises_when_not_interactive_and_unsupplied(self):
        with self.assertRaises(prompts.PromptError):
            self.call_expecting_no_input(
                prompts.ask_required, "Key", interactive=False
            )

    def test_supplied_values_still_work_when_not_interactive(self):
        self.assertEqual(
            self.call_expecting_no_input(
                prompts.ask_required, "Key", supplied="k", interactive=False
            ),
            "k",
        )


if __name__ == "__main__":
    unittest.main()
