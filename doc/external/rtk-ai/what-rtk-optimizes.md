# RTK — what RTK optimizes

Source: https://www.rtk-ai.app/docs/resources/what-rtk-covers/
Retrieved: 2026-10-19 (fetched by the tdd-manager via oxylabs `universal_scraper` during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

The full per-ecosystem list of commands RTK filters, and what "no filter" means.

RTK reduces **bash output bytes** — the only thing it controls. Those bytes
are one contributor to input tokens, and input tokens are only part of a bill
that also counts output tokens.

Git: `git status` (compact stat format, grouped by state), `git log` (hash +
author + subject only), `git diff` (context reduced, headers stripped),
`git show` (same as diff), `git stash list` (compact one-line per entry).

GitHub CLI: `gh pr view` (removes ASCII art and verbose metadata), `gh pr
checks` (status + name only, failures highlighted), `gh run list` (compact
workflow run summary), `gh issue view` (body only, no decoration).

Graphite: `gt log` (stack summary only), `gt status` (current branch context).

Cargo / Rust: `cargo test` / `cargo nextest` (failures only, passed tests
suppressed), `cargo build` / `cargo check` (errors and warnings only),
`cargo clippy` (lint warnings grouped by file).

JavaScript / TypeScript: `jest`, `vitest` (failures only), `tsc` (type errors
grouped by file), `eslint` (violations grouped by rule), `pnpm list` (compact
dependency tree), `pnpm outdated` (package + current + latest only), `next
build` (route summary + errors only), `prisma migrate` (migration status
only), `playwright test` (failures + trace links only).

**Python: `pytest` (failures only), `ruff check` (violations grouped by file),
`mypy` (type errors grouped by file), `pip install` (installed packages only,
progress stripped). NOTE: no `python -m unittest` / stdlib unittest filter.**

Go: `go test` (failures only), `golangci-lint run` (violations grouped by
file), `go build` (errors only).

Ruby: `rspec` (failures only), `rubocop` (offenses grouped by file), `rake`
(task output, build errors highlighted).

.NET: `dotnet build` (errors and warnings only), `dotnet test` (failures
only), `dotnet format` (changed files only).

Docker / Kubernetes: `docker ps` (essential columns), `docker images` (name +
tag + size only), `docker logs` (deduplicated, last N lines), `docker compose
up` (service status, errors highlighted), `kubectl get pods` (name + status +
restarts only), `kubectl logs` (deduplicated entries).

Files and Search: `ls` (tree format with file counts), `find` (tree format),
`grep` (truncated lines, grouped by file), `ast-grep` (grouped by file, capped
overflow; `--json` passes through), `diff` (context reduced), `wc` (compact
counts), `cat` / `head` / `tail <file>` (smart file reading via `rtk read`),
`rtk smart <file>` (2-line heuristic code summary).

Cloud and Data: `aws` (JSON condensed, relevant fields only), `psql` (query
results without decoration), `curl` (response body only, headers stripped).

Global flags: `-v`/`--verbose` show filtering details on stderr.

Commands that are not rewritten: if a command isn't in the list, RTK runs it
through passthrough — the output reaches the LLM unchanged. `rtk bypass make
install` runs it, tracks usage, no filtering. `rtk discover` lists missed
opportunities.
