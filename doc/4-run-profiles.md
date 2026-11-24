# Working with run profiles

One Anvil installation can serve many repositories, and a run must be able to
tell which one it is in. `setup-repo` records each provisioned repository as a
**profile** in the store at `~/.anvil/profiles.yaml`, and the two `profile`
commands read it back. A record is the identity a run consumes: the absolute
repository path, the GitHub identity the guards gate resolved, the base branch
the gate checked, and the name of the environment variable that holds the
repository's token — never the token's value.

Nothing in the store is a secret: both commands print only the record's own
fields, so neither ever reveals a token.

## The record

| Field | What `setup-repo` records |
| --- | --- |
| `name` | The profile name — the value of `--profile NAME`, or the answer the run asks for interactively: there is no default. Letters, digits, dot, dash and underscore; it may not start with `-`, `.` or a digit, because a leading hyphen would read as a flag. |
| `path` | The target repository's absolute path. |
| `owner`, `repo` | The GitHub identity the guards gate resolved from the target's `origin` — `null` when no repository could be resolved, never a guess. |
| `base` | The branch the guards gate checked: `main`. |
| `token_env` | The environment variable that holds the repository's token, derived from the name: `project-x` becomes `GITHUB_TOKEN_PROJECT_X`. The store records the key name only; a value is looked up in `~/.anvil/.env` under that key, falling back to the install's `.env` `GITHUB_TOKEN`, and a token missing from both resolves to nothing rather than an error. |
| `project` | A block for facts a run learns about the repository. `setup-repo` records it empty today. |

The gateway port and the coder model are deliberately not in the record: one
llama-swap backend serves every repository, so they are not properties of a
profile.

## One path, one profile

The store holds at most one record per repository path:

- **Re-saving the same name and path updates the record in place.** Re-running
  `setup-repo` on an already provisioned repository refreshes `owner`, `repo`
  and `base` without leaving a duplicate — provisioning twice is normal.
- **Saving a path under a new name renames the existing record in place.** The
  `project` block carries across and `token_env` is re-derived from the new
  name.
- **Saving a name that already points at a different, still-existing
  repository is refused**, naming the path it already points at — a silent
  overwrite would leave a later run editing the wrong repository. A stale
  record whose path has vanished is not a collision, so the save proceeds.

## When a record is written

`setup-repo` asks for the profile name **before** it provisions anything, so a
bad `--profile NAME` is a usage error (exit code `2`) that stops the run clean
and a bad answer given interactively is simply asked again. It then writes the
record **after** the provisioning succeeds, from the identity the guards gate
already resolved — never re-resolving it.

- `--profile NAME` supplies the name without prompting; an interactive run
  without the flag is asked with no default, and re-asked until the name is
  valid.
- `--yes` and non-interactive runs cannot answer a question that has no
  default: they fail on the prompt code `6`, naming `--profile NAME` as the
  fix, and nothing is provisioned.
- `--dry-run` names the store path and every field that would be recorded, and
  writes nothing — the store file is not created or modified.
- A run with `--no-github` has no identity to record, so it writes no profile
  and asks no name question.
- A gate that ran but could not resolve the identity still records, with
  `owner` and `repo` as `null` rather than a guess.

A store failure after a successful provisioning — a name collision at a
different path, an unwritable store — exits with the configuration code `3`:
the provisioning succeeded, and the failure is reported, not swallowed.

## Inspecting the store

```bash
./anvil profile list           # every profile, one line: name and absolute path
./anvil profile show NAME      # one record, field by field
```

- `profile list` is a discovery tool. It exits `0` with `No profiles are
  saved.` when the store is empty, and it still lists a record whose directory
  has been deleted, with its stored path — a deleted checkout is exactly when
  you want to find the profile that pointed at it.
- `profile show` is strict. It exits `2` for a name the store does not hold —
  naming the known profiles, or saying none are saved, so a typo is fixable
  from the message — and exits `3` for a record whose path has vanished or a
  malformed store: a record that cannot be trusted is not printed as if it
  were.
- Both commands are read-only, and both print only the record's own fields.
  `show` prints the `token_env` key name — never a resolved token value.

For the `setup-repo` side — the name prompt and what the record captures —
see the [VS Code plugin setup guide](2-setting-up-vscode-plugin.md).
