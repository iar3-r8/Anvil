"""JSONL event-stream reader for ``pi --mode json`` streams.

Anvil consumes the Pi JSON event stream when recording bake-off runs
(``plans/pi-phase1-bakeoff.md``). This module owns the whole job of turning
that byte stream into structured Python data: framing the records, and - in
later cycles - the higher-level functions built on top of the framing
(``tool_calls`` and ``outcome`` account for tool usage and final state).

Framing rule (``doc/external/pi-dev/json-event-stream.md``, "Framing and
process I/O"): records are separated by LF only; an optional preceding
carriage return is stripped for CRLF streams; Unicode line and paragraph
separators (U+2028/U+2029) are ordinary string content, never boundaries.

Stdlib only: ``json``. No exception type yet - every function in this
module is total and never raises, so there is no failure to classify. The
module's one-exception convention applies once a function that can fail is
added.
"""

import json
from typing import Any, Dict, List, Optional


def parse(text: str) -> Dict[str, Any]:
    """Split a JSONL event stream into records.

    Returns a plain dict with exactly two keys, JSON-native throughout so the
    bake-off record pipeline can embed and ``json.dumps`` it directly:

    - ``"events"``: ``List[dict]`` - the parsed JSON-object records, in
      stream order;
    - ``"malformed_lines"``: ``int`` - how many non-blank lines were skipped.

    Records are split on LF only, with an optional preceding CR stripped.
    Blank (empty or whitespace-only) lines are skipped silently. A line that
    is not valid JSON, or is valid JSON but not an object, is skipped and
    counted in ``malformed_lines``; a truncated final line therefore discards
    nothing but itself. ``parse`` never raises on malformed input.
    """
    events: List[dict] = []
    malformed_lines = 0

    for line in text.split("\n"):
        # CRLF support: the CR belongs to the line ending, never to a field.
        if line.endswith("\r"):
            line = line[:-1]
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            malformed_lines += 1
            continue
        if not isinstance(record, dict):
            malformed_lines += 1
            continue
        events.append(record)

    return {"events": events, "malformed_lines": malformed_lines}


def session(events: List[dict]) -> Dict[str, Any]:
    """Extract the session header from a parsed event stream.

    Returns a plain dict with exactly two keys, JSON-native throughout so
    the bake-off record can embed it and ``json.dumps`` it directly:

    - ``"session_id"``: ``Optional[str]`` - the ``id`` of the first record,
      when that record is a ``session`` header carrying an ``id``; ``None``
      otherwise, and never ``""`` (an absent field means "no id", so it is
      not coerced to an empty string);
    - ``"version"``: ``Optional[int]`` - the ``version`` of that same first
      record; ``None`` when there is no first record to read it from, or
      the record carries no ``version`` field.

    The first record of a ``--mode json`` stream is the session header
    (``doc/external/pi-dev/json-event-stream.md``, "Session header"). A
    ``session`` record that is not the first record is ignored: only the
    first record is the header. An absent header is normal, not an error
    - RPC mode emits no header at all - so a stream whose first record is
    not a header, and an empty stream, both yield ``{"session_id": None,
    "version": None}``. ``session`` never raises.
    """
    if not events:
        return {"session_id": None, "version": None}

    first = events[0]
    if first.get("type") != "session":
        return {"session_id": None, "version": None}

    # Verbatim: "id" not in the header -> None, never "". ``.get`` returns
    # None exactly when the field is absent.
    return {
        "session_id": first.get("id"),
        "version": first.get("version"),
    }


def tool_calls(events: List[dict]) -> Dict[str, int]:
    """Account for tool usage in a parsed event stream.

    Returns a plain dict with exactly five keys, all ints:

    - ``"attempted"``: number of ``tool_execution_start`` records (each
      ``toolCallId`` counted once);
    - ``"succeeded"``: matched ``tool_execution_end`` records whose
      ``isError`` is not truthy (absent or false: the tool completed
      without an error flag);
    - ``"failed"``: matched ``tool_execution_end`` records whose
      ``isError`` is truthy;
    - ``"unfinished"``: starts whose id never gets an end;
    - ``"orphaned"``: ends whose id has no start. An orphaned end must
      not change ``attempted``, ``succeeded`` or ``failed``.

    Correlation is by ``toolCallId``, not by stream order. ``durationMs``
    is timing metadata and does not affect the counters. Non-tool event
    types are ignored. Empty input yields all five counters at 0.
    """
    started: set = set()
    ended: Dict[Any, bool] = {}

    for event in events:
        event_type = event.get("type")
        tool_call_id = event.get("toolCallId")
        if event_type == "tool_execution_start":
            started.add(tool_call_id)
        elif event_type == "tool_execution_end":
            ended[tool_call_id] = bool(event.get("isError"))

    matched = started & set(ended)
    failed = sum(1 for tool_call_id in matched if ended[tool_call_id])

    return {
        "attempted": len(started),
        "succeeded": len(matched) - failed,
        "failed": failed,
        "unfinished": len(started - set(ended)),
        "orphaned": len(set(ended) - started),
    }


def outcome(events: List[dict]) -> Dict[str, Any]:
    """Extract a run's outcome and usage from a parsed event stream.

    Returns a plain dict with exactly seven keys, JSON-native throughout:

    - ``"settled"``: ``bool`` - ``True`` iff the stream holds an
      ``agent_settled`` record (even an aborted one: an aborted run still
      settled, ``aborted`` is what says why it ended);
    - ``"aborted"``: ``Optional[bool]`` - takes ``agent_settled.aborted``
      verbatim. ``None`` when there is no ``agent_settled`` record or the
      record carries no ``aborted`` field: absent means "we do not know",
      so it is never coerced to ``False`` (which would claim knowledge the
      stream never gave); ``False`` means the stream said "not aborted";
    - ``"input"`` / ``"output"`` / ``"totalTokens"``: ``int`` - from the
      LAST ``message_update`` that carried a ``usage`` field, in stream
      order. Usage is cumulative, so the last one already contains the
      whole run: values are never summed. A ``message_update`` without a
      ``usage`` field is a content delta: it does not reset the last-seen
      usage;
    - ``"cost_total"``: ``float`` - the flattened ``cost.total`` of that
      same last usage;
    - ``"usage_reported"``: ``bool`` - ``True`` iff at least one
      ``message_update`` carried a ``usage`` field. ``False`` plus zeros
      is the signal that the numbers are placeholders, not measurements.

    Non-relevant event types (session, turn, tool, ``agent_end``) are
    ignored. Cache fields of the usage block (``cacheRead``/``cacheWrite``,
    ``cost.input``/...) are ignored. No ``agent_settled`` at all yields
    ``settled`` ``False`` and ``aborted`` ``None``; no usage ever seen
    yields zeros and ``usage_reported`` ``False``. Empty input yields
    ``settled`` ``False``, ``aborted`` ``None``, zeros, ``usage_reported``
    ``False``.
    """
    settled = False
    aborted: Optional[bool] = None
    usage_reported = False
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cost_total = 0.0

    for event in events:
        event_type = event.get("type")
        if event_type == "agent_settled":
            settled = True
            # Verbatim: "aborted" not in event -> None; present -> the
            # value as-is. ``.get`` returns None exactly when absent.
            aborted = event.get("aborted")
        elif event_type == "message_update":
            usage = event.get("usage")
            if not isinstance(usage, dict):
                continue
            usage_reported = True
            input_tokens = usage.get("input", 0)
            output_tokens = usage.get("output", 0)
            total_tokens = usage.get("totalTokens", 0)
            cost = usage.get("cost")
            if isinstance(cost, dict):
                cost_total = cost.get("total", 0.0)

    return {
        "settled": settled,
        "aborted": aborted,
        "input": input_tokens,
        "output": output_tokens,
        "totalTokens": total_tokens,
        "cost_total": cost_total,
        "usage_reported": usage_reported,
    }


def tool_durations(events: List[dict]) -> List[Dict[str, Any]]:
    """Report the duration of each tool in a parsed event stream.

    Returns a plain ``List[dict]`` in stream order, one entry per
    ``tool_execution_end`` record. ``tool_execution_start`` and
    ``tool_execution_update`` contribute no entry: only ``end`` carries a
    duration, and empty input yields ``[]``.

    Each entry is JSON-native, with exactly four keys:

    - ``"toolCallId"``: verbatim from the record;
    - ``"toolName"``: verbatim from the record;
    - ``"durationMs"``: verbatim from the record; ``None`` when the field
      is absent - ``durationMs`` is monotonic and absent when the tool did
      not run (``doc/external/pi-dev/json-event-stream.md``, "Tool
      execution events"), so an absent value must never read as a 0 ms run;
      a non-numeric value passes through uncoerced;
    - ``"isError"``: ``bool`` - truthy on the record stays ``True``; absent
      means the tool completed without an error, so it becomes ``False``,
      never ``None``.

    ``tool_durations`` never raises.
    """
    durations: List[Dict[str, Any]] = []

    for event in events:
        if event.get("type") != "tool_execution_end":
            continue
        durations.append(
            {
                "toolCallId": event.get("toolCallId"),
                "toolName": event.get("toolName"),
                # ``.get`` returns None exactly when the field is absent,
                # which is the required "the tool did not run" sentinel.
                "durationMs": event.get("durationMs"),
                "isError": bool(event.get("isError")),
            }
        )

    return durations


def retries(events: List[dict]) -> Dict[str, Any]:
    """Account for assistant-turn retries in a parsed event stream.

    Returns a plain dict with exactly five keys, JSON-native throughout so
    the bake-off record can embed it and ``json.dumps`` it directly:

    - ``"attempted"``: ``int`` - number of ``auto_retry_start`` records;
    - ``"succeeded"``: ``int`` - ``auto_retry_end`` records whose
      ``success`` is truthy;
    - ``"failed"``: ``int`` - ``auto_retry_end`` records whose ``success``
      is falsy (absent or false: the retry did not complete successfully);
    - ``"unfinished"``: ``int`` - starts with no end: more starts than ends
      in the stream (never negative);
    - ``"final_errors"``: ``List[str]`` - the ``finalError`` string of each
      end that carries one, in stream order. A ``success: false`` end
      without a ``finalError`` still counts in ``failed`` and adds nothing
      to the list, so the list never holds ``None``.

    Correlation is by start/end pairing in stream order, not by id: the
    retry events in the documentation carry no shared id field to correlate
    on (``doc/external/pi-dev/json-event-stream.md``, "Retry events"):
    ``auto_retry_start`` carries ``attempt``, ``maxAttempts``, ``delayMs``
    and ``errorMessage`` (line 181); ``auto_retry_end`` carries ``success``
    and ``attempt``, and a final failure adds a ``finalError`` string
    (line 185).

    Only the assistant-turn retry events are counted. The compaction and
    branch-summary retry events (``summarization_retry_scheduled``,
    ``summarization_retry_attempt_start``, ``summarization_retry_finished``)
    are a different mechanism - compaction's, not the assistant turn's -
    and never move any counter or entry, so a stream of only those yields
    every counter at 0 and ``final_errors`` ``[]``.

    Empty input yields all four counters at 0 and ``final_errors`` ``[]``.
    ``retries`` never raises.
    """
    attempted = 0
    finished = 0
    succeeded = 0
    failed = 0
    final_errors: List[str] = []

    for event in events:
        event_type = event.get("type")
        if event_type == "auto_retry_start":
            attempted += 1
        elif event_type == "auto_retry_end":
            finished += 1
            if event.get("success"):
                succeeded += 1
            else:
                failed += 1
            # Verbatim: a final failure adds a finalError string
            # (doc/external/pi-dev/json-event-stream.md, line 185); an
            # absent field adds no entry, so the list never holds None.
            final_error = event.get("finalError")
            if final_error is not None:
                final_errors.append(final_error)

    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "unfinished": attempted - finished if attempted > finished else 0,
        "final_errors": final_errors,
    }


def compactions(events: List[dict]) -> List[Dict[str, Any]]:
    """Report compaction pressure in a parsed event stream.

    Returns a plain ``List[dict]`` in stream order, one entry per
    ``compaction_start`` record, paired with the ``compaction_end`` that
    follows it when one arrives. Correlation is by start/end pairing in
    stream order, not by id: the compaction events in the documentation
    carry no shared id field to correlate on
    (``doc/external/pi-dev/json-event-stream.md``, "Compaction events").
    An end with no start pending contributes nothing. A start that never
    gets an end still yields its entry, flagged ``completed`` ``False``.
    Empty input yields ``[]``.

    Each entry is JSON-native, with exactly five keys:

    - ``"reason"``: verbatim from the start record's ``reason``; never
      validated against the three documented values ``manual``,
      ``threshold`` and ``overflow`` (
      ``doc/external/pi-dev/json-event-stream.md``,
      "compaction_start.reason", line 148) - the field is data;
    - ``"tokensBefore"`` / ``"estimatedTokensAfter"``: verbatim from the
      paired end's ``result`` (
      ``doc/external/pi-dev/json-event-stream.md``,
      "compaction_end.result", line 160); ``None`` when the end never
      arrived, when it carries no ``result`` at all - an aborted or
      failed compaction omits it (line 172) - or when the field is
      absent inside a present ``result``. A missing value is "we do not
      know", never ``0``: a ``0`` would read as a compaction that freed
      the whole window;
    - ``"aborted"``: the end record's ``aborted`` verbatim; ``None`` when
      no end arrived, because we do not know whether it aborted;
    - ``"completed"``: ``True`` iff the paired end arrived - an end is an
      end, even an aborted one; ``False`` for a start with no end.

    ``compactions`` never raises.
    """
    entries: List[Dict[str, Any]] = []
    open_entries: List[Dict[str, Any]] = []

    for event in events:
        event_type = event.get("type")
        if event_type == "compaction_start":
            entry = {
                # Verbatim from the start; never validated against the
                # documented values (line 148). ``.get`` returns None
                # exactly when the field is absent.
                "reason": event.get("reason"),
                # Both token fields start None: "we do not know" until a
                # paired end's result says otherwise. Never 0.
                "tokensBefore": None,
                "estimatedTokensAfter": None,
                # No end yet: we do not know whether it aborted.
                "aborted": None,
                "completed": False,
            }
            entries.append(entry)
            open_entries.append(entry)
        elif event_type == "compaction_end" and open_entries:
            entry = open_entries.pop(0)
            entry["completed"] = True
            # Verbatim from the end; absent -> None, never a coerced
            # False (which would claim the stream never gave).
            entry["aborted"] = event.get("aborted")
            # If compaction aborted or failed, result is absent (line
            # 172) - a non-dict result is treated the same: unknown.
            result = event.get("result")
            if isinstance(result, dict):
                entry["tokensBefore"] = result.get("tokensBefore")
                entry["estimatedTokensAfter"] = result.get(
                    "estimatedTokensAfter"
                )

    return entries


def usage_detail(events: List[dict]) -> Dict[str, Any]:
    """Report the cache and cost breakdown of a parsed event stream.

    Returns a plain dict with exactly eight keys, JSON-native throughout
    so the record pipeline can embed it and ``json.dumps`` it directly:

    - ``"cacheRead"`` / ``"cacheWrite"``: ``int`` - the cache token
      counts of the LAST ``message_update`` that carried a ``usage``
      field, in stream order, verbatim;
    - ``"cost_input"`` / ``"cost_output"`` / ``"cost_cacheRead"`` /
      ``"cost_cacheWrite"`` / ``"cost_total"``: ``float`` - the flattened
      ``cost`` block of that same last usage (``cost.input``,
      ``cost.output``, ``cost.cacheRead``, ``cost.cacheWrite``,
      ``cost.total``); all five zeros when the usage carries no
      ``cost`` block - the provider withheld the cost, so the cost
      fields are placeholders while the token fields still report;
    - ``"usage_reported"``: ``bool`` - ``True`` iff at least one
      ``message_update`` carried a ``usage`` field. ``False`` plus zeros
      is the signal that the numbers are placeholders, not measurements.

    The source rule is identical to ``outcome``'s (line 142): the LAST
    ``message_update`` that carried a ``usage`` field wins - usage is
    cumulative (``doc/external/pi-dev/json-event-stream.md``, line 110),
    so values are never summed; a ``message_update`` without a
    ``usage`` field is a content delta and does not reset the last-seen
    usage. The ``usage`` field carries ``input``, ``output``,
    ``cacheRead``, ``cacheWrite``, ``totalTokens`` and ``cost``
    (``doc/external/pi-dev/json-event-stream.md``, line 113). This
    sibling reports the cache and cost fields that ``outcome``
    deliberately omits: ``outcome``'s closed seven-key shape is a
    landed pin and is untouched here.

    No usage ever seen yields all value fields zero and
    ``usage_reported`` ``False``; empty input yields the same.
    ``usage_detail`` never raises.
    """
    usage_reported = False
    cache_read = 0
    cache_write = 0
    cost_input = 0.0
    cost_output = 0.0
    cost_cache_read = 0.0
    cost_cache_write = 0.0
    cost_total = 0.0

    for event in events:
        if event.get("type") != "message_update":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            continue
        usage_reported = True
        # Verbatim from the last usage; ``.get`` returns the default
        # exactly when the field is absent.
        cache_read = usage.get("cacheRead", 0)
        cache_write = usage.get("cacheWrite", 0)
        # An absent cost block yields all five cost zeros while the
        # token fields still report. A non-dict cost block is treated
        # the same way as ``outcome`` treats one: the cost fields are
        # left as the previous usage set them, never reset.
        cost = usage.get("cost")
        if isinstance(cost, dict):
            cost_input = cost.get("input", 0.0)
            cost_output = cost.get("output", 0.0)
            cost_cache_read = cost.get("cacheRead", 0.0)
            cost_cache_write = cost.get("cacheWrite", 0.0)
            cost_total = cost.get("total", 0.0)

    return {
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "cost_input": cost_input,
        "cost_output": cost_output,
        "cost_cacheRead": cost_cache_read,
        "cost_cacheWrite": cost_cache_write,
        "cost_total": cost_total,
        "usage_reported": usage_reported,
    }
