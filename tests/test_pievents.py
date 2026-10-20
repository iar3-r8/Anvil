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


# --- Behaviour 9: tool-call accounting -----------------------------------
#
# Pinned return shape: ``tool_calls(events: List[dict])`` returns a plain
# dict with exactly five keys, all ints:
#
# - ``"attempted"``: number of ``tool_execution_start`` records;
# - ``"succeeded"``: matched ``end`` records whose ``isError`` is not
#   truthy (an ``end`` with ``isError`` absent counts as a success: the
#   tool completed without an error flag);
# - ``"failed"``: matched ``end`` records with ``isError`` truthy;
# - ``"unfinished"``: ``start`` records with no matching ``end``;
# - ``"orphaned"``: ``end`` records whose ``toolCallId`` has no ``start``.
#
# A plain dict, JSON-native, because behaviour 11 embeds the counts
# verbatim in the run record and ``json.dumps``-es it. Several tests assert
# the complete dict by value, so the coder has no room for extra keys.
#
# Event shapes (``doc/external/pi-dev/json-event-stream.md``, "Tool
# execution events"): ``tool_execution_start`` carries ``toolCallId`` and
# ``toolName``; ``tool_execution_end`` carries ``toolCallId``, ``isError``
# (bool) and ``durationMs`` (absent when the tool did not run).
TOOL_CALL_KEYS = {"attempted", "succeeded", "failed", "unfinished", "orphaned"}


class ToolCallsTestCase(PieventsTestCase):
    """Base for behaviour 9: guarded access to ``tool_calls`` and a
    helper that builds raw JSONL text from record dicts, so the tests see
    the real stream shape through ``parse``."""

    def _tool_calls(self):
        """Fetch ``anvilkit.pievents.tool_calls``, failing clearly if absent."""
        pievents = self._pievents()
        tool_calls = getattr(pievents, "tool_calls", None)
        self.assertTrue(
            callable(tool_calls),
            "anvilkit.pievents.tool_calls is not callable; the "
            "tool-call accounting (behaviour 9) has not been "
            "implemented yet",
        )
        return tool_calls

    @staticmethod
    def _stream_lines(records):
        """One JSON object per line, LF-joined, with a trailing LF."""
        return "\n".join(json.dumps(record) for record in records) + "\n"


class TestToolCallsReturnShape(ToolCallsTestCase):
    """The pinned return shape: a plain dict, exactly the five counter
    keys, all ints; empty stream yields all zeros."""

    def test_tool_calls_returns_dict_with_exactly_five_int_keys(self):
        tool_calls = self._tool_calls()
        result = tool_calls([])
        self.assertIsInstance(
            result,
            dict,
            "tool_calls must return a plain dict, so the bake-off record "
            "(behaviour 11) can embed it and json.dumps it directly",
        )
        self.assertEqual(
            set(result),
            TOOL_CALL_KEYS,
            "tool_calls must return exactly the five counter keys: no "
            "extra keys, no missing keys",
        )
        for key in TOOL_CALL_KEYS:
            self.assertIsInstance(
                result[key],
                int,
                "tool_calls['%s'] must be an int" % key,
            )

    def test_tool_calls_empty_events_yields_all_zero_counters(self):
        tool_calls = self._tool_calls()
        self.assertEqual(
            tool_calls([]),
            {
                "attempted": 0,
                "succeeded": 0,
                "failed": 0,
                "unfinished": 0,
                "orphaned": 0,
            },
            "an empty stream has nothing to account for: all five "
            "counters must be exactly zero",
        )

    def test_tool_calls_on_parsed_empty_stream_yields_all_zero_counters(self):
        # Through the real entry path: parse("") -> {"events": [], ...}
        pievents = self._pievents()
        tool_calls = self._tool_calls()
        result = tool_calls(pievents.parse("")["events"])
        self.assertEqual(
            result,
            {
                "attempted": 0,
                "succeeded": 0,
                "failed": 0,
                "unfinished": 0,
                "orphaned": 0,
            },
        )


class TestToolCallsPlanGivenStream(ToolCallsTestCase):
    """Contract 1: the plan's given stream, raw JSONL text through
    ``parse``. Three starts (ids A, B, C) plus two ends - A with
    ``isError: false`` and B with ``isError: true`` - leave C unfinished."""

    def test_tool_calls_plan_given_stream_counts_three_one_one_one(self):
        tool_calls = self._tool_calls()
        pievents = self._pievents()
        stream = self._stream_lines(
            [
                {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
                {"type": "tool_execution_start", "toolCallId": "B", "toolName": "bash"},
                {"type": "tool_execution_start", "toolCallId": "C", "toolName": "write"},
                {
                    "type": "tool_execution_end",
                    "toolCallId": "A",
                    "toolName": "read",
                    "result": {"ok": True},
                    "isError": False,
                    "durationMs": 12,
                },
                {
                    "type": "tool_execution_end",
                    "toolCallId": "B",
                    "toolName": "bash",
                    "result": None,
                    "isError": True,
                    "durationMs": 40,
                },
            ]
        )
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 3,
                "succeeded": 1,
                "failed": 1,
                "unfinished": 1,
                "orphaned": 0,
            },
            "three starts -> attempted 3; end A (isError false) -> "
            "succeeded 1; end B (isError true) -> failed 1; start C "
            "never ended -> unfinished 1; every end matched a start -> "
            "orphaned 0",
        )


class TestToolCallsCorrelationById(ToolCallsTestCase):
    """Contract 2: correlation is by ``toolCallId``, not by order or
    position: an end for id C arriving before the end for id A must
    still credit C."""

    def test_tool_calls_ends_out_of_order_credit_by_tool_call_id(self):
        tool_calls = self._tool_calls()
        stream = self._stream_lines(
            [
                {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
                {"type": "tool_execution_start", "toolCallId": "B", "toolName": "bash"},
                {"type": "tool_execution_start", "toolCallId": "C", "toolName": "edit"},
                # end C arrives first: an order-based (positional)
                # correlator would credit A instead.
                {
                    "type": "tool_execution_end",
                    "toolCallId": "C",
                    "toolName": "edit",
                    "result": {"ok": True},
                    "isError": False,
                    "durationMs": 7,
                },
                {
                    "type": "tool_execution_end",
                    "toolCallId": "A",
                    "toolName": "read",
                    "result": None,
                    "isError": True,
                    "durationMs": 3,
                },
            ]
        )
        pievents = self._pievents()
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 3,
                "succeeded": 1,
                "failed": 1,
                "unfinished": 1,
                "orphaned": 0,
            },
            "the ends must be matched to their starts by toolCallId: "
            "end C is the success, end A is the failure, and B stays "
            "unfinished even though its start is the middle one",
        )


class TestToolCallsOrphanedEnd(ToolCallsTestCase):
    """Contract 3: an ``end`` with no matching ``start`` is counted in
    ``orphaned`` and does NOT silently change ``attempted``/
    ``succeeded``/``failed``."""

    def test_tool_calls_end_without_start_is_orphaned_not_attempted(self):
        tool_calls = self._tool_calls()
        stream = self._stream_lines(
            [
                {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
                {
                    "type": "tool_execution_end",
                    "toolCallId": "A",
                    "toolName": "read",
                    "result": {"ok": True},
                    "isError": False,
                    "durationMs": 5,
                },
                # no start for id Z anywhere in the stream
                {
                    "type": "tool_execution_end",
                    "toolCallId": "Z",
                    "toolName": "bash",
                    "result": None,
                    "isError": True,
                    "durationMs": 9,
                },
            ]
        )
        pievents = self._pievents()
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 1,
                "succeeded": 1,
                "failed": 0,
                "unfinished": 0,
                "orphaned": 1,
            },
            "the orphan end for id Z is not a tool that was attempted: "
            "attempted must stay 1 and the orphan's isError: true must "
            "not increment failed - it goes to orphaned only",
        )


class TestToolCallsEndWithoutIsError(ToolCallsTestCase):
    """Contract 4: an ``end`` whose ``isError`` field is absent counts
    as a success - the tool completed without an error flag."""

    def test_tool_calls_end_missing_isError_counts_as_succeeded(self):
        tool_calls = self._tool_calls()
        events = [
            {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
            {
                "type": "tool_execution_end",
                "toolCallId": "A",
                "toolName": "read",
                "result": {"ok": True},
                "durationMs": 11,
                # isError deliberately absent
            },
        ]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 1,
                "succeeded": 1,
                "failed": 0,
                "unfinished": 0,
                "orphaned": 0,
            },
            "an end with no isError field is a completed tool without an "
            "error flag: it is a success, not a failure and not "
            "unfinished",
        )


class TestToolCallsEndWithoutDurationMs(ToolCallsTestCase):
    """Contract 5: ``durationMs`` is absent when the tool did not run
    (``doc/external/pi-dev/json-event-stream.md``, "Tool execution
    events") - its absence must not disturb the five counters."""

    def test_tool_calls_end_missing_durationMs_counters_unaffected(self):
        tool_calls = self._tool_calls()
        stream = self._stream_lines(
            [
                {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
                {"type": "tool_execution_start", "toolCallId": "B", "toolName": "bash"},
                {
                    "type": "tool_execution_end",
                    "toolCallId": "A",
                    "toolName": "read",
                    "result": {"ok": True},
                    "isError": False,
                    # durationMs deliberately absent: the tool did not run
                },
                {
                    "type": "tool_execution_end",
                    "toolCallId": "B",
                    "toolName": "bash",
                    "result": None,
                    "isError": True,
                    "durationMs": 21,
                },
            ]
        )
        pievents = self._pievents()
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 2,
                "succeeded": 1,
                "failed": 1,
                "unfinished": 0,
                "orphaned": 0,
            },
            "durationMs is timing metadata, not a counter input: an end "
            "lacking it is still a complete end for its toolCallId",
        )


class TestToolCallsNoEndsAtAll(ToolCallsTestCase):
    """Contract 7: a stream of starts with no ends at all - every start
    is unfinished."""

    def test_tool_calls_starts_without_any_ends_are_all_unfinished(self):
        tool_calls = self._tool_calls()
        events = [
            {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
            {"type": "tool_execution_start", "toolCallId": "B", "toolName": "write"},
        ]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 2,
                "succeeded": 0,
                "failed": 0,
                "unfinished": 2,
                "orphaned": 0,
            },
            "with no end records at all, both starts stay unfinished and "
            "succeeded/failed/orphaned stay zero",
        )


class TestToolCallsIgnoresOtherEvents(ToolCallsTestCase):
    """A real ``--mode json`` stream interleaves session, message and
    queue records with the tool records: only ``tool_execution_start``
    and ``tool_execution_end`` may move the counters."""

    def test_tool_calls_ignores_non_tool_event_types(self):
        tool_calls = self._tool_calls()
        stream = self._stream_lines(
            [
                {"type": "session", "version": 3, "id": "uuid", "cwd": "/path"},
                {"type": "agent_start"},
                {"type": "turn_start"},
                {
                    "type": "message_update",
                    "usage": {"input": 10, "output": 1, "totalTokens": 11},
                },
                {"type": "tool_execution_start", "toolCallId": "A", "toolName": "read"},
                {"type": "tool_execution_update", "toolCallId": "A", "partialResult": {}},
                {
                    "type": "tool_execution_end",
                    "toolCallId": "A",
                    "toolName": "read",
                    "result": {"ok": True},
                    "isError": False,
                    "durationMs": 2,
                },
                {"type": "agent_settled", "aborted": False},
            ]
        )
        pievents = self._pievents()
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            tool_calls(events),
            {
                "attempted": 1,
                "succeeded": 1,
                "failed": 0,
                "unfinished": 0,
                "orphaned": 0,
            },
            "session, agent, turn, message and tool_execution_update "
            "records are not tool lifecycle boundaries: only the one "
            "start/end pair must move the counters",
        )


# --- Behaviour 10: outcome and usage ---------------------------------------
#
# Pinned return shape: ``outcome(events: List[dict])`` returns a plain dict
# with exactly seven keys, JSON-native throughout:
#
# - ``"settled"``: ``bool`` - ``True`` iff the stream holds an
#   ``agent_settled`` record;
# - ``"aborted"``: ``Optional[bool]`` - takes ``agent_settled.aborted``
#   verbatim; ``None`` when the stream has no ``agent_settled`` record OR
#   the record carries no ``aborted`` field. Pinned: absent field means
#   ``None``, never a coerced ``False`` - the field's mere presence is what
#   distinguishes "the run said it was not aborted" (False) from "we do
#   not know" (None), and ``None`` is already the never-finished sentinel,
#   so a coerced False would silently claim knowledge the stream never gave.
#   (An aborted run still settles: ``settled`` True, ``aborted`` True.)
# - ``"input"`` / ``"output"`` / ``"totalTokens"``: ``int`` - from the LAST
#   ``message_update.usage`` seen in stream order (usage is cumulative per
#   ``doc/external/pi-dev/json-event-stream.md``, "Reconstruct streaming
#   messages", so the last one wins; it is never summed);
# - ``"cost_total"``: ``float`` - the flattened ``cost.total`` of that same
#   last usage (the flattened spelling because behaviour 11's record key is
#   ``cost_total``);
# - ``"usage_reported"``: ``bool`` - ``True`` iff at least one
#   ``message_update`` carried a ``usage`` field. ``False`` plus zeros is
#   the signal that the numbers are placeholders, not measurements -
#   Pi's docs note usage can stay zero until completion when the provider
#   does not report it while streaming.
#
# A plain dict, JSON-native, because behaviour 11 embeds the fields
# verbatim in the run record and ``json.dumps``-es it. Several tests assert
# the complete dict by value, so the coder has no room for extra keys.
#
# Event shapes (``doc/external/pi-dev/json-event-stream.md``):
# ``message_update`` carries cumulative ``usage`` (``input``, ``output``,
# ``totalTokens``, ``cost.total``); ``agent_settled`` carries ``aborted``;
# ``agent_end.willRetry`` precedes ``agent_settled`` and is noise for this
# function.
OUTCOME_KEYS = {
    "settled",
    "aborted",
    "input",
    "output",
    "totalTokens",
    "cost_total",
    "usage_reported",
}


class OutcomeTestCase(PieventsTestCase):
    """Base for behaviour 10: guarded access to ``outcome`` and stream
    builders, so the tests see the real stream shape through ``parse``."""

    def _get_outcome(self):
        """Fetch ``anvilkit.pievents.outcome``, failing clearly if absent.

        Named ``_get_outcome`` on purpose: ``unittest.TestCase`` owns an
        instance attribute called ``_outcome`` (set by ``TestCase.__call__``
        to its internal ``_Outcome`` result tracker), which would shadow a
        helper of that name and turn every call into
        ``TypeError: '_Outcome' object is not callable``.
        """
        pievents = self._pievents()
        outcome = getattr(pievents, "outcome", None)
        self.assertTrue(
            callable(outcome),
            "anvilkit.pievents.outcome is not callable; the "
            "outcome/usage extraction (behaviour 10) has not been "
            "implemented yet",
        )
        return outcome

    @staticmethod
    def _stream_lines(records):
        """One JSON object per line, LF-joined, with a trailing LF."""
        return "\n".join(json.dumps(record) for record in records) + "\n"

    @staticmethod
    def _usage(input_tokens, output_tokens, total_tokens, cost_total):
        """A cumulative usage block in Pi's shape: the four fields this
        behaviour reads, plus the cache fields that real streams carry
        and that must be ignored by ``outcome``."""
        return {
            "input": input_tokens,
            "output": output_tokens,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": total_tokens,
            "cost": {
                "input": 0.0,
                "output": 0.0,
                "cacheRead": 0.0,
                "cacheWrite": 0.0,
                "total": cost_total,
            },
        }


class TestOutcomeReturnShape(OutcomeTestCase):
    """The pinned return shape: a plain dict, exactly the seven keys,
    with the documented types; empty stream yields the never-finished
    default."""

    def test_outcome_returns_dict_with_exactly_seven_keys_and_types(self):
        outcome = self._get_outcome()
        result = outcome([])
        self.assertIsInstance(
            result,
            dict,
            "outcome must return a plain dict, so the bake-off record "
            "(behaviour 11) can embed it and json.dumps it directly",
        )
        self.assertEqual(
            set(result),
            OUTCOME_KEYS,
            "outcome must return exactly the seven keys: no extra keys, "
            "no missing keys",
        )
        self.assertIsInstance(result["settled"], bool)
        self.assertIs(result["aborted"], None)
        for key in ("input", "output", "totalTokens"):
            self.assertIsInstance(result[key], int, "outcome['%s'] must be an int" % key)
        self.assertIsInstance(result["cost_total"], float)
        self.assertIsInstance(result["usage_reported"], bool)

    def test_outcome_empty_stream_is_never_finished_with_zero_usage(self):
        # Contract 5: empty stream -> the run never finished and nothing
        # was ever reported.
        outcome = self._get_outcome()
        self.assertEqual(
            outcome([]),
            {
                "settled": False,
                "aborted": None,
                "input": 0,
                "output": 0,
                "totalTokens": 0,
                "cost_total": 0.0,
                "usage_reported": False,
            },
            "an empty stream never settled and never reported usage: "
            "settled False, aborted None, zeros, usage_reported False",
        )


class TestOutcomeHappyPath(OutcomeTestCase):
    """Contract 1: the plan's given stream, raw JSONL text through
    ``parse`` - several cumulative ``message_update`` records with
    increasing values, then a settled run whose ``agent_settled`` record
    carries no ``aborted`` field. The LAST usage wins; the absent field
    pins ``aborted`` to ``None`` (not a coerced ``False``)."""

    def test_outcome_plan_given_stream_takes_last_cumulative_usage(self):
        outcome = self._get_outcome()
        pievents = self._pievents()
        stream = self._stream_lines(
            [
                {"type": "session", "version": 3, "id": "uuid", "cwd": "/path"},
                {"type": "agent_start"},
                {"type": "turn_start"},
                {
                    "type": "message_update",
                    "usage": self._usage(10, 5, 15, 0.0001),
                    "assistantMessageEvent": {"type": "text_delta", "delta": "Hi"},
                },
                {
                    "type": "message_update",
                    "usage": self._usage(12, 20, 32, 0.0002),
                    "assistantMessageEvent": {"type": "text_delta", "delta": " there"},
                },
                {"type": "tool_execution_start", "toolCallId": "A", "toolName": "edit"},
                {
                    "type": "tool_execution_end",
                    "toolCallId": "A",
                    "toolName": "edit",
                    "result": {"ok": True},
                    "isError": False,
                    "durationMs": 3,
                },
                {
                    "type": "message_update",
                    "usage": self._usage(15, 40, 55, 0.00035),
                    "assistantMessageEvent": {"type": "text_delta", "delta": " done"},
                },
                {"type": "agent_end", "messages": [], "willRetry": False},
                # aborted deliberately absent: the field's presence is
                # what separates False from None
                {"type": "agent_settled"},
            ]
        )
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            outcome(events),
            {
                "settled": True,
                "aborted": None,
                "input": 15,
                "output": 40,
                "totalTokens": 55,
                "cost_total": 0.00035,
                "usage_reported": True,
            },
            "settled True from the agent_settled record; aborted None "
            "because the record carries no aborted field (absent is not "
            "false); tokens and cost_total from the LAST message_update."
            "usage (15/40/55, cost.total 0.00035), not the earlier "
            "cumulative snapshots and not a sum",
        )

    def test_outcome_agent_settled_with_explicit_false_aborted_pins_false(self):
        # Pins the other side of the absent-field decision: when the
        # stream DOES say "not aborted", the result is False, not None.
        outcome = self._get_outcome()
        events = [
            {"type": "message_update", "usage": self._usage(3, 2, 5, 0.00005)},
            {"type": "agent_settled", "aborted": False},
        ]
        self.assertEqual(
            outcome(events),
            {
                "settled": True,
                "aborted": False,
                "input": 3,
                "output": 2,
                "totalTokens": 5,
                "cost_total": 0.00005,
                "usage_reported": True,
            },
            "an explicit aborted: false is known information and must "
            "surface as False, distinct from the None of an absent "
            "field",
        )


class TestOutcomeAbortedRun(OutcomeTestCase):
    """Contract 2: an aborted run still settled - ``agent_settled`` with
    ``aborted: true`` means ``settled`` True AND ``aborted`` True."""

    def test_outcome_aborted_settled_run_reports_settled_true_aborted_true(self):
        outcome = self._get_outcome()
        pievents = self._pievents()
        stream = self._stream_lines(
            [
                {"type": "agent_start"},
                {
                    "type": "message_update",
                    "usage": self._usage(8, 11, 19, 0.00012),
                },
                {"type": "agent_end", "messages": [], "willRetry": False},
                {"type": "agent_settled", "aborted": True},
            ]
        )
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            outcome(events),
            {
                "settled": True,
                "aborted": True,
                "input": 8,
                "output": 11,
                "totalTokens": 19,
                "cost_total": 0.00012,
                "usage_reported": True,
            },
            "the run ended by abort but it DID settle: settled stays "
            "True while aborted takes the record's true; the usage "
            "reported before the abort is still the run's usage",
        )


class TestOutcomeNeverFinished(OutcomeTestCase):
    """Contract 3: usage was reported but no ``agent_settled`` record
    ever arrived - the run never finished. ``settled`` False and
    ``aborted`` None are the signal; the token numbers are still what
    they are (the plan: the numbers are the numbers, ``settled`` is what
    tells you they are final)."""

    def test_outcome_usage_without_agent_settled_is_never_finished(self):
        outcome = self._get_outcome()
        pievents = self._pievents()
        stream = self._stream_lines(
            [
                {"type": "agent_start"},
                {"type": "turn_start"},
                {
                    "type": "message_update",
                    "usage": self._usage(10, 5, 15, 0.0001),
                },
                {
                    "type": "message_update",
                    "usage": self._usage(12, 20, 32, 0.0002),
                },
                # the stream ends here: no agent_settled anywhere
            ]
        )
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            outcome(events),
            {
                "settled": False,
                "aborted": None,
                "input": 12,
                "output": 20,
                "totalTokens": 32,
                "cost_total": 0.0002,
                "usage_reported": True,
            },
            "without an agent_settled record the run never finished: "
            "settled False, aborted None - but the last-seen usage is "
            "still reported as-is, because settled is what says the "
            "numbers are final",
        )


class TestOutcomeNoUsageSeen(OutcomeTestCase):
    """Contract 4: a settled run whose stream never carried a usage
    field - zeros plus ``usage_reported: False``, which is the signal
    the numbers are placeholders, not measurements."""

    def test_outcome_settled_run_without_any_usage_reports_zeros(self):
        outcome = self._get_outcome()
        pievents = self._pievents()
        stream = self._stream_lines(
            [
                {"type": "agent_start"},
                # message updates without usage (a provider that does not
                # report usage while streaming)
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": "Hi"},
                },
                {"type": "message_end", "message": {"role": "assistant"}},
                {"type": "agent_end", "messages": [], "willRetry": False},
                {"type": "agent_settled", "aborted": False},
            ]
        )
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            outcome(events),
            {
                "settled": True,
                "aborted": False,
                "input": 0,
                "output": 0,
                "totalTokens": 0,
                "cost_total": 0.0,
                "usage_reported": False,
            },
            "no usage was ever seen: zeros plus usage_reported False - "
            "the downstream record must be able to tell a measured zero "
            "from a missing measurement",
        )


class TestOutcomeCumulativeLastWins(OutcomeTestCase):
    """Contract 6: usage is cumulative, so the LAST record's values win -
    they are never added together. totalTokens 110 then 250 must yield
    250, not 360."""

    def test_outcome_two_cumulative_usage_records_yield_last_not_sum(self):
        outcome = self._get_outcome()
        events = [
            {"type": "message_update", "usage": self._usage(100, 10, 110, 0.01)},
            {"type": "message_update", "usage": self._usage(200, 50, 250, 0.025)},
            {"type": "agent_settled", "aborted": False},
        ]
        self.assertEqual(
            outcome(events),
            {
                "settled": True,
                "aborted": False,
                "input": 200,
                "output": 50,
                "totalTokens": 250,
                "cost_total": 0.025,
                "usage_reported": True,
            },
            "cumulative usage means the last record already contains the "
            "whole run: 250 totalTokens, not 110 + 250 = 360, and cost "
            "0.025, not 0.01 + 0.025 = 0.035",
        )


class TestOutcomeMessageUpdateWithoutUsage(OutcomeTestCase):
    """Contract 7: a ``message_update`` without a ``usage`` field -
    common in a real stream, where most deltas carry no usage - is
    ignored for token purposes and does NOT reset the last-seen usage,
    not even when it is the last record before settle."""

    def test_outcome_usageless_message_updates_do_not_reset_last_usage(self):
        outcome = self._get_outcome()
        pievents = self._pievents()
        stream = self._stream_lines(
            [
                {"type": "agent_start"},
                {
                    "type": "message_update",
                    "usage": self._usage(10, 5, 15, 0.0001),
                },
                # a usage-less delta between the two usage-bearing updates
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": "..."},
                },
                {
                    "type": "message_update",
                    "usage": self._usage(12, 20, 32, 0.0002),
                },
                # and one trailing after the last usage-bearing update:
                # it must not clear or zero the last-seen usage
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": "done"},
                },
                {"type": "agent_settled", "aborted": False},
            ]
        )
        events = pievents.parse(stream)["events"]
        self.assertEqual(
            outcome(events),
            {
                "settled": True,
                "aborted": False,
                "input": 12,
                "output": 20,
                "totalTokens": 32,
                "cost_total": 0.0002,
                "usage_reported": True,
            },
            "usage-less message_updates are content deltas, not usage "
            "resets: the numbers must still be those of the last "
            "usage-bearing record (12/20/32, cost.total 0.0002)",
        )
