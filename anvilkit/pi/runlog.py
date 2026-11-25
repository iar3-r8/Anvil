"""Pi run ids, the run archive and the reopen renderer (``plans/pi-phase11-runlog.md``).

The concern: an unattended Pi run must stay reopenable after it ends, whether
it finished or died mid-way. This module owns what that takes - the run id and
the ``<run-id>-<role>`` session ids, the archive written under
``logs/runs/<run-id>/``, and the Markdown report that reopens it. It never
drives Pi and executes no process; it reads and writes the archive and nothing
else.

A run id is ``run-YYYYMMDD-HHMMSS-<4hex>``: a zero-padded UTC stamp plus a
4-char lowercase-hex entropy suffix, so every run is uniquely addressable.
``session_id`` derives the per-role session id ``<run-id>-<role>``
(behaviour 3): the run id crosses through verbatim and is not revalidated,
and the role must be one of ``pirole.ROLES`` or ``RunLogError`` names it
and lists the four known roles.

``new_run_id`` accepts both values explicitly (behaviour 1); when either is
omitted it is computed at call time from the module's own references -
``datetime.now(timezone.utc)`` for the stamp and ``secrets.token_hex(2)`` for
the suffix (behaviour 2) - never local time, never a counter. Those
references are module-level names exactly so callers can patch them.

``start_run`` opens a run's archive directory ``logs/runs/<run-id>/`` and
writes ``meta.json`` before anything else runs (behaviour 6): a run that
dies mid-way leaves a readable record, with ``finished_at`` null,
``outcome`` unknown and ``complete`` false. Validation of ``intake``,
``sessions`` and ``started_at`` happens before any filesystem I/O, so a
rejected run is never half-recorded. An id whose archive directory already
exists is refused before any validation or I/O (behaviour 7): a past run is
evidence and is never overwritten.

``finish_run`` marks a finished run complete (behaviour 11): it rewrites
the run's ``meta.json`` with the given ``finished_at`` and outcome and
``complete`` true, every other key preserved verbatim. ``outcome`` must be
one of the four terminals in ``FINISH_OUTCOMES`` and ``finished_at`` a
string; either violation, or a missing ``meta.json``, raises
``RunLogError`` before anything is written, so a refused call never
half-rewrites the record.

``write_stream`` (behaviour 8), ``write_diff`` (behaviour 9),
``write_commits`` (behaviour 10) and ``write_prompts`` (behaviour 11
of ``plans/pi-phase12-launch-gen.md``) keep what they were given: the
captured stream verbatim in ``<role>.jsonl`` byte-for-byte - an empty
or unparseable stream is stored unchanged, since those are the runs
worth reading; the diff text verbatim in ``diff.patch``, where an empty
diff still lands as an empty file, so "changed nothing" stays
distinguishable from "never recorded"; the commit list in
``commits.json`` via ``json.dumps``, in order; and each role document
verbatim in ``prompts/<stem>.md`` in UTF-8, no newline invented. Every
writer refuses an unknown role, an empty document mapping or a missing
run directory with ``RunLogError`` naming the offender, before any
file is created.

``open_run`` renders a completed archive as a Markdown report
(behaviour 12): the run id and stamps, the ``anvil version`` from
``meta.json``'s ``anvil_version``, the intake, one section per role
carrying the session id, the stream file path and the settled/aborted
state, tool-call counters, tokens and cost computed via ``pievents``,
then the diff and commit sections, then the prompts section naming each
archived document under ``prompts/`` by its file path in ``pirole.ROLES``
order with ``shared-agents`` and ``project`` after the roles (behaviour 13
of ``plans/pi-phase12-launch-gen.md``). Raw stream bytes and raw prompt
text are never inlined - only file paths, since a stream can hold prompts,
tool arguments and file contents. A stream that parses to zero events -
empty, truncated or not JSON - renders the pinned line ``stream
unparseable: <n> malformed lines, no readable events`` instead of the
facts, and never raises (behaviour 13). Every member is read through a
guard that treats a missing or unreadable member as absent, so a
half-written archive can never crash the renderer.

A run whose ``meta.json`` is not marked complete - the run died mid-way
and ``finish_run`` never ran - is rendered the same way and additionally
carries the exact line ``status: INCOMPLETE`` (behaviour 14); each
absent member renders its pinned wording (``no diff recorded``,
``no commits recorded``, ``no stream recorded for <role>``,
``no anvil version recorded``, ``no prompts recorded``) while
whatever did land renders unchanged. A complete run carries no
INCOMPLETE text at all. ``open_run`` never raises on such a half-written
archive; it raises ``RunLogError`` only for an unknown run id, naming the
id and the path searched (behaviour 15), so a typo is fixable without
reading the source.

Stdlib only, no process execution, and writes are confined to the run
directory it was given. One exception type: ``RunLogError``.
"""

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from anvilkit import __version__
from anvilkit.pi import pievents, pirole


class RunLogError(Exception):
    """A run id that cannot be built, or a run log that cannot be written."""


def new_run_id(
    now: Optional[datetime] = None,
    entropy: Optional[str] = None,
) -> str:
    """Return ``run-YYYYMMDD-HHMMSS-<4hex>`` for the instant ``now``.

    ``now`` must be an aware datetime in UTC; ``entropy`` must be exactly
    four lowercase hex characters. Either violation raises ``RunLogError``
    naming the offending value. When ``now`` is ``None`` it defaults to
    ``datetime.now(timezone.utc)`` and when ``entropy`` is ``None`` it
    defaults to ``secrets.token_hex(2)``, both consulted at call time via
    the module-level ``datetime`` and ``secrets`` references.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if entropy is None:
        entropy = secrets.token_hex(2)
    if now.utcoffset() is None:
        raise RunLogError(
            "now must be an aware datetime in UTC, got naive %r" % (now,)
        )
    if now.utcoffset() != timedelta(0):
        raise RunLogError(
            "now must be a UTC datetime, got %r" % (now,)
        )
    if len(entropy) != 4 or any(
        char not in "0123456789abcdef" for char in entropy
    ):
        raise RunLogError(
            "entropy must be exactly 4 lowercase hex chars, got %r"
            % (entropy,)
        )
    return "run-" + now.strftime("%Y%m%d-%H%M%S") + "-" + entropy


def session_id(run_id: str, role: str) -> str:
    """Return ``<run-id>-<role>`` for the run ``run_id``.

    The run id crosses through verbatim - it is not revalidated against
    ``new_run_id``'s format, so a syntactically valid string this module
    would never produce still gets the role appended. The role is the only
    checked input: it must be one of ``pirole.ROLES``, and any other value
    raises ``RunLogError`` naming the offending role and listing all four
    known roles.
    """
    if role not in pirole.ROLES:
        raise RunLogError(
            "unknown role %r: the known roles are %s"
            % (role, ", ".join(pirole.ROLES))
        )
    return run_id + "-" + role


def start_run(
    root: Path,
    run_id: str,
    intake: Dict[str, object],
    sessions: Dict[str, str],
    started_at: str,
) -> Path:
    """Open the archive directory for run ``run_id`` and write its ``meta.json``.

    If ``root/logs/runs/<run-id>/`` already exists the run is refused before
    any validation or I/O: ``RunLogError`` names the run id and nothing on
    disk is touched (behaviour 7 - a past run is evidence and is never
    overwritten).

    Creates ``root/logs/runs/<run-id>/`` and writes ``meta.json`` with exactly
    the eight planned keys - ``run_id``, ``started_at``, ``finished_at`` (null),
    ``intake``, ``sessions``, ``outcome`` (``"unknown"``), ``complete`` (false)
    and ``anvil_version`` (``anvilkit.__version__``, read live, never
    validated) - so a run that dies mid-way leaves a readable record. Returns
    the run directory's ``Path``.

    ``run_id`` is taken as given (it is produced by ``new_run_id``). The other
    three inputs are validated before any filesystem I/O: ``intake`` must be a
    dict with exactly the keys ``{"issue", "text"}``, ``sessions`` must be a
    dict whose keys are all in ``pirole.ROLES``, and ``started_at`` must be a
    ``str``. Any violation raises ``RunLogError`` naming the offending field
    (or role) and leaves no ``meta.json`` behind.
    """
    run_dir = root / "logs" / "runs" / run_id
    if run_dir.exists():
        raise RunLogError(
            "run %r already has an archive at %s and will not be "
            "overwritten" % (run_id, run_dir)
        )
    _validate_start_inputs(intake, sessions, started_at)
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "intake": intake,
        "sessions": sessions,
        "outcome": "unknown",
        "complete": False,
        "anvil_version": __version__,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return run_dir


def _validate_start_inputs(
    intake: object,
    sessions: object,
    started_at: object,
) -> None:
    """Check the three validated ``start_run`` inputs; raise ``RunLogError``.

    Pure validation - no filesystem I/O - so a rejected run is never
    half-recorded. Each violation names its field: ``intake`` for a missing,
    extra or non-dict intake, ``sessions`` (or the offending role) for a
    non-dict sessions map or an unknown role, and ``started_at`` for a
    non-string value.
    """
    if not isinstance(intake, dict) or set(intake.keys()) != {"issue", "text"}:
        raise RunLogError(
            "intake must be a dict with exactly the keys "
            "{'issue', 'text'}, got %r" % (intake,)
        )
    if not isinstance(sessions, dict):
        raise RunLogError(
            "sessions must be a dict of role to session id, got %r"
            % (sessions,)
        )
    for role in sessions:
        if role not in pirole.ROLES:
            raise RunLogError(
                "sessions has an unknown role %r: the known roles are %s"
                % (role, ", ".join(pirole.ROLES))
            )
    if not isinstance(started_at, str):
        raise RunLogError(
            "started_at must be a str, got %r" % (started_at,)
        )


# The four terminal outcomes a finished run can carry. ``unknown`` is the
# "we never learned" terminal - a valid finished outcome, not an
# unfinished run.
FINISH_OUTCOMES = ("shipped", "halted", "failed", "unknown")


def finish_run(run_dir: Path, outcome: str, finished_at: str) -> None:
    """Mark the run in ``run_dir`` complete by rewriting its ``meta.json``.

    Rewrites ``meta.json`` with ``finished_at`` set to the given stamp,
    ``outcome`` set to the given outcome and ``complete`` set to true,
    every other key preserved verbatim - a finished run keeps the record
    ``start_run`` opened for it, with exactly those three fields changed.

    ``outcome`` must be one of the four terminals in ``FINISH_OUTCOMES``
    and ``finished_at`` a ``str``; either violation raises ``RunLogError``
    naming the offending value (for an outcome, also listing all four
    known outcomes), and ``meta.json`` must exist and be readable,
    otherwise ``RunLogError`` names its path. All validation happens
    before any write, so a refused call leaves the record unchanged.
    """
    if outcome not in FINISH_OUTCOMES:
        raise RunLogError(
            "unknown outcome %r: the known outcomes are %s"
            % (outcome, ", ".join(FINISH_OUTCOMES))
        )
    if not isinstance(finished_at, str):
        raise RunLogError(
            "finished_at must be a str, got %r" % (finished_at,)
        )
    meta_path = run_dir / "meta.json"
    if not meta_path.is_file():
        raise RunLogError(
            "meta.json does not exist or is not readable: %s" % (meta_path,)
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["finished_at"] = finished_at
    meta["outcome"] = outcome
    meta["complete"] = True
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def write_stream(run_dir: Path, role: str, text: str) -> None:
    """Write the role's captured stream to ``<role>.jsonl`` byte-for-byte.

    ``text`` is the driver's captured ``result["stdout"]`` and is written
    verbatim in UTF-8 with no newline added: an empty stream writes an empty
    file, and an unparseable stream is kept unchanged - the captured bytes
    are data, so this module never parses or rewrites a stream. ``role``
    must be one of ``pirole.ROLES`` (otherwise ``RunLogError`` names the
    role and no file is created), and ``run_dir`` must exist as a directory
    (otherwise ``RunLogError`` names the path).
    """
    if role not in pirole.ROLES:
        raise RunLogError(
            "unknown role %r: the known roles are %s"
            % (role, ", ".join(pirole.ROLES))
        )
    _require_run_dir(run_dir)
    (run_dir / (role + ".jsonl")).write_text(text, encoding="utf-8")


def write_diff(run_dir: Path, text: str) -> None:
    """Write the run's diff text to ``diff.patch`` verbatim.

    An empty diff still writes an empty file, since "changed nothing" is
    data - a run that changed nothing stays distinguishable from a run
    whose diff was never recorded. A missing run directory raises
    ``RunLogError`` naming the path, the same guard as ``write_stream``.
    """
    _require_run_dir(run_dir)
    (run_dir / "diff.patch").write_text(text, encoding="utf-8")


def write_commits(run_dir: Path, commits: List[Dict[str, str]]) -> None:
    """Write the run's commit list to ``commits.json`` via ``json.dumps``.

    ``commits`` must be a list whose entries are each a dict with exactly
    the keys ``{"sha", "subject"}``, in order; an entry with a missing or
    extra key raises ``RunLogError`` naming the index of the offending
    entry. An empty list writes ``[]``. A missing run directory raises
    ``RunLogError`` naming the path.
    """
    if not isinstance(commits, list):
        raise RunLogError(
            "commits must be a list of {'sha', 'subject'} dicts, got %r"
            % (commits,)
        )
    for index, entry in enumerate(commits):
        if not isinstance(entry, dict) or set(entry.keys()) != {
            "sha",
            "subject",
        }:
            raise RunLogError(
                "commits entry at index %d must be a dict with exactly the "
                "keys {'sha', 'subject'}, got %r" % (index, entry)
            )
    _require_run_dir(run_dir)
    (run_dir / "commits.json").write_text(json.dumps(commits), encoding="utf-8")


def write_prompts(run_dir: Path, documents: Dict[str, str]) -> None:
    """Write the run's role documents to ``prompts/<stem>.md`` verbatim.

    Each entry of ``documents`` is written to ``<run-dir>/prompts/<stem>.md``
    byte-for-byte in UTF-8 with no newline invented, matching the write
    discipline of ``write_stream`` and the ``meta.json`` writer. An empty
    mapping raises ``RunLogError`` naming the mapping, and a missing run
    directory raises ``RunLogError`` naming the path - both before any
    file or directory is created, so the ``prompts/`` directory does not
    exist afterwards.
    """
    if not isinstance(documents, dict) or not documents:
        raise RunLogError(
            "documents must be a non-empty stem-to-text mapping, got %r"
            % (documents,)
        )
    _require_run_dir(run_dir)
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for stem, text in documents.items():
        (prompts_dir / (stem + ".md")).write_text(text, encoding="utf-8")


def _require_run_dir(run_dir: Path) -> None:
    """Raise ``RunLogError`` naming the path if ``run_dir`` is not a directory.

    The shared missing-run-directory guard for the archive writers - the
    same guard as behaviour 8, pinned the same way by every writer.
    """
    if not run_dir.is_dir():
        raise RunLogError(
            "run directory does not exist or is not a directory: %s"
            % (run_dir,)
        )


def open_run(run_id: str, root: Path) -> str:
    """Return the Markdown report of the run ``run_id`` under ``root``.

    Reads the archive at ``root/logs/runs/<run-id>/`` - ``meta.json``, one
    ``<role>.jsonl`` per role present in ``meta.json``'s sessions map
    (in ``pirole.ROLES`` order), ``diff.patch``, ``commits.json`` and the
    archived documents under ``prompts/`` - and renders them as a Markdown
    report: the run id and both stamps verbatim, the ``anvil version`` from
    ``meta.json``'s ``anvil_version``, the intake, one section per role
    carrying the session id, the stream file path and the settled/aborted
    state, tool-call counters, tokens and cost computed via ``pievents``,
    then the diff and commit sections in ``commits.json`` order, then the
    prompts section naming each archived document by its file path.

    Raw stream bytes are never inlined - only the stream's file path, since
    a stream can hold prompts, tool arguments and file contents. Every
    member is read individually through ``_read_text_if_present`` /
    ``_read_json_if_present``: a missing or unreadable member is rendered
    as its absence, never as a crash, so a half-written archive stays
    reopenable. On well-formed input no error is raised.

    Completeness is read from ``meta.json``'s ``complete`` flag as written
    by ``start_run`` and ``finish_run`` in this module. A run that is not
    complete - the flag false, or ``meta.json`` itself absent or invalid -
    is half-written: the report carries the exact whole line
    ``status: INCOMPLETE`` next to the stamps, and each absent member
    renders its pinned absence wording (``no diff recorded``,
    ``no commits recorded``, ``no stream recorded for <role>``,
    ``no anvil version recorded``, ``no prompts recorded``) while
    whatever did land renders unchanged. A complete run carries no
    INCOMPLETE text at all. ``open_run`` never raises on a half-written
    archive: a run that died mid-way is still reopenable. An unknown run
    id - no directory at the archive path - raises ``RunLogError`` naming
    the run id and the path searched before anything is rendered
    (behaviour 15): a typo is fixable without reading the source.
    """
    run_dir = root / "logs" / "runs" / run_id
    if not run_dir.is_dir():
        # First failure mode: an unknown id must never fall through to the
        # half-written rendering. The message carries the run id verbatim,
        # the archive path searched, and its parent, so a typo in either
        # is fixable without reading the source.
        raise RunLogError(
            "run %r has no archive at %s, searched under %s"
            % (run_id, run_dir, run_dir.parent)
        )
    meta = _read_json_if_present(run_dir / "meta.json")
    complete = isinstance(meta, dict) and meta.get("complete") is True

    lines: List[str] = ["# Run report: " + run_id, ""]
    if isinstance(meta, dict):
        lines.append("started_at: %s" % (meta.get("started_at"),))
        lines.append("finished_at: %s" % (meta.get("finished_at"),))
        if not complete:
            # The half-written mark: the exact whole line, in the report's
            # key: value style, reserved for runs finish_run never marked
            # complete. A complete run carries no INCOMPLETE text at all.
            lines.append("status: INCOMPLETE")
        version = meta.get("anvil_version")
        if version is None and not complete:
            # The version never landed: the pinned absence wording, in
            # the same absent-safe style as the other members.
            lines.append("no anvil version recorded")
        elif version is not None:
            # The archive's own stored value, never a re-read of the
            # running module: the report must reopen a past run.
            lines.append("anvil version: %s" % (version,))
        lines.append("")
        intake = meta.get("intake")
        lines.extend(_intake_section(intake))
        sessions = meta.get("sessions")
        if isinstance(sessions, dict):
            for role in pirole.ROLES:
                if role in sessions:
                    lines.extend(
                        _role_section(role, sessions[role], run_dir, complete)
                    )
    lines.extend(_diff_section(run_dir, complete))
    lines.extend(_commits_section(run_dir, complete))
    lines.extend(_prompts_section(run_dir, complete))
    return "\n".join(lines) + "\n"


def _intake_section(intake: object) -> List[str]:
    """Render the intake section from ``meta.json``'s ``intake`` dict.

    A non-dict intake renders as an empty intake: the numbers and text are
    simply absent, never a crash.
    """
    lines = ["## Intake", ""]
    issue = intake.get("issue") if isinstance(intake, dict) else None
    text = intake.get("text") if isinstance(intake, dict) else None
    lines.append("issue: %s" % (issue,))
    lines.append("text: %s" % (text,))
    lines.append("")
    return lines


def _role_section(
    role: str, session_id: object, run_dir: Path, complete: bool
) -> List[str]:
    """Render one role's section: session id, stream path and pievents facts.

    The stream file is referenced by its absolute path only; its bytes are
    parsed via ``pievents`` for the settled/aborted state, the tool-call
    counters, the tokens and the cost. A missing or unreadable stream in a
    half-written archive - one ``open_run`` marked INCOMPLETE - renders the
    pinned line ``no stream recorded for <role>`` instead of the stream
    path and facts, so a run that died mid-way never crashes the renderer.

    A stream that parses to zero events - whatever its malformed-line
    count, so an empty stream is unparseable with a count of zero - is
    unparseable: instead of the facts the section renders the pinned
    line ``stream unparseable: <n> malformed lines, no readable events``
    with ``<n>`` from ``pievents.parse``'s ``malformed_lines`` (behaviour
    13). A stream with at least one event is never marked unparseable,
    even when it also carries malformed lines - the marker is the
    zero-events state, not the malformed-lines state. A broken stream
    never raises - the broken run is the one most worth reopening.
    """
    lines = ["## Role: " + role, ""]
    lines.append("session id: %s" % (session_id,))
    stream_path = run_dir / (role + ".jsonl")
    lines.append("stream: %s" % (stream_path,))
    text = _read_text_if_present(stream_path)
    if text is None and not complete:
        # The stream never landed: the pinned absence wording, not the
        # stream path - a half-written archive's missing stream is data.
        lines.append("no stream recorded for " + role)
    if text is not None:
        parsed = pievents.parse(text)
        events = parsed["events"]
        if not events:
            lines.append(
                "stream unparseable: %d malformed lines, no readable events"
                % (parsed["malformed_lines"],)
            )
        else:
            session_info = pievents.session(events)
            if session_info["session_id"] is not None:
                lines.append(
                    "stream session: %s" % (session_info["session_id"],)
                )
            outcome = pievents.outcome(events)
            calls = pievents.tool_calls(events)
            lines.append("settled: %s" % (outcome["settled"],))
            lines.append("aborted: %s" % (outcome["aborted"],))
            lines.append(
                "tool calls: attempted=%d succeeded=%d failed=%d "
                "unfinished=%d orphaned=%d"
                % (
                    calls["attempted"],
                    calls["succeeded"],
                    calls["failed"],
                    calls["unfinished"],
                    calls["orphaned"],
                )
            )
            lines.append(
                "tokens: input=%d output=%d total=%d"
                % (
                    outcome["input"],
                    outcome["output"],
                    outcome["totalTokens"],
                )
            )
            lines.append("cost: %s" % (outcome["cost_total"],))
    lines.append("")
    return lines


def _diff_section(run_dir: Path, complete: bool) -> List[str]:
    """Render the diff section from ``diff.patch``, absent-safe.

    The diff is ours to show, so its text is inlined verbatim in a fenced
    code block; an absent file in a half-written archive - one
    ``open_run`` marked INCOMPLETE - renders the pinned line
    ``no diff recorded``.
    """
    lines = ["## Diff", ""]
    diff_text = _read_text_if_present(run_dir / "diff.patch")
    if diff_text is None and not complete:
        # The diff never landed: the pinned absence wording.
        lines.append("no diff recorded")
    if diff_text is not None:
        lines.append("```")
        lines.append(diff_text)
        lines.append("```")
    lines.append("")
    return lines


def _commits_section(run_dir: Path, complete: bool) -> List[str]:
    """Render the commits section from ``commits.json``, in file order.

    Each entry renders as ``- <sha> <subject>`` in the order
    ``commits.json`` holds them; an absent file in a half-written archive
    - one ``open_run`` marked INCOMPLETE - renders the pinned line
    ``no commits recorded``.
    """
    lines = ["## Commits", ""]
    commits = _read_json_if_present(run_dir / "commits.json")
    if commits is None and not complete:
        # The commits never landed: the pinned absence wording.
        lines.append("no commits recorded")
    if isinstance(commits, list):
        for commit in commits:
            if isinstance(commit, dict):
                lines.append(
                    "- %s %s" % (commit.get("sha"), commit.get("subject"))
                )
    lines.append("")
    return lines


def _prompts_section(run_dir: Path, complete: bool) -> List[str]:
    """Render the prompts section from the ``prompts/`` directory.

    Each archived document renders as ``prompt: <run-dir>/prompts/<stem>.md``
    - the file's path only, never its contents, in the same style as the
    report's ``stream:`` lines. The report order is fixed, whatever the
    write order was: the stems in ``pirole.ROLES`` order first, then
    ``shared-agents`` and ``project``, then any other stems alphabetically,
    so the same archive reopens the same way. An absent or empty
    ``prompts/`` directory in a half-written archive - one ``open_run``
    marked INCOMPLETE - renders the pinned line ``no prompts recorded``.
    """
    lines = ["## Prompts", ""]
    prompts_dir = run_dir / "prompts"
    stems: List[str] = []
    if prompts_dir.is_dir():
        try:
            stems = sorted(
                path.stem for path in prompts_dir.iterdir() if path.is_file()
            )
        except OSError:
            stems = []
    ordered = [stem for stem in pirole.ROLES if stem in stems]
    for stem in ("shared-agents", "project"):
        if stem in stems:
            ordered.append(stem)
    ordered.extend(
        stem for stem in stems if stem not in pirole.ROLES and stem not in ordered
    )
    if not ordered and not complete:
        # The prompts never landed: the pinned absence wording.
        lines.append("no prompts recorded")
    for stem in ordered:
        lines.append("prompt: %s" % (prompts_dir / (stem + ".md"),))
    lines.append("")
    return lines


def _read_text_if_present(path: Path) -> Optional[str]:
    """Read ``path`` as UTF-8 text, or ``None`` when absent or unreadable.

    The absence guard shared by ``open_run``'s member reads: a missing or
    unreadable member is data (a half-written archive), never a crash.
    """
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_json_if_present(path: Path) -> Optional[Any]:
    """Read and parse ``path`` as JSON, or ``None`` when absent or invalid.

    The JSON counterpart of ``_read_text_if_present``: a missing,
    unreadable or non-JSON member is rendered as absent, never a crash.
    """
    text = _read_text_if_present(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None
