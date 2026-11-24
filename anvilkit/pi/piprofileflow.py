"""The setup-repo profile-record flow: name resolution (no default), the
post-provisioning record and the dry-run announcement.

The profile-record flow moved here verbatim from ``anvilkit.cli``
(plans/cli-segmentation.md behaviour 7): the public API drops the leading
underscore and the CLI calls it qualified
(``piprofileflow.resolve_profile_name(...)``). This module orchestrates the
record: it reads through ``prompts.ask_required`` (the no-default seam,
behaviours 21/22) and writes through ``piprofile`` (the store I/O module,
which stays untouched). The import direction stays one-way - no runtime
import of ``cli``, only the TYPE_CHECKING-guarded ``Context`` annotation.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple

from .. import prompts
from ..cliexit import EXIT_USAGE, fail
from ..prompts import PromptError
from . import piprofile

if TYPE_CHECKING:  # typing only: never imported at runtime, so the import
    # direction stays one-way (no family module imports cli)
    from ..cli import Context


def profile_root() -> Path:
    """The profile store root: ``~/.anvil``, computed at call time.

    Computed per command rather than at import so a caller that overrides
    ``$HOME`` (the test suite does) is seen on every invocation, not pinned
    to whatever home existed when the module loaded.
    """
    return Path.home() / ".anvil"


def resolve_profile_name(shared: "Context", supplied: Optional[str]) -> str:
    """Resolve the profile name for the record (behaviour 21).

    Runs BEFORE anything is provisioned, on the path that records (the
    guard gate ran). A supplied ``--profile`` name is returned without
    prompting; a supplied name that fails the store's charset rule
    fails on the usage code - naming the allowed charset, the way the
    store module names it - before the caller may provision. With no
    flag there is NO default: the question is asked through the house
    seam, :func:`prompts.ask_required`, which asks with no default
    and re-asks until a non-empty answer arrives (behaviour 22: the
    read aborts cleanly on an exhausted stdin instead of re-prompting
    forever); an answer that fails ``piprofile.valid_name`` is echoed
    with the allowed charset named, and the question is asked again.
    ``--yes`` and non-interactive runs cannot answer a no-default
    question, so they raise :class:`PromptError` naming
    ``--profile NAME`` as the fix before the seam is reached; so does
    an interactive run whose stdin ends before the question is
    answered, whose generic :class:`PromptError` is re-raised with
    the same fix named. The caller maps the :class:`PromptError` to
    the prompt exit code.
    """
    if supplied is not None:
        if not piprofile.valid_name(supplied):
            raise fail(
                "❌ invalid profile name {!r}: use only {}".format(
                    supplied, piprofile._ALLOWED_CHARSET
                ),
                EXIT_USAGE,
            )
        return supplied

    if shared.assume_yes or not shared.interactive():
        # No default exists, so --yes has nothing to accept and a
        # non-interactive run has no way to answer: fail on the prompt
        # code before any provisioning, naming the fix. Checked before
        # the seam so this message - not ask_required's generic one -
        # is what the run fails with.
        raise PromptError(
            "no profile name was supplied and there is no default to "
            "accept - pass --profile NAME to supply the name without "
            "prompting."
        )

    # The check above guarantees the interactive, non-yes path, so
    # ask_required's defaults are the only ones reachable here.
    prompt = "Profile name for the Anvil profile store"
    try:
        while True:
            name = prompts.ask_required(prompt)
            if piprofile.valid_name(name):
                return name
            shared.echo(
                "invalid profile name {!r}: use only {}".format(
                    name, piprofile._ALLOWED_CHARSET
                )
            )
    except PromptError:
        # ask_required's exhausted-stdin failure names the missing
        # value but not the fix; re-raise with --profile NAME named,
        # the way the --yes/non-interactive path does.
        raise PromptError(
            "{} is required but stdin provided no value. Pass "
            "--profile NAME to supply the name without prompting.".format(
                prompt
            )
        ) from None


def record_profile(
    path: str, name: str, repository: Optional[Tuple[str, str]]
) -> None:
    """Record a successful provisioning under ``name`` (behaviour 14).

    Written after ``provision.setup_repo`` succeeds, from values already
    resolved: the absolute target path, the guard gate's identity, and the
    literal branch the gate checked. The store root is ``~/.anvil`` and is
    read at call time via ``Path.home()`` so the suite can redirect ``HOME``
    without touching the real home. ``repository`` may be ``None`` when the
    identity was unresolvable; then owner and repo are recorded as null
    rather than guessed. A ``ProfileError`` (for instance a name collision
    at a different path) is left to escape: ``run()`` maps it to
    ``EXIT_CONFIG``, so a failed record is never silently swallowed after
    a success.
    """
    owner, repo = repository if repository is not None else (None, None)
    piprofile.save_profile(
        root=Path.home() / ".anvil",
        name=name,
        path=path,
        owner=owner,
        repo=repo,
        base="main",
        project={},
    )


def announce_or_record_profile(
    shared: "Context",
    path: str,
    profile_name: str,
    repository: Optional[Tuple[str, str]],
) -> None:
    """Announce (dry-run) or write the profile record after a successful
    provisioning (behaviours 14 and 16)."""
    # Behaviour 14: the record is written AFTER a successful provisioning,
    # from values already resolved - the gate's identity, never re-resolved.
    # A skipped gate (--no-github) has no identity to record, so the record
    # runs only when the gate ran; the name was resolved and validated
    # before provisioning (behaviour 15), so it is None exactly when the
    # gate did not run. A gate that ran but could not resolve the identity
    # still records - with owner/repo null rather than a guessed identity.
    # Behaviour 16: under --dry-run the record is only NAMED, never written -
    # the store path is computed at call time (Path.home()), so an overridden
    # HOME names the location the operator would see. Only key names and
    # facts are echoed; a token value never appears.
    if shared.dry_run:
        owner, repo = (
            repository if repository is not None else (None, None)
        )
        shared.echo(
            "would store profile {!r} in {} - path: {}, owner: {}, "
            "repo: {}, base: {}, token_env: {}".format(
                profile_name,
                Path.home() / ".anvil" / "profiles.yaml",
                os.path.abspath(path),
                owner,
                repo,
                "main",
                piprofile.token_env_for(profile_name),
            )
        )
    else:
        record_profile(path, profile_name, repository)
