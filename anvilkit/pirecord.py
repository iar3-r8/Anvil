"""Bake-off run-record builder (``plans/pi-phase1-bakeoff.md``, behaviour 11).

Anvil records every Pi bake-off run as a single JSON-native dict with a closed
thirteen-key shape, assembled here from the three dimension sources the rest of
the bake-off pipeline produces:

- the **run outcome** - exit code, wall time, the waited-for-input flag and
  the artifact paths, measured by the host recipe;
- **the model's work** - the tool-call counters shaped by
  ``anvilkit.pievents.tool_calls`` and the outcome dict shaped by
  ``anvilkit.pievents.outcome``;
- **the fixture state** - the assertion result from
  ``anvilkit.pifixture.assertion_passes`` and the changed-files list from
  ``anvilkit.pifixture.changed_files``.

``build`` validates that every dimension arrived (a missing one raises
``RecordError`` naming the field, so a half-recorded run cannot become a
verdict) and assembles the record. ``render_table`` (behaviour 12) renders
a list of records as the go/no-go Markdown table plus the verdict line,
a read-only view: it never mutates its records.

Stdlib only. One exception type: ``RecordError``.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

_CONFIG_VALUES = ("print", "json", "ultrawork")
_ARTIFACT_KEYS = ("stdout", "stderr", "jsonl", "before_digest", "after_digest")
_TOOL_CALL_KEYS = ("attempted", "succeeded", "failed", "unfinished", "orphaned")
_OUTCOME_KEYS = (
    "settled",
    "aborted",
    "input",
    "output",
    "totalTokens",
    "cost_total",
    "usage_reported",
)


class RecordError(Exception):
    """A dimension needed for the run record is missing or malformed.

    A single exception type covers every half-record guard, so the host recipe
    needs only one ``except`` clause. Every message names the field whose
    value must be recovered.
    """


def _require_dict(value: Any, field: str) -> Dict[str, Any]:
    """Fail naming ``field`` when a required dict dimension is absent."""
    if value is None:
        raise RecordError(
            "{} is missing: a half-recorded run cannot become a verdict".format(field)
        )
    if not isinstance(value, dict):
        raise RecordError(
            "{} must be a dict, got {}".format(field, type(value).__name__)
        )
    return value


def _require_counter_keys(mapping: Dict[str, Any], keys: Tuple[str, ...], field: str) -> None:
    """Fail naming ``field`` when a counter dict is missing any of its keys."""
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise RecordError(
            "{} is missing required counter key(s): {}".format(field, ", ".join(missing))
        )


def _validate_artifacts(artifacts: Any) -> Dict[str, Any]:
    """Validate the artifacts sub-dict: exactly the five pinned keys, each a
    ``str`` path except ``jsonl``, which may be ``None`` for the print and
    ultrawork runs that produce no JSONL stream."""
    if artifacts is None:
        raise RecordError(
            "artifacts is missing: a half-recorded run cannot become a verdict"
        )
    if not isinstance(artifacts, dict):
        raise RecordError(
            "artifacts must be a dict, got {}".format(type(artifacts).__name__)
        )
    missing = [key for key in _ARTIFACT_KEYS if key not in artifacts]
    extra = [key for key in artifacts if key not in _ARTIFACT_KEYS]
    if missing or extra:
        raise RecordError(
            "artifacts must have exactly the keys {}, "
            "missing: {}, extra: {}".format(_ARTIFACT_KEYS, missing, extra)
        )
    for key, value in artifacts.items():
        if value is not None and not isinstance(value, str):
            raise RecordError(
                "artifacts[{}] must be a str path (serialize Path objects by "
                "the caller), got {}".format(key, type(value).__name__)
            )
    return artifacts


def build(
    config: str,
    *,
    model: str,
    exit_code: Optional[int],
    wall_time_s: float,
    waited_for_input: bool,
    artifacts: Any,
    tool_calls: Any,
    outcome: Any,
    assertion: Any,
    changed_files: Optional[List[str]],
    timestamp: str,
) -> Dict[str, Any]:
    """Assemble the thirteen-key bake-off run record.

    Everything after ``config`` is keyword-only, so a half-recorded run cannot
    pass a dimension in the wrong position: the caller must name every
    dimension, and :class:`RecordError` can point at the exact field.

    The returned dict is a plain dict with exactly the thirteen pinned keys,
    JSON-native throughout, so ``json.loads(json.dumps(record,
    sort_keys=True)) == record`` holds by construction:

    - ``"config"``: one of ``"print"``, ``"json"``, ``"ultrawork"``;
    - ``"completed"``: ``True`` iff ``exit_code == 0`` AND the assertion's
      ``passed`` is ``True``;
    - ``"exit_code"``, ``"wall_time_s"``, ``"waited_for_input"``,
      ``"changed_files"``, ``"tool_calls"``, ``"assertion"``, ``"model"`` and
      ``"timestamp"``: verbatim;
    - ``"tokens"``: ``{"input": int, "output": int, "totalTokens": int}``
      lifted from the outcome dict - the remaining outcome fields stay in the
      JSONL artifacts, not in the closed record key set;
    - ``"cost_total"``: lifted from the outcome dict's ``cost_total``;
    - ``"artifacts"``: exactly the keys ``stdout``, ``stderr``, ``jsonl``,
      ``before_digest``, ``after_digest``; each a ``str`` path except
      ``jsonl``, which may be ``None``.

    Raises:
        RecordError: ``config`` is not one of the three pinned configurations;
            any required dimension (``tool_calls``, ``outcome``, ``assertion``,
            ``exit_code``, ``changed_files``, ``artifacts``) is missing; a
            counter dict is missing a key; ``artifacts`` carries a wrong key
            set or a non-``str`` path; or ``timestamp`` is not a string.
    """
    if config not in _CONFIG_VALUES:
        raise RecordError(
            "config must be one of {}, got {!r}".format(_CONFIG_VALUES, config)
        )
    if exit_code is None:
        raise RecordError(
            "exit_code is missing: a half-recorded run cannot become a verdict"
        )
    if changed_files is None:
        raise RecordError(
            "changed_files is missing: a half-recorded run cannot become a verdict"
        )
    if not isinstance(timestamp, str):
        raise RecordError(
            "timestamp must be a str (the caller passes the ISO-8601 UTC "
            "stamp), got {}".format(type(timestamp).__name__)
        )

    tool_calls_dict = _require_dict(tool_calls, "tool_calls")
    _require_counter_keys(tool_calls_dict, _TOOL_CALL_KEYS, "tool_calls")
    outcome_dict = _require_dict(outcome, "outcome")
    _require_counter_keys(outcome_dict, _OUTCOME_KEYS, "outcome")
    assertion_dict = _require_dict(assertion, "assertion")
    artifacts_dict = _validate_artifacts(artifacts)

    completed = exit_code == 0 and assertion_dict.get("passed") is True

    return {
        "config": config,
        "completed": completed,
        "exit_code": exit_code,
        "wall_time_s": wall_time_s,
        "waited_for_input": waited_for_input,
        "changed_files": changed_files,
        "tool_calls": tool_calls_dict,
        "tokens": {
            "input": outcome_dict["input"],
            "output": outcome_dict["output"],
            "totalTokens": outcome_dict["totalTokens"],
        },
        "cost_total": outcome_dict["cost_total"],
        "artifacts": artifacts_dict,
        "assertion": assertion_dict,
        "model": model,
        "timestamp": timestamp,
    }


def _format_bool_cell(value: Any) -> str:
    """Render a boolean cell as ``yes``/``no`` - plain ASCII, so the table
    survives PR descriptions and README viewers that mangle emoji or
    Python literals."""
    return "yes" if value else "no"


def _format_tool_calls_cell(tool_calls: Dict[str, Any]) -> str:
    """Render the tool-call counters; the orphaned counter is appended only
    when non-zero, so a clean run does not advertise it."""
    text = (
        "{} attempted / {} ok / {} failed / {} unfinished".format(
            tool_calls["attempted"],
            tool_calls["succeeded"],
            tool_calls["failed"],
            tool_calls["unfinished"],
        )
    )
    if tool_calls["orphaned"]:
        text += " / {} orphaned".format(tool_calls["orphaned"])
    return text


def _verdict_line(completed: int, total: int) -> str:
    """The verdict: NO-GO when nothing completed, GO when everything did,
    PARTIAL when some did - a partial bake-off is not a clean GO."""
    if completed == total:
        return "GO ({} of {} completed)".format(completed, total)
    if completed == 0:
        return "NO-GO"
    return "PARTIAL ({} of {} completed)".format(completed, total)


def render_table(records: List[dict]) -> str:
    """Render the go/no-go Markdown table (behaviour 12).

    One row per record in **input order** (the evidence is in run order -
    re-sorting would silently reorder it), columns ``config`` /
    ``Completed`` / ``Tool calls`` / ``Wall time`` / ``Tokens`` /
    ``Waited for input``, followed by a final verdict line:

    - ``Completed`` and ``Waited for input`` render as ``yes``/``no``;
    - ``Tool calls`` renders the four standard counters, appending the
      orphaned counter only when it is non-zero;
    - ``Wall time`` renders ``str(wall_time_s) + "s"``, no rounding;
    - ``Tokens`` renders ``tokens["totalTokens"]`` as a bare integer -
      the total, not the input/output split, because the go/no-go
      decision compares runs;
    - the verdict is ``NO-GO`` when no record has ``completed`` True,
      ``GO (n of n completed)`` when all did, ``PARTIAL (n of m
      completed)`` when some but not all.

    An empty ``records`` list renders the header, the separator and a
    single ``no runs recorded`` row - never an empty string.

    This function is a read-only view: it reads the records, never
    mutates them, so the caller can re-render or re-serialize the same
    list afterwards.

    Raises:
        RecordError: a ``config`` value appears more than once, naming
            the duplicated value so the caller knows which record to fix.
    """
    seen: Set[str] = set()
    for record in records:
        config = record["config"]
        if config in seen:
            raise RecordError(
                "duplicate config value {!r}: the table has one row per "
                "configuration".format(config)
            )
        seen.add(config)

    lines = [
        "| config | Completed | Tool calls | Wall time | Tokens | "
        "Waited for input |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not records:
        lines.append("| no runs recorded |")
    else:
        for record in records:
            lines.append(
                "| {} | {} | {} | {}s | {} | {} |".format(
                    record["config"],
                    _format_bool_cell(record["completed"]),
                    _format_tool_calls_cell(record["tool_calls"]),
                    record["wall_time_s"],
                    record["tokens"]["totalTokens"],
                    _format_bool_cell(record["waited_for_input"]),
                )
            )
    completed = sum(1 for record in records if record["completed"])
    lines.append(_verdict_line(completed, len(records)))
    return "\n".join(lines)
