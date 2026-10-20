"""Tests for anvilkit.pievents - the JSONL event-stream reader.

Written before the implementation (TDD, ``plans/pi-phase1-bakeoff.md``,
behaviour 8: "JSONL framing"). Behaviours 9-10 (tool accounting,
outcome/usage) land in later cycles as further classes in the same file.

The Pi framing rule (``doc/external/pi-dev/json-event-stream.md``,
"Framing and process I/O"): split records on LF only, strip an optional
preceding carriage return, and treat Unicode line and paragraph
separators (U+2028/U+2029) as ordinary string content, never as record
boundaries.

The production module ``anvilkit.pievents`` does not exist yet, so every
test loads it through ``_pievents``, which fails with a clear assertion
instead of letting a collection-time ImportError mask the reason the
suite is red.

Pinned return shape: ``parse(text: str)`` returns a plain dict with
exactly two keys:

- ``"events"``: ``List[dict]`` - the parsed JSON-object records, in
  stream order;
- ``"malformed_lines"``: ``int`` - how many lines were skipped.

A dict, not a class, because the rest of the bake-off record pipeline
(behaviour 11) is dict-shaped and ``json.dumps``-able, and a plain dict
leaves the coder no room for undocumented fields: several tests assert
the complete dict by value.
"""

import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The literal Unicode line/paragraph separator characters. The raw
# streams below are built with these characters embedded, never with an
# escape sequence, so the framing code under test sees exactly what Pi
# would write.
U2028 = "\u2028"
U2029 = "\u2029"


class PieventsTestCase(unittest.TestCase):
    def _pievents(self):
        """Import anvilkit.pievents, failing clearly if the module is absent."""
        spec = importlib.util.find_spec("anvilkit.pievents")
        self.assertIsNotNone(
            spec,
            "anvilkit.pievents cannot be imported; the JSONL event-stream "
            "reader has not been implemented yet",
        )
        return importlib.import_module("anvilkit.pievents")


class TestReturnShape(PieventsTestCase):
    """The pinned return shape, plus contract 7: empty/whitespace-only
    input yields no events and no malformed lines."""

    def test_parse_returns_dict_with_exactly_two_keys(self):
        pievents = self._pievents()
        parsed = pievents.parse('{"type": "agent_start"}\n')
        self.assertIsInstance(
            parsed,
            dict,
            "parse must return a plain dict, so the bake-off record "
            "(behaviour 11) can embed it and json.dumps it directly",
        )
        self.assertEqual(
            set(parsed),
            {"events", "malformed_lines"},
            "parse must return exactly the keys 'events' and "
            "'malformed_lines': no extra keys, no missing keys",
        )
        self.assertIsInstance(parsed["events"], list)
        self.assertIsInstance(parsed["malformed_lines"], int)

    def test_parse_empty_string_returns_no_events_zero_malformed(self):
        pievents = self._pievents()
        self.assertEqual(pievents.parse(""), {"events": [], "malformed_lines": 0})

    def test_parse_whitespace_only_input_returns_no_events_zero_malformed(self):
        pievents = self._pievents()
        self.assertEqual(
            pievents.parse("   \n\t\n  \n"),
            {"events": [], "malformed_lines": 0},
            "whitespace-only lines are blank lines: skipped silently, "
            "not counted in malformed_lines",
        )


class TestCrlfFraming(PieventsTestCase):
    """Contract 1: a CRLF-joined stream parses to the same events as the
    LF-joined form; the CR is stripped and never part of a field."""

    @staticmethod
    def _records():
        return [
            {"type": "session", "version": 3, "id": "uuid", "cwd": "/path"},
            {"type": "agent_start"},
            {"type": "agent_settled", "aborted": False, "note": "done"},
        ]

    def test_parse_crlf_stream_parses_to_same_events_as_lf_stream(self):
        pievents = self._pievents()
        records = self._records()
        serialized = [json.dumps(record) for record in records]
        lf_stream = "\n".join(serialized) + "\n"
        crlf_stream = "\r\n".join(serialized) + "\r\n"
        self.assertEqual(pievents.parse(lf_stream)["events"], records)
        self.assertEqual(
            pievents.parse(crlf_stream),
            {"events": records, "malformed_lines": 0},
            "CRLF-joined records must parse to the same events as the "
            "LF-joined form, with nothing counted malformed",
        )

    def test_parse_crlf_stream_carriage_return_never_part_of_a_field(self):
        pievents = self._pievents()
        records = self._records()
        serialized = [json.dumps(record) for record in records]
        crlf_stream = "\r\n".join(serialized) + "\r\n"
        events = pievents.parse(crlf_stream)["events"]
        self.assertEqual(events, records)
        for event in events:
            for key, value in event.items():
                if isinstance(value, str):
                    self.assertNotIn(
                        "\r",
                        value,
                        "CR from the CRLF line ending leaked into field "
                        "%r" % key,
                    )

    def test_parse_stream_ending_in_crlf_has_no_phantom_record(self):
        pievents = self._pievents()
        stream = '{"type": "agent_start"}\r\n'
        self.assertEqual(
            pievents.parse(stream),
            {"events": [{"type": "agent_start"}], "malformed_lines": 0},
        )


class TestTrailingLf(PieventsTestCase):
    """Contract 2: a final LF does not produce a phantom empty record."""

    def test_parse_trailing_lf_does_not_produce_phantom_record(self):
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            '{"type": "agent_settled", "aborted": false}\n'
        )
        self.assertEqual(
            pievents.parse(stream),
            {
                "events": [
                    {"type": "agent_start"},
                    {"type": "agent_settled", "aborted": False},
                ],
                "malformed_lines": 0,
            },
        )

    def test_parse_stream_without_trailing_lf_still_returns_last_record(self):
        # "Split records only on LF": splitting "a\nb" on LF yields two
        # records, so a captured stream whose final record is not
        # newline-terminated still yields that record. Only a *truncated*
        # final line is malformed (behaviour 14).
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            '{"type": "agent_settled", "aborted": false}'
        )
        self.assertEqual(
            pievents.parse(stream),
            {
                "events": [
                    {"type": "agent_start"},
                    {"type": "agent_settled", "aborted": False},
                ],
                "malformed_lines": 0,
            },
        )


class TestBlankLines(PieventsTestCase):
    """Contract 3: a blank line in the middle is skipped and is NOT
    counted as malformed - it is not a record at all."""

    def test_parse_blank_line_in_middle_is_skipped_not_counted_malformed(self):
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            "\n"
            '{"type": "agent_settled", "aborted": false}\n'
        )
        self.assertEqual(
            pievents.parse(stream),
            {
                "events": [
                    {"type": "agent_start"},
                    {"type": "agent_settled", "aborted": False},
                ],
                "malformed_lines": 0,
            },
            "an empty line is not a record at all: skipped silently, "
            "never counted in malformed_lines",
        )

    def test_parse_consecutive_blank_lines_are_all_skipped_not_counted_malformed(self):
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            "\n\n\n"
            '{"type": "agent_settled", "aborted": false}\n'
        )
        parsed = pievents.parse(stream)
        self.assertEqual(
            parsed["events"],
            [{"type": "agent_start"}, {"type": "agent_settled", "aborted": False}],
        )
        self.assertEqual(parsed["malformed_lines"], 0)


class TestUnicodeSeparators(PieventsTestCase):
    """Contract 4: U+2028/U+2029 inside a JSON string are NOT record
    boundaries - the record stays one record and the separator survives
    in the parsed field."""

    def test_parse_u2028_inside_string_is_not_a_record_boundary(self):
        pievents = self._pievents()
        record = json.dumps(
            {"type": "message_update", "text": "first" + U2028 + "second"},
            ensure_ascii=False,
        )
        self.assertIn(
            U2028,
            record,
            "sanity: the raw record must carry the literal U+2028, not an escape",
        )
        parsed = pievents.parse(record + "\n")
        self.assertEqual(
            parsed,
            {
                "events": [
                    {"type": "message_update", "text": "first" + U2028 + "second"}
                ],
                "malformed_lines": 0,
            },
            "a U+2028 inside a JSON string must not split the record: a "
            "boundary-splitting parser would yield zero events and two "
            "malformed fragments",
        )

    def test_parse_u2029_inside_string_is_not_a_record_boundary(self):
        pievents = self._pievents()
        record = json.dumps(
            {"type": "message_update", "text": "alpha" + U2029 + "beta"},
            ensure_ascii=False,
        )
        parsed = pievents.parse(record + "\n")
        self.assertEqual(
            parsed["events"],
            [{"type": "message_update", "text": "alpha" + U2029 + "beta"}],
        )
        self.assertEqual(parsed["malformed_lines"], 0)


class TestPlanGivenStream(PieventsTestCase):
    """Behaviour 8's given condition in one stream: CRLF line ends, a
    trailing LF, a blank line, and a JSON string containing U+2028."""

    def test_parse_plan_given_stream_satisfies_all_four_conditions(self):
        pievents = self._pievents()
        lines = [
            json.dumps(
                {"type": "session", "version": 3, "id": "uuid"},
                ensure_ascii=False,
            ),
            "",  # the blank line (CRLF-terminated by the join)
            json.dumps(
                {"type": "message_update", "text": "a" + U2028 + "b"},
                ensure_ascii=False,
            ),
        ]
        stream = "\r\n".join(lines) + "\r\n"
        self.assertEqual(
            pievents.parse(stream),
            {
                "events": [
                    {"type": "session", "version": 3, "id": "uuid"},
                    {"type": "message_update", "text": "a" + U2028 + "b"},
                ],
                "malformed_lines": 0,
            },
        )


class TestMalformedLines(PieventsTestCase):
    """Contracts 5 and 6: a malformed line and a non-object JSON line
    are skipped and counted in ``malformed_lines``; nothing raises; the
    surrounding valid records are still returned."""

    def test_parse_truncated_json_line_is_skipped_and_counted_malformed(self):
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            '{"type": "agen\n'
            '{"type": "agent_settled", "aborted": false}\n'
        )
        parsed = pievents.parse(stream)  # must not raise
        self.assertEqual(
            parsed["events"],
            [{"type": "agent_start"}, {"type": "agent_settled", "aborted": False}],
        )
        self.assertEqual(parsed["malformed_lines"], 1)

    def test_parse_truncated_final_line_keeps_surrounding_records(self):
        # The truncated final line is the realistic host-run case
        # (behaviour 14): the run is still recorded from the valid prefix.
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            '{"type": "agen\n'
        )
        parsed = pievents.parse(stream)
        self.assertEqual(parsed["events"], [{"type": "agent_start"}])
        self.assertEqual(parsed["malformed_lines"], 1)

    def test_parse_multiple_malformed_lines_are_all_counted(self):
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            "no json at all\n"
            '{"type": "agen\n'
            '{"broken"\n'
            '{"type": "agent_settled", "aborted": false}\n'
        )
        parsed = pievents.parse(stream)
        self.assertEqual(
            parsed["events"],
            [{"type": "agent_start"}, {"type": "agent_settled", "aborted": False}],
        )
        self.assertEqual(parsed["malformed_lines"], 3)

    def test_parse_non_object_json_line_is_skipped_and_counted_malformed(self):
        # Valid JSON but not an object. The event list is a List[dict],
        # so downstream (behaviours 9-10) only ever sees dicts.
        pievents = self._pievents()
        stream = (
            '{"type": "agent_start"}\n'
            "42\n"
            '"str"\n'
            "[1, 2]\n"
            '{"type": "agent_settled", "aborted": false}\n'
        )
        parsed = pievents.parse(stream)
        self.assertEqual(
            parsed["events"],
            [{"type": "agent_start"}, {"type": "agent_settled", "aborted": False}],
        )
        self.assertEqual(parsed["malformed_lines"], 3)
        for event in parsed["events"]:
            self.assertIsInstance(event, dict)
