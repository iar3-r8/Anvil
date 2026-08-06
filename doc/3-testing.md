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

Two commands inspect actual behaviour without starting or changing anything:

```bash
./anvil doctor                                   # what Anvil found on this host
./anvil --dry-run up                             # the docker command that would run
./anvil --dry-run setup-repo /tmp/scratch --yes  # the files that would be written
```

## When to run

- Before committing anything under `anvilkit/`.
- After editing `config.yaml`, `anvil.yaml`, or any file in `templates/`.
- Before opening a pull request.

> Conventions for *writing* tests (TDD cycle, what may not be asserted on, the
> stdin and `CliRunner` pitfalls) live in
> [`.roo/rules/coding-guidelines.md`](../.roo/rules/coding-guidelines.md).
