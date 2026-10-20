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

This cycle owns ``build``: it validates that every dimension arrived (a
missing one raises ``RecordError`` naming the field, so a half-recorded run
cannot become a verdict) and assembles the record. The go/no-go table
(``render_table``, behaviour 12) lands in a later cycle in this same module.

Stdlib only. One exception type: ``RecordError``.
"""

from typing import Any, Dict, List, Optional, Tuple

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
