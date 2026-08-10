# Decision: git push from inside the dev container

## Context

`git push` inside the dev container fails before it reaches the network:

```
error: cannot run ssh: No such file or directory
fatal: unable to fork
```

The remote is in SSH form, so git tries to `exec` an `ssh` client.
[`.devcontainer/Dockerfile`](../.devcontainer/Dockerfile:9) installs
`ca-certificates curl gnupg git sudo`; nothing on `python:3.11-slim-bookworm`
pulls in `openssh-client`, so `/usr/bin/ssh` does not exist.

Installing the binary would only move the failure one step later. The sandbox
deliberately mounts the workspace and nothing else — see
[`plans/devcontainer.md`](devcontainer.md:32) — so `$HOME/.ssh` is absent and
there is no key material to authenticate with. The next error would be
`Permission denied (publickey)`.

The container is, however, already trusted with a GitHub credential:
`GITHUB_TOKEN` arrives via `remoteEnv` in
[`.devcontainer/devcontainer.json`](../.devcontainer/devcontainer.json:22).

## Decision

**Authenticate over HTTPS using the `GITHUB_TOKEN` the container already has.
Do not install `openssh-client` and do not forward an SSH agent.**

Configured with `git config --system` in the Dockerfile, in the root `RUN`
layers that precede `USER vscode`. System scope is the right level: it is
image-wide, needs no `postCreateCommand`, and is still overridden by any
`--global` or per-repo setting a developer adds later.

Two settings are required.

1. **A credential helper that reads the token from the environment at use
   time**, so no token value is ever written to a file:

   ```
   credential.https://github.com.helper = !f() { test "$1" = get && \
       printf 'username=x-access-token\npassword=%s\n' "$GITHUB_TOKEN"; }; f
   ```

   The `$GITHUB_TOKEN` expansion must survive image build — quote it so the
   shell running `RUN` does not substitute it, since at build time it is empty.
   `x-access-token` is the username GitHub accepts for token auth.

2. **`insteadOf` rewrites, so existing SSH remotes keep working** without
   anyone editing `.git/config`. Both spellings are needed, and the second must
   use `--add` or it replaces the first:

   ```
   url.https://github.com/.insteadOf = git@github.com:
   url.https://github.com/.insteadOf = ssh://git@github.com/
   ```

**The fix lands in `templates/devcontainer/Dockerfile` as well.** That template
is what `setup-repo` ships into target repos via
[`provision._copy_devcontainer()`](../anvilkit/provision.py:334); fixing only
the Anvil-native copy would leave every provisioned repo carrying the defect.
The two files must stay in parity, enforced by a test.

### Written inline, and not covered by tests

The two `git config` calls are written inline in the `RUN` layer rather than
extracted into a helper script. Extraction was considered only because it would
have allowed behavioural assertions via `git credential fill` and
`git ls-remote --get-url`; with no tests planned, that motivation disappears and
the template stays at two files.

**This is a deliberate exception to the strict-TDD rule in the coding
guidelines.** The justification is that the change is image build configuration
with no Python surface: the only assertions available would be against
Dockerfile source text, which the guidelines forbid, or against a real image
build, which is slow Docker I/O the suite must not do. Verification is therefore
manual and empirical — a real push from inside a rebuilt container.

The consequence is that **the parity between `.devcontainer/Dockerfile` and
`templates/devcontainer/Dockerfile` is unguarded**. Nothing will fail if a later
change updates one and not the other, and the symptom would surface only in a
freshly provisioned repo. Anyone editing either file must edit both.

## Consequences

### What this buys

- No new apt package, and the security boundary drawn in
  [`plans/devcontainer.md`](devcontainer.md:32) is unchanged. No host key
  material, no agent socket, no `$HOME` mount.
- The credential is scoped to `github.com` and to a single token whose
  permissions the user controls, rather than an agent that can sign for every
  key it holds.
- SSH-form remotes continue to work untouched, so no developer has to re-point
  a remote.

### Costs and limits

- **Only `github.com`.** Any other SSH remote still fails, now with the
  original `cannot run ssh` error. That is acceptable — and is the honest
  signal, since no credential exists for those hosts either.
- **The token needs the right scopes.** `repo` at minimum, plus `workflow` to
  push changes under `.github/workflows/`. A token that is merely present is
  not necessarily sufficient.
- **An unset `GITHUB_TOKEN` degrades badly.** The helper yields an empty
  password and git reports `Authentication failed`, which points at the wrong
  cause. `doctor` should name it explicitly when `ANVIL_IN_CONTAINER` is set:
  the check is that the variable is present and non-empty, never a validation
  call to the API, which would be network I/O.

## Adjacent findings, in scope

- **Commit identity.** With `$HOME` unmounted, `user.name` and `user.email` may
  be unset, which breaks `git commit` — a separate failure from this one, and
  one the TDD cycle will hit as soon as it tries to commit. VS Code usually
  copies the host `.gitconfig` into the container; that behaviour needs
  confirming rather than assuming, including whether it collides with what we
  set at system scope.
- **`safe.directory`.** A bind-mounted workspace whose owner uid does not match
  the container `vscode` uid provokes `detected dubious ownership`. The image
  pins uid 1000, which matches the common case, so this is a verification step
  and not presumed work.

## Alternatives considered

- **`openssh-client` plus forwarded SSH agent.** Keeps SSH remotes native and
  exposes only the agent socket, not the keys. Rejected because it widens the
  filesystem/process boundary the container exists to draw, depends on the host
  having an agent loaded, and lets the container sign with any key that agent
  holds.
- **Mounting `~/.ssh` read-only.** Directly contradicts
  [`plans/devcontainer.md`](devcontainer.md:32) and puts private keys inside a
  sandbox built to keep them out.
- **`postCreateCommand` instead of the Dockerfile.** Changeable without a
  rebuild and more visible than a build layer, but it runs per-attach, is easy
  to clobber when a target repo sets its own, and the template currently has no
  `postCreateCommand` to extend.
- **Rewriting remotes to HTTPS in `.git/config`.** Fixes one clone and leaves
  the image broken for the next one.
