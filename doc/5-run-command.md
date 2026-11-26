# Running a task end to end

`anvil pi run` drives the agentic pipeline from the command line: one recorded
repository, one GitHub issue, and the run takes the issue from intake to pull
request — the same pipeline [how the agents work](how-the-agents-work.md)
explains. The record the run comes from is the profile store's
([working with run profiles](4-run-profiles.md)); everything below is what the
command does with it.

## The command

```bash
./anvil pi run PROFILE ISSUE
```

- `PROFILE` — the name of the record in `~/.anvil/profiles.yaml`. The record
  supplies the target repository's path, its GitHub identity and its base
  branch, so the command never asks where the task lives.
- `ISSUE` — the number of the GitHub issue to run.

The run's roles execute in a sandbox container, so Docker must be running and
the llama-swap gateway up (`./anvil up`) before a run can ship.

## What a run does

1. **The profile gate.** The store is loaded first, before anything else
   runs: a name the store does not hold, or a record whose path has vanished,
   is a usage error (exit `2`, the store's own message), and no archive is
   created.
2. **The token.** The record's `token_env` key is looked up in
   `~/.anvil/.env`, falling back to the install's `.env` `GITHUB_TOKEN`. The
   token reaches only the GitHub reads — never stdout, the archive, or the
   containers. Missing from both, the run reports that it proceeds
   unauthenticated and does so.
3. **The intake.** The issue is read on the host: its title and body become
   the pull request's title and body, and its labels decide the branch —
   `feature/issue-<n>`, or `bugfix/issue-<n>` when a label is named `bug`.
   When the read fails — the issue is missing or unreachable — the read's
   reason is reported and the run ends on the `intake_failed` outcome: no
   loop, no push, no archive.
4. **The archive.** Before the loop starts, the run opens its archive (below),
   so a run that dies mid-way leaves a readable record.
5. **The loop.** The pipeline runs against the issue with the repository's
   role documents generated at its start: progress is posted on the issue as
   it goes, the work is committed to the branch, and — when the loop ships —
   the branch is pushed to `origin` and the pull request is opened.

## Reading the exit code

`pi run` never exits `0` when it has run: the run's outcome is its own code,
so a script can tell the three endings apart with `$?`:

```bash
./anvil pi run anvil 114
case $? in
  10) echo "the pull request is open" ;;
  11) echo "the run halted" ;;
  12) echo "the intake could not be read" ;;
esac
```

| Code | Outcome | Meaning |
| --- | --- | --- |
| `10` | `opened` | The loop shipped: the branch is pushed to `origin` and the pull request is open on the issue. |
| `11` | `halted` | A designed stop, not a crash: the loop's second failed green on the same behaviour, after which nothing is pushed and no pull request is opened — the halt is posted on the issue instead. |
| `12` | `intake_failed` | The issue could not be read on the host. Nothing ran: no loop, no push, no archive. |

The failures before the loop start carry the codes they always carry: `2` for
the profile gate, and `1` when a finished run cannot push the branch, or when
the archive cannot be opened. A non-zero push is a reported failure — it exits
`1`, never an outcome code.

## The run archive

Everything a run records lands in `~/.anvil/runs/<profile>/<run-id>/` —
outside the target repository, whose working tree the run never records in.
The directory is opened **before** the loop runs, so a run that dies mid-way
leaves a readable record:

- `meta.json` — the run id, the start and finish stamps, the intake (the issue
  number and its title), one session id per role — architect, coder, tester,
  docs — the outcome, a complete flag, and the Anvil version read live at
  start.
- `prompts/<stem>.md` — the role documents the loop generated, archived
  verbatim after the run, so a finished run reads from its archive alone.

A run id is a UTC stamp plus entropy — `run-YYYYMMDD-HHMMSS-` and four hex
characters — so it is unique by construction; a run id whose archive directory
already exists is refused (exit `1`) before anything runs, and a past run is
never overwritten.

## Dry run

`--dry-run` does everything a run does that changes nothing — the profile
gate, the token resolution and the read-only issue read — then stops and
announces: the profile, the derived branch, the archive path that would be
written, and each seam it does not invoke (the run cycle, the push, the
archive).

```bash
./anvil --dry-run pi run anvil 114
```

It exits `0` and writes nothing — `~/.anvil/runs` is not even created. The
failures a real run would hit are reported the same way: a name the store does
not hold still exits `2`, and an issue the read cannot reach still exits `12`.
