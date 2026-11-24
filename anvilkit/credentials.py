"""The setup-repo credential resolution: the GitHub token, the Oxylabs pair and the Anthropic frontier choice, each prompted or bypassable, keys persisted to .env and never echoed."""

from typing import TYPE_CHECKING, Optional, Tuple

from . import config, env, prompts

if TYPE_CHECKING:  # typing only: never imported at runtime, so the import
    # direction stays one-way (no family module imports cli)
    from .cli import Context

_UNSET_API_KEY = "to set"

ANTHROPIC_KEY_ENV = "ANTHROPIC_API_KEY"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"


def resolve_github_token(
    shared: "Context", token: Optional[str], no_github: bool
) -> str:
    """Decide the GitHub token."""
    if no_github:
        return ""

    if token is not None:
        # A flag-supplied value is authoritative; persist it so flag-less runs
        # are not prompted forever. An explicit empty string returns as-is and
        # never blanks a non-empty stored value.
        _persist_github_token(shared, token)
        return token

    # Consult the .env store before prompting: a non-empty stored token is
    # reused as-is so already-configured machines are not re-prompted. The
    # lookup sits before the --yes / non-interactive guard, matching
    # resolve_oxylabs.
    stored = env.get(shared.env_path, GITHUB_TOKEN_ENV)
    if stored:
        # The value itself is never echoed.
        shared.echo("🔑 Reusing existing GITHUB_TOKEN from .env")
        return stored

    if shared.assume_yes or not shared.interactive():
        return ""

    wants_github = prompts.confirm(
        "❓ Do you use GitHub and want to map a personal repository token for the agent?",
        default=False,
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
    )

    if not wants_github:
        shared.echo("⚠️  Skipping interactive GitHub integration token.")
        shared.echo("💡 Note: If you wish to set this up later, you must manually edit")
        shared.echo("   '.env' and populate GITHUB_TOKEN.")
        return ""

    resolved = prompts.ask_required(
        "🔑 Enter your GitHub Personal Access Token",
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
        hide_input=True,
    )
    _persist_github_token(shared, resolved)
    return resolved


def _persist_github_token(shared: "Context", token: str) -> None:
    """Store the token in .env, replacing any existing entry."""
    if not token:
        # --github-token "" reaches here via the flag path; treating an empty
        # value as a no-op is what keeps it from blanking a stored token.
        return

    if shared.dry_run:
        shared.echo("would store {} in {}".format(GITHUB_TOKEN_ENV, shared.env_path))
        return

    if env.get(shared.env_path, GITHUB_TOKEN_ENV) == token:
        return

    env.set_value(shared.env_path, GITHUB_TOKEN_ENV, token)
    # The value itself is never echoed.
    shared.echo("⚡ Token accepted and persisted to .env")


def resolve_oxylabs(
    shared: "Context",
    username: Optional[str],
    no_oxylabs: bool,
    password: Optional[str] = None,
) -> Tuple[str, str]:
    """Decide the Oxylabs credentials, returning (username, password)."""
    if no_oxylabs:
        return ("", "")

    if username is not None:
        return (username, password if password is not None else "")

    # Check .env for existing credentials.
    env_username = env.get(shared.env_path, "OXYLABS_USERNAME")
    env_password = env.get(shared.env_path, "OXYLABS_PASSWORD")
    if env_username and env_password:
        return (env_username, env_password)

    if shared.assume_yes or not shared.interactive():
        return ("", "")

    wants_oxylabs = prompts.confirm(
        "❓ Do you want to use Oxylabs web scraping for documentation lookups?\nSign up at https://dashboard.oxylabs.io/en/overview/scraper",
        default=False,
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
    )

    if not wants_oxylabs:
        shared.echo("⚠️  Skipping Oxylabs web scraping setup.")
        shared.echo("💡 Note: If you wish to set this up later, you must manually edit")
        shared.echo("   '.env' and populate OXYLABS_USERNAME and OXYLABS_PASSWORD.")
        return ("", "")

    resolved_username = prompts.ask_required(
        "🔑 Enter your Oxylabs Username",
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
        hide_input=False,
    )
    resolved_password = prompts.ask_required(
        "🔑 Enter your Oxylabs Password",
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
        hide_input=True,
    )
    shared.echo("⚡ Credentials accepted and persisted to .env")
    env.set_value(shared.env_path, "OXYLABS_USERNAME", resolved_username)
    env.set_value(shared.env_path, "OXYLABS_PASSWORD", resolved_password)
    return (resolved_username, resolved_password)


class Frontier:
    """The resolved architect-mode provider settings."""

    def __init__(self, api_key: str, model_id: str, use_anthropic: bool) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self.use_anthropic = use_anthropic


def resolve_frontier(
    shared: "Context",
    settings: config.AnvilSettings,
    anthropic_key: Optional[str],
    no_anthropic: bool,
    want_anthropic: bool,
    anthropic_model: Optional[str],
) -> Frontier:
    """Decide the architect provider."""
    declined = Frontier(
        api_key=_UNSET_API_KEY,
        model_id=settings.default_anthropic_model,
        use_anthropic=False,
    )

    if no_anthropic:
        return declined

    # A supplied key, or an explicit --anthropic, is the consent itself.
    enabled = want_anthropic or anthropic_key is not None
    if not enabled:
        enabled = prompts.confirm(
            "❓ Do you want to use an Anthropic frontier model for architect and orchestrator modes?",
            default=False,
            assume_yes=shared.assume_yes,
            interactive=shared.interactive(),
        )

    if not enabled:
        shared.echo(
            "⚠️  Skipping frontier model setup - architect and orchestrator modes "
            "will use the local gateway."
        )
        shared.echo("💡 Note: If you wish to set this up later, edit")
        shared.echo("   'zoo-code-settings.json' and point modeApiConfigs.architect")
        shared.echo("   and modeApiConfigs.orchestrator at the '{}' id.".format(
            settings.anthropic_profile_id))
        return declined

    api_key = anthropic_key
    if api_key is None:
        # An existing key in .env is reused rather than re-requested.
        existing = env.get(shared.env_path, ANTHROPIC_KEY_ENV)
        if existing:
            shared.echo("🔑 Reusing existing {} from .env".format(ANTHROPIC_KEY_ENV))
            api_key = existing

    if api_key is None:
        api_key = prompts.ask_required(
            "🔑 Enter your Anthropic API Key",
            assume_yes=shared.assume_yes,
            interactive=shared.interactive(),
            hide_input=True,
        )

    _persist_anthropic_key(shared, api_key)

    model_id = prompts.choose(
        "Available Anthropic models",
        options=settings.anthropic_models,
        default=settings.default_anthropic_model,
        supplied=anthropic_model,
        assume_yes=shared.assume_yes,
        interactive=shared.interactive(),
    )

    return Frontier(api_key=api_key, model_id=model_id, use_anthropic=True)


def _persist_anthropic_key(shared: "Context", api_key: str) -> None:
    """Store the key in .env, replacing any existing entry."""
    if shared.dry_run:
        shared.echo("would store {} in {}".format(ANTHROPIC_KEY_ENV, shared.env_path))
        return

    if env.get(shared.env_path, ANTHROPIC_KEY_ENV) == api_key:
        return

    env.set_value(shared.env_path, ANTHROPIC_KEY_ENV, api_key)
    # The value itself is never echoed.
    shared.echo("⚡ Key accepted and persisted to .env")
