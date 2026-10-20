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

Stdlib only: ``json``. No exception type yet - ``parse`` never raises on
malformed input, so there is no failure to classify. The module's
one-exception convention applies once a later function that can fail is
added.
"""

import json
from typing import Any, Dict, List


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
