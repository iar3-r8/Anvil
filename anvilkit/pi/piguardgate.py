"""The setup-repo guard gate: the branch and token findings, the blocked-gate
follow-ups (free plan, CODEOWNERS, ruleset and token recipe) and the sectioned
report.

The guard-gate flow moved here verbatim from ``anvilkit.cli``
(plans/cli-segmentation.md behaviour 4): the public API drops the leading
underscore and the CLI calls it qualified (``piguardgate.guard_gate(...)``).
The import direction stays one-way - no runtime import of ``cli``, only the
TYPE_CHECKING-guarded ``Context`` annotation.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

import typer

from .. import credentials, env, prompts
from ..cliexit import EXIT_GUARDS_BLOCKED
from ..credentials import GITHUB_TOKEN_ENV
from . import picodeowners, piguard, pitokenrecipe, piruleset
from .piruleset import RulesetError

if TYPE_CHECKING:  # typing only: never imported at runtime, so the import
    # direction stays one-way (no family module imports cli)
    from ..cli import Context


def guard_gate(
    shared: "Context",
    path: str,
    token_flag: Optional[str],
    no_github: bool,
) -> Tuple[str, Optional[Tuple[str, str]]]:
    """Resolve the GitHub token and run the guard gate on ``path``; a
    blocked gate exits 9 without provisioning (behaviours 6, 7, 8 and 11)."""
    token = credentials.resolve_github_token(shared, token_flag, no_github)
    shared.echo("")
    # The guard gate: after the token (the gate needs it) and before the
    # frontier/oxylabs prompts, so a blocked run asks no question it will
    # then discard. --no-github skips it entirely: with no GitHub there is
    # nothing to gate (plans/setup-repo-guards.md behaviours 4 and 10).
    # None unless the gate ran: the profile record (behaviour 14) reuses
    # this identity rather than re-resolving it.
    repository: Optional[Tuple[str, str]] = None
    if not no_github:
        branch_findings, token_findings, repository = collect_guard_findings(
            Path(path), token, "main"
        )
        # Behaviour 11: the report prints whenever ANY finding has
        # status warn or fail - computed over the branch + token
        # findings together, the same combined list the verdict and
        # the renderers see - not only when the gate blocks, so a
        # proceeding gate shows why the warn stands. The condition
        # is status-only, piguard.render_fixes' own selection rule,
        # and NEVER includes skipped: a clean gate of only
        # passed/skipped findings prints nothing, as today (a plain
        # target with no git origin is all-skipped).
        if any(
            finding.get("status") in ("warn", "fail")
            for finding in branch_findings + token_findings
        ):
            shared.echo("")
            # Behaviour 6: the sectioned report, the same blocks
            # verify-guards prints - never re-derived. The findings
            # carry no token value, so nothing secret is echoed.
            echo_guard_report(shared, branch_findings, token_findings)
        if piguard.gate_verdict(branch_findings + token_findings) == "blocked":
            free_plan_followup(
                shared, branch_findings, repository, "main", Path(path)
            )
            shared.echo("")
            remediation = piguard.gate_remediation(
                branch_findings, token_findings
            )
            # Behaviour 7: the gate prepares the fix a junior can
            # follow - the importable ruleset - after the report and
            # before the final exit. The run still ends blocked; the
            # prepared fix never masks the block.
            if remediation["needs_ruleset"]:
                prepare_gate_ruleset(shared, Path(path))
                shared.echo("")
            # Behaviour 8: the gate prints the token fix a junior
            # can follow - the pre-filled creation URL and the
            # ordered steps - after the ruleset preparation (branch
            # rules first, then the token fix) and before the final
            # exit. Only a bad token (a token finding with status
            # fail) earns the recipe (the warn asymmetry). The URL
            # carries no token value, so nothing secret is echoed.
            # ``repository`` is only None when no repository could be
            # resolved, in which case the token probes never ran, so
            # the guard is defensive and unreachable.
            if remediation["needs_token_recipe"] and repository is not None:
                prepare_gate_token_recipe(shared, repository)
                shared.echo("")
            shared.echo(
                "⛔ Fix the branch rules and token scope above, then "
                "re-run setup-repo."
            )
            raise typer.Exit(EXIT_GUARDS_BLOCKED)
    return token, repository


def report_guards(shared: "Context") -> None:
    """The Guards section: the piguard findings for the project's own repository.

    Runs the same guard flow verify-guards uses, but always against this
    project's directory, and reports rather than exits: the branch-rule
    findings print first, then the token-scope findings from the same
    ``check_token_all`` seam, doctor's exit status is unchanged by any
    finding, and it still writes nothing.
    """
    shared.echo("")
    shared.echo("Guards")

    token = env.get(shared.env_path, GITHUB_TOKEN_ENV)

    # The same single flow verify-guards runs, with doctor's noun; a probe
    # added to _collect_guard_findings reaches doctor with no edit here.
    findings, token_findings, _repository = collect_guard_findings(
        shared.root, token, "main", noun="project"
    )

    # Behaviour 19: the findings print as wrapped blocks - a status-prefixed
    # headline, the finding's substance at 80 columns, and an indented fix:/
    # see: line - under a section header per source, so branch and token
    # findings no longer run together as unbroken lines.
    echo_guard_report(shared, findings, token_findings)


def ask_free_plan(
    shared: "Context",
    findings: List[Dict[str, Any]],
    asker: Optional[Callable[..., bool]] = None,
) -> bool:
    """Ask the free-plan question once when a file_paths warn is present
    (behaviour 4 of plans/file-path-interactive-free-plan.md): one
    ``prompts.confirm`` with default False whose text asks whether the plan
    offers "Restrict file paths" - the positive form, re-asked after the
    double negative read as confusing (behaviour 9): the question is
    positive and the caller inverts - a ``no`` answer means the plan lacks
    the option, which is exactly when the walkthrough applies. The asker is
    injectable for tests. ``shared`` is unused here: the gating
    (non-interactive / ``assume_yes`` / ``dry_run``) and the printing happen
    in the caller, ``_free_plan_followup``."""
    if asker is None:
        asker = prompts.confirm
    if not picodeowners.wants_walkthrough(findings):
        return False
    # Behaviour 10 (plans/file-path-codeowners-interactive.md): the question
    # names where the option lives, on its OWN line - the near-exact
    # parenthetical from the saved rulesets page. The option sits under
    # "Push protections" of a push ruleset, NOT under "Restrictions", so no
    # section name is claimed beyond the UI path and the ruleset it lands in.
    return asker(
        'Does your GitHub plan offer "Restrict file paths" in the ruleset UI?\n'
        "(Settings > Rulesets > Rulesets, then your main branch ruleset)",
        default=False,
    )


def free_plan_followup(
    shared: "Context",
    branch_findings: List[Dict[str, Any]],
    repository: Optional[Tuple[str, str]],
    branch: str,
    target: Path,
) -> None:
    """The free-plan follow-up, printed after the guard report at the two
    call sites that prompt (behaviour 5 of
    plans/file-path-interactive-free-plan.md; doctor reports and never
    prompts, so it calls this nowhere).

    Gated on a ``file_paths`` warn (behaviour 3's predicate) and on a
    resolved repository: with neither, or an unresolvable repository, the
    report is byte-identical to before the wiring - no line, no prompt,
    no walkthrough (behaviour 6's error clause, landed early because the
    follow-up needs the repository anyway).

    Non-interactive, ``--yes`` and ``--dry-run`` runs never ask: they print
    exactly one line, then return - no prompt, no stdin read, and the exit
    code is untouched (behaviour 5). The line is a report line, one
    sentence, built here, not in a module - and it is unconditional: the
    file-present skip branches are gone (behaviour 1 of
    plans/file-path-fallback-file-only.md), so a file at the path prints
    the same free-plan line as an absent one.

    An interactive run asks the behaviour-4 unit exactly once: the question
    is positive (behaviour 9) and the caller inverts - a ``no`` answer means
    the plan lacks the option, so it prints the six-step walkthrough
    (behaviour 6) built by ``picodeowners`` from the resolved repository
    and the checked ``branch`` - never re-derived here - after the
    report's "To fix" section and bypass note, then ends in the
    interactive CODEOWNERS flow (behaviour 20), the file present or
    not: the file-present skip branches are gone (behaviour 1 of
    plans/file-path-fallback-file-only.md), and it is safe because the
    clobber guard is the write seam's ``CodeownersError``, never a skip
    - and once the marker is the file alone (that plan's behaviour 2), a
    file-present run never reaches this follow-up at all
    (``wants_walkthrough`` is False). A ``yes`` answer keeps the
    output byte-identical - no confirmation line (behaviour 7's polarity
    under the positive question): the plan offers the option, and the
    report's "To fix" line is the fix. A ``CodeownersError`` is
    reported as one line and never raised, so the run is never masked
    into success.
    """
    if not picodeowners.wants_walkthrough(branch_findings):
        return
    if repository is None:
        return
    if shared.dry_run or shared.assume_yes or not shared.interactive():
        # Behaviour 5: the fallback prints the free-plan line
        # unconditionally - the file-present skip branch is gone
        # (behaviour 1 of plans/file-path-fallback-file-only.md), so a
        # file at the path counts no different from an absent one.
        # No prompt, no stdin read, the exit code untouched.
        shared.echo(
            "Your plan may not offer \"Restrict file paths\" - the "
            "free-plan CODEOWNERS fix: re-run without --yes to see the "
            "walkthrough."
        )
        return
    answer = ask_free_plan(shared, branch_findings)
    if answer:
        # A 'yes' means the plan offers the option: no walkthrough (the
        # caller inverts, behaviour 9), but behaviour 10 of
        # plans/file-path-codeowners-interactive.md replaces the silent
        # return with exactly one locating line - tell the reader to tick
        # it in that ruleset and that the report's "To fix" entry names
        # the rule. One sentence, at most 80 characters.
        shared.echo(
            'Tick it in that ruleset; the "To fix" entry above names the rule.'
        )
        return
    owner, repo = repository
    try:
        body = picodeowners.codeowners_body(owner)
        steps = picodeowners.walkthrough_steps(owner, repo, branch, body)
    except picodeowners.CodeownersError as exc:
        shared.echo("could not build the walkthrough: {}".format(exc))
        return
    for step in steps:
        shared.echo(step)
    # The file-present skip is gone (behaviour 1 of
    # plans/file-path-fallback-file-only.md): a present file falls through
    # to the flow and is refused at the write seam, never at a skip.
    # Behaviour 20 (plans/file-path-codeowners-interactive.md): the no
    # branch ends in the interactive CODEOWNERS flow, using the SAME
    # default seams (``prompts.ask`` / ``prompts.confirm``) the rest of
    # the command uses - so both call sites (verify-guards, the blocked
    # setup-repo gate) reach it with no per-site wiring, and it changes
    # no exit code and never raises.
    codeowners_flow(shared, owner, repo, branch, target)


def codeowners_flow(
    shared: "Context",
    owner: str,
    repo: str,
    branch: str,
    target: Path,
    ask: Optional[Callable[..., str]] = None,
    confirm: Optional[Callable[..., bool]] = None,
) -> None:
    """The interactive CODEOWNERS follow-up for a free plan (behaviour 14
    of plans/file-path-codeowners-interactive.md): ask the owner handles,
    show the built content, confirm it.

    One ``ask`` for the handles, defaulting to the pre-filled ``@owner``
    (editable); the body ``picodeowners.codeowners_body`` builds from the
    answered handles is echoed verbatim, line by line; then one
    ``confirm`` "Use this CODEOWNERS content?" default True. A no ends the
    flow with no write and no further prompt. A ``CodeownersError`` prints
    exactly one line and ends the flow; no exception leaves the function
    and no exit code changes.

    Behaviour 15: between the body echoes and the confirm, each answered
    handle token is checked with
    ``picodeowners.self_approval_warning(token, owner)`` (behaviour 13:
    case-insensitive, ``@`` stripped, a ``/`` team handle -> None); if any
    is non-None, the first warning line and
    ``picodeowners.last_push_step()`` are echoed once each, then the flow
    continues to the confirm - the run is never blocked, and the token is
    never compared: only handle-vs-``owner``, no env lookup.

    Behaviour 18: after the content confirm passes, the flow makes the
    write offer - one more ``confirm`` "Write .github/CODEOWNERS into
    {target}?" default False. A yes writes through
    ``picodeowners.write_codeowners`` (behaviour 17's seam) and echoes
    the written path; a no echoes exactly one line saying nothing was
    written; a ``CodeownersError`` from the seam echoes exactly one line
    and lets no exception out.

    Behaviour 19: all three write outcomes - written, write-failed and
    offer-declined - fall through to one shared ending: one intro line
    saying to run the git commands yourself, then each of
    ``picodeowners.commit_commands()`` (behaviour 12) echoed in order.
    The commands print identically in all three cases, and Anvil never
    runs them; a declined CONTENT (behaviour 14) ends before the offer
    and prints none.

    ``ask``/``confirm`` are injected seams (the ``_ask_free_plan``
    precedent) defaulting to ``prompts.ask``/``prompts.confirm``.
    ``branch`` names the branch the commit step lands on - behaviour 20
    added it to the intro line.
    """
    if ask is None:
        ask = prompts.ask
    if confirm is None:
        confirm = prompts.confirm
    handles = ask("CODEOWNERS owner handle(s), space-separated:", default="@" + owner)
    try:
        body = picodeowners.codeowners_body(handles)
    except picodeowners.CodeownersError as exc:
        shared.echo("could not build the CODEOWNERS content: {}".format(exc))
        return
    for line in body.splitlines():
        shared.echo(line)
    for token in handles.split():
        warning = picodeowners.self_approval_warning(token, owner)
        if warning is not None:
            shared.echo(warning)
            shared.echo(picodeowners.last_push_step())
            break
    if not confirm("Use this CODEOWNERS content?", default=True):
        return
    # behaviour 18: the write offer - explicit, default no.
    if not confirm(
        "Write .github/CODEOWNERS into {}?".format(target), default=False
    ):
        shared.echo(
            "Nothing written: the offer was declined; .github/CODEOWNERS "
            "is not written."
        )
    else:
        try:
            path = picodeowners.codeowners_path(target)
            written = picodeowners.write_codeowners(path, body)
            shared.echo(str(written))
        except picodeowners.CodeownersError as exc:
            shared.echo("could not write .github/CODEOWNERS: {}".format(exc))
    # behaviour 19: the commands always print - after the written,
    # failed and declined outcomes alike; Anvil never runs them.
    # Behaviour 20: the intro line names the branch the commit lands on.
    shared.echo(
        "Run these yourself in the target repository (branch {}):".format(
            branch
        )
    )
    for command in picodeowners.commit_commands():
        shared.echo(command)


def echo_guard_report(
    shared: "Context",
    branch_findings: List[Dict[str, Any]],
    token_findings: List[Dict[str, Any]],
) -> None:
    """The sectioned guards report: a "Branch rules" header, each branch
    finding as a wrapped block, a "Token scope" header, each token finding
    the same way - one blank line between blocks.

    The blocks come from ``piguard.render_finding_block`` - the behaviour-19
    blocks reused, never re-derived, so no line exceeds 80 characters.
    The report ends with the numbered "To fix" section - the mitigations of
    every warn and fail finding across BOTH sections in one sequence, from
    ``piguard.render_fixes`` - printed only when such a finding exists, and
    then always with ``piguard.BYPASS_NOTE`` as the final line, so the
    bypass caveat survives exactly once per report (behaviour 9 of
    plans/guard-finding-compact.md).
    verify-guards, doctor's Guards section and the blocked setup-repo gate
    all print through this, so the report shape cannot drift between them
    (plans/setup-repo-guards.md behaviour 6).
    """
    shared.echo("Branch rules")
    for index, finding in enumerate(branch_findings):
        if index:
            shared.echo("")
        for line in piguard.render_finding_block(finding):
            shared.echo(line)

    shared.echo("")
    shared.echo("Token scope")
    for index, finding in enumerate(token_findings):
        if index:
            shared.echo("")
        for line in piguard.render_finding_block(finding):
            shared.echo(line)

    shared.echo("")
    fixes = piguard.render_fixes(branch_findings + token_findings, width=80)
    if fixes:
        for line in fixes:
            shared.echo(line)
        shared.echo("")
    shared.echo(piguard.BYPASS_NOTE)


def prepare_gate_ruleset(shared: "Context", target: Path) -> None:
    """Prepare the importable ruleset a blocked gate reports on.

    Writes ``target/.github-ruleset.json`` through the
    ``piruleset.write_ruleset`` seam (the five-rule ruleset, rendered,
    ``force=False``), then prints the written path and the manual import
    steps, so a junior sees exactly what to import next.

    An existing file is never overwritten: it is named as already
    prepared and left untouched (``force`` is never passed true), but
    the import steps still follow, since printing is not writing. A
    ``RulesetError`` is reported, naming the path, and never raised -
    the run still ends blocked, never masked into success. This
    function raises no other exception type.

    Under ``--dry-run`` nothing is written and no existing file is
    claimed: the path the run would write is announced in the file's
    ``would write`` phrasing, and the import steps still follow, since
    printing is not writing (plans/setup-repo-guards.md behaviour 12).
    """
    path = piruleset.default_output_path(target)
    if shared.dry_run:
        shared.echo("would write {}:".format(path))
        for line in piruleset.import_steps(None, path):
            shared.echo("  - {}".format(line))
        return
    if path.exists():
        shared.echo(
            "the ruleset is already prepared at {} - import it as "
            "below".format(path)
        )
        for line in piruleset.import_steps(None, path):
            shared.echo("  - {}".format(line))
        return
    try:
        written = piruleset.write_ruleset(
            path,
            piruleset.render_ruleset_json(piruleset.build_ruleset()),
            force=False,
        )
    except RulesetError as exc:
        shared.echo(
            "could not write the ruleset to {}: {}".format(path, exc)
        )
        return
    shared.echo("Wrote the ruleset to {}:".format(written))
    for line in piruleset.import_steps(None, written):
        shared.echo("  - {}".format(line))


def prepare_gate_token_recipe(
    shared: "Context", repository: Tuple[str, str]
) -> None:
    """Print the token fix a blocked gate reports on.

    The pre-filled fine-grained creation URL as its own line, then the
    ordered UI steps from ``pitokenrecipe.recipe_steps``, built by the
    module and never re-derived. The URL carries no token value (the token
    text is shown by GitHub's UI once and never passes through Anvil), so
    nothing secret is echoed.

    A ``TokenRecipeError`` is reported, naming the failure, and never
    raised - the run still ends blocked, never masked into success. This
    function raises no other exception type.
    """
    owner, repo = repository
    try:
        url = pitokenrecipe.build_recipe_url(owner, repo)
    except pitokenrecipe.TokenRecipeError as exc:
        shared.echo("could not build the token recipe: {}".format(exc))
        return
    shared.echo(url)
    for step in pitokenrecipe.recipe_steps(owner, repo, url):
        shared.echo(step)


def collect_guard_findings(
    target: Path,
    token: str,
    branch: str,
    other_repo: Optional[str] = None,
    noun: str = "target",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[Tuple[str, str]]]:
    """The shared guard flow: resolve -> fetch -> check_all -> check_token_all.

    verify-guards and doctor's Guards section each ran this flow inline; this
    is the single implementation. Returns ``(branch_findings, token_findings,
    repository)``: the branch findings are ``check_all`` of the fetched rules,
    or ``skipped_findings`` of the reason the repository could not be resolved
    or the fetch failed, and the token findings are ``check_token_all``
    whenever the repository resolves - even when the fetch failed. ``noun`` is
    the word the unresolvable reason uses: "target" (verify-guards) or
    "project" (doctor).

    Once the repository resolves, the CODEOWNERS file's presence is
    computed once - ``picodeowners.codeowners_path(target).is_file()``
    - and passed through ``check_all`` to the file_paths check as its
    fallback marker's file half (behaviour 7 of
    plans/file-path-fallback-satisfied.md). That is the same predicate
    the #109 skip uses, so the skip and the verdict cannot disagree. It
    is computed after the repository check, so an unresolvable
    repository yields ``skipped_findings`` before any of it.
    """
    repository = piguard.resolve_repository(target)
    if repository is None:
        reason = (
            "owner/repo could not be resolved from the origin remote of "
            "{}: the {} has no origin, or its remote is not a GitHub "
            "repository, and the identity is never guessed".format(target, noun)
        )
        branch_findings: List[Dict[str, Any]] = piguard.skipped_findings(reason)
        token_findings: List[Dict[str, Any]] = []
    else:
        owner, repo = repository
        codeowners_present = picodeowners.codeowners_path(target).is_file()
        rules, fetch_reason = piguard.fetch_branch_rules(
            owner, repo, branch, token
        )
        if rules is None:
            branch_findings = piguard.skipped_findings(fetch_reason)
        else:
            branch_findings = piguard.check_all(
                rules, codeowners_present=codeowners_present
            )
        # The token probes run whenever the repository resolves, even when the
        # branch-rules fetch failed.
        token_findings = piguard.check_token_all(
            owner, repo, token=token, other_repo=other_repo
        )
    return branch_findings, token_findings, repository
