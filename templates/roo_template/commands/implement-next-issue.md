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
