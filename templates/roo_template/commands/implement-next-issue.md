---
description: Find the most logical next open GitHub issue, confirm it, and hand it to the tdd-manager pipeline
mode: tdd-manager
---

Implement the next issue

Finds the most logical next open GitHub issue, confirms it with the user, and hands it to the tdd-manager pipeline.

**Usage:**
- Run with no argument: `/implement-next-issue` — the argument is optional, and the command works fine with nothing after it.
- Optionally pass free-form context to bias the selection: `/implement-next-issue <context>`

**Example:**
```
/implement-next-issue
/implement-next-issue the API auth flow
```

**Prerequisites:**
- The GitHub MCP server must be available — all GitHub calls in this workflow go through it.
- The GitHub owner and repository name come from `.roo/rules/AGENTS.md`.

**Ranking:**

When more than one open issue is a candidate, rank them by the five criteria below, in this order. Each earlier criterion outranks the later ones:

1. **Bug over feature** — a bug (issue type or bug label) outranks a feature.
2. **Priority label** — an explicit `priority:*` label orders the candidates; when the label is absent, this criterion degrades to the next tiebreaker (this repo uses no priority labels today).
3. **Milestone** — an issue with a milestone outranks one without.
4. **Not blocked** — an issue with no open blockers (`issue_dependencies_summary.blocked_by == 0`) outranks a blocked one.
5. **Oldest created_at** — when every earlier criterion ties, the oldest `created_at` wins; this is the final tiebreaker.

**Pull request exclusion:**

GitHub's issues endpoint may return pull requests as entries, and an issue already claimed by an open pull request is not a free candidate. Before ranking, run the exclusion in two arms:

1. **Skip PR entries** — skip any returned issue entry that is itself a pull request; it is not a candidate issue at all.
2. **Exclude closer-referenced issues** — list the open pull requests via `list_pull_requests`, and exclude any issue referenced by a `Fixes #N`, `Closes #N` or `Resolves #N` closer in an open pull request's title or body; that issue is already in flight.

If the pull request listing fails, report the failure and stop — never proceed on the unfiltered issue list, since a silent fallback would re-select work that is already being implemented.

**Argument handling:**

When free-form context is supplied after the command, it overrides the five-criterion ranking chain outright: an open issue matching the supplied context wins the selection, even if another issue would have ranked higher under the chain. In that case the one-line rationale names the match — e.g. "issue #42 matches the supplied context 'API auth flow'".

When the context matches no open issue, say so in the rationale and fall back to the unbiased ranking rather than selecting nothing.

**Confirmation:**

Before any work starts, present the top candidate to the user with its number, title and a one-line rationale, then ask exactly one confirmation question. Ask no further question unless the issue itself is genuinely ambiguous.
