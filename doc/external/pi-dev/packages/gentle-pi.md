# gentle-pi · Packages · Pi

Source URL: https://pi.dev/packages/gentle-pi
Fetched: 2026-10-20

Why this page is saved (abridged — the full README is a very long product page; the
sections bearing on the Anvil decision are kept verbatim below): gentle-pi is the closest
existing thing to what Anvil wants to build. It ships a TDD-ish harness ("behavior changes
are test-first by default"), focused subagents as separate processes with per-card model /
tokens / cost / elapsed, **profiles that route the orchestrator independently from
packaged and review roles** — i.e. a per-role model routing answer — and a published
benchmark table comparing before/after routing in seconds, turns and dollars. It is also
21.7 MB, v4.3.0 with a 4.1.0 "stable" install line, replaces Pi's builtin `codemode`,
and is a trademarked single-author product. Downloads 33.4K/mo. MIT.

---

# gentle-pi

Turn Pi into el Gentleman: an ODD development harness with focused subagents, configured TDD evidence, native review, and skill discovery.

## Package details

Types: extension, skill, theme, prompt

- npm: https://www.npmjs.com/package/gentle-pi
- repo: https://github.com/Gentleman-Programming/gentle-shell
- home: https://github.com/Gentleman-Programming/gentle-shell#readme

```
$ pi install npm:gentle-pi
```

| Field | Value |
|---|---|
| Package | `gentle-pi` |
| Version | `4.3.0` |
| Published | Oct 16, 2026 |
| Downloads | 33.4K/mo · 5,945/wk |
| Author | alan_buscaglia |
| License | MIT |
| Types | extension, skill, theme, prompt |
| Size | 21.7 MB |
| Dependencies | 1 dependency · 4 peers |

Pi manifest JSON

```json
{
  "image": "https://cdn.jsdelivr.net/npm/gentle-pi/assets/gentle-logo-only.png",
  "skills": ["./skills"],
  "themes": ["./themes"],
  "prompts": ["./prompts"],
  "extensions": ["./extensions"]
}
```

## Security note

Pi packages can execute code and influence agent behavior. Review the source before installing third-party packages.

## README — the sections that bear on the decision

### ODD — The everyday workflow

**Organic Driven Development (ODD)** is the everyday path: the agent explores before changing anything, clarifies only real decisions, and keeps small understood work small. Substantial, authorized work gets one recoverable feature document — mirrored in memory when available — so progress, evidence, and the next step survive an interruption; behavior changes are test-first by default when a runnable test applies.

Tasks are sized by understanding, risk, and resumability: work you could finish from the request and `git diff` alone runs inline, with no subagents and no task document. The feature document quotes your spec verbatim, and every handoff points at it instead of paraphrasing it, so exact strings, error messages, and examples reach the workers intact.

### Focused agents — Context with a return path

Bring in help without losing the thread. Focused package-owned Pi agents can map a codebase, implement a bounded change, or verify it, while one parent stays accountable for the scope, the decisions, and the final summary.

The parent delegates for a reason, not for size. Understanding that outgrows one inline batch (about 3 calls and 10k tokens) gets one read-only explorer; two or more independent units of behavior, each big enough to outweigh a subagent's start-up and with disjoint edit surfaces, get parallel writers; a change that touches a named high-risk item gets an independent verifier, whatever model wrote it; a long session hands its next unit to a fresh worker. Without a named reason the parent works inline — file count and task size never decide the route.

### Measured — What proportional routing changed

The routing rules came from benchmarks. These runs use a local benchmark with hidden acceptance suites; each cell is a single run (n=1), and cost is API-equivalent.

| Scenario | Before | After |
| --- | --- | --- |
| 3-line bug in one function | 335 s · 56 turns · $0.339 | **77 s · 10 turns · $0.105** — inline, no subagents |
| Bug rooted in shared logic | 479 s · $0.361 | **276 s · $0.207** — one explorer |
| Data migration (high risk) | 559 s · $0.403 · needed a feedback round | 539 s · $0.555 · **accepted on the first round** — one independent verifier |
| 73-line spec, 26 hidden checks | Paraphrased handoffs: 13 failing, still 23/26 after two feedback rounds | Spec passed by reference (#1718) |

Against the same model in Codex CLI, with blind review of every solution, Gentle Shell was accepted on the first round in every cell and ranked higher on the medium (3 of 3 runs) and large tasks; it was close on the small one. The large task still took about three times longer (17.5–17.9 min vs 6.1 min) — that gap is open work. Sources: #1723, #1794, #1713.

### Gentle Agents — Parallel work with a live view

Delegating work should not mean losing it. Every subagent runs as its own process with a live card above the editor — model, tokens, cost, elapsed — and `alt+a` opens the full view with retained threads, stop controls, and history restored on resume. A child can ask you a question as an ordinary dialog, and background results come back as cards that start a new turn — nothing polls.

### Profiles and model routing — One deliberate decision per knob

Model, effort, and who does what should be choices, not accidents. Named profiles route the orchestrator atomically and independently from packaged and review roles; a repository can pin its profile so its subagents stop following the globally active one, and the panel always shows the routing the runtime actually uses.

### Native review — Review the exact change

Review the exact change, not a moving target. Native review keeps one candidate in view, returns risk-scoped evidence, and can surface a bounded correction path. You still decide what happens next in your repository.

Review is proportionate: an independent verifier runs only for a named high-risk item in every RDD state, a review is only due for high-risk work, and the agent forwards the 4R lenses that fit what it touched — with its reason — instead of paying for all four.

> ℹ️ **RDD is opt-in:** enable native receipt-driven development only through an explicit `/gentle:review-mode enable` decision.

### Permission modes — Normal, Auto, or YOLO

Choose `/gentle:mode auto` to check eligible actions with an independent inference using the current session model. Ordinary checks are tool-free; an eligible script check can inspect at most two complete files.

Auto covers primary file/shell/custom/MCP tools and nested calls through the SDK pipeline while retaining explicit restrictions, destructive guards and independent consent. It adds separately recorded inference cost and latency; unavailable or stale decisions do not run the action. **This is not a sandbox or a claim of proprietary classifier parity.**

`/gentle:yolo enable` supplies standing permission for ordinary already-scoped implementation, checks, commits, non-force pushes and PR creation. Destructive operations still require fresh confirmation. **This is not a sandbox.**

### Install paths (abridged)

- Path A: `npm i -g gentle-pi` then `gentle-shell` — a launcher that opens Pi with the package loaded, in its own home `~/.gentle-shell/agent`, without touching your pi install. Requires Pi 1.2.0 or newer. Every other argument is forwarded to pi unchanged, for example `gentle-shell --mode rpc` or `gentle-shell -p "..."`.
- Path B: `pi install npm:gentle-pi@4.1.0` into an existing pi agent, restart, then `gentle-ai sync`.
- Path C / installers: a browser wizard and double-click installers that install Node.js, pnpm, Pi and Gentle Shell.

gentle-pi replaces Pi's builtin `codemode` with its compact renderer, so Pi warns at startup that the builtin was not loaded.

### Also in the box (abridged)

| Component | What it does |
| --- | --- |
| Startup and runtime panel | A configurable gentle-shell entry point and visible runtime state for Pi. |
| Skills and delivery guidance | Package skills for documentation, issue work, PRs, reviews, and reviewable work units. |
| Model, effort, persona, and profile controls | Explicit knobs for how Pi routes and presents work. |
| Safety boundaries | Guards around destructive operations and sensitive-path handling. |
| Parent ↔ subagent communication | Delegate, steer, reply, and cross-session notification within your local profile. |
| Gentle Stats | `/gentle:stats` shows local usage history: activity heatmap, tokens, cost, streaks, and per-model share. |

> **Trademark notice:** The gentle-shell™ and gentle-pi™ names and associated logos are trademarks of Alan Buscaglia. The MIT License applies to the code; it does not permit implying endorsement or official affiliation.
