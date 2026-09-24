# Testing

Anvil's test suite is `unittest` from the standard library. Every module in
`anvilkit/` has a matching `tests/test_*.py`.

## Running the tests

```bash
./tests/run                      # the whole suite
./tests/run tests.test_cli       # one module
./tests/run tests.test_cli.TestDispatch.test_up_starts_the_stack
./tests/run -k dry_run           # filter by name
```

`tests/run` provisions the virtual environment through `scripts/bootstrap.sh`, so
the suite always runs against the same interpreter `./anvil` uses. There is
nothing to install by hand, and no need to invoke `python3` directly.

Exit code `0` means everything passed. The suite takes a couple of seconds; it
never touches the network, the Docker daemon, or your home directory.

## Checking the CLI against a real host

Commands that inspect actual behaviour without starting or changing anything:

```bash
./anvil doctor                                   # what Anvil found on this host
./anvil --dry-run up                             # the docker command that would run
./anvil --dry-run setup-repo /tmp/scratch --yes  # the files that would be written
./anvil --dry-run stress MODEL                   # the levels, port and log path that would be used
```

## When to run

- Before committing anything under `anvilkit/`.
- After editing `config.yaml`, `anvil.yaml`, or any file in `templates/`.
- Before opening a pull request.

> Conventions for *writing* tests (strict TDD, what may not be asserted on, the
> stdin, `CliRunner` and `getpass` pitfalls) live in the qna-tester's rules,
> [`.roo/rules-qna-tester/instructions.xml`](../.roo/rules-qna-tester/instructions.xml).

## Testing the shipped rules

The rules in `templates/roo_template/` are data under test, and several modules
assert on their parsed structure:

| Module | Covers |
| --- | --- |
| [`tests/test_templates_rules.py`](../tests/test_templates_rules.py) | the architect template; the tdd-manager delegation contract |
| [`tests/test_manager_rules.py`](../tests/test_manager_rules.py) | the tdd-manager workflow, its practices and its byte ceiling |
| [`tests/test_agents_rules.py`](../tests/test_agents_rules.py) | both `AGENTS.md` copies: sections and bullets |
| [`tests/test_rules_mirror.py`](../tests/test_rules_mirror.py) | the four XML rule files stay byte-identical between `templates/roo_template/` and `.roo/` |
| [`tests/test_shared_rules_split.py`](../tests/test_shared_rules_split.py) | mode-specific rules sit in their `rules-{slug}/` file, not in the shared always-on files |

Two properties of this suite are worth knowing:

- **The assertions are phrase predicates** — substring checks on lower-cased
  element text — so the rule prose has latitude and deleting a matched element
  is what turns a test red, not rewording.
- **The byte ceiling is the one exception to "never assert on the source
  text."** `TDD_MANAGER_BYTE_CEILING` in
  [`tests/test_manager_rules.py`](../tests/test_manager_rules.py) caps the
  tdd-manager rule file at 12,288 B. The size *is* the requirement there —
  the defect being guarded is that the file is too large and every subtask
  pays for it — and it never stands alone: the phrase predicates in the same
  modules prove no rule was lost. The argument for the exception is in
  [`plans/cut-agent-context-cost.md`](../plans/cut-agent-context-cost.md) §6.
