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
