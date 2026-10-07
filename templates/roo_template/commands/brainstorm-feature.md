---
description: Run a structured, iterative architectural brainstorming session that ends by writing a spec and raising fractioned GitHub issues — no implementation code
mode: Architect
---

Brainstorm a feature architecturally, in plain language, before any code is written.

The session has three phases: gather context and pressure-test the requirements, write the spec report, then sign off and raise fractioned GitHub issues. This command starts with Phase 1.

**Plain language, always**

Write everything this session produces — the specifications, the behaviours, the final report — in clear, simple, plain language that a non-specialist reader can follow. Avoid jargon; if a technical term is unavoidable, define it in one line the first time it appears. This rule stands for the whole session and outranks any habit of reaching for specialist shorthand.

**Phase 1 — Context, then the grill**

1. **Gather first, ask second.**
   On launch, gather the early context and requirements before you ask anything: read the relevant code, docs, and configuration that the feature touches. Only then dig into what you found with questions.

2. **One question per message.**
   Ask exactly one question at a time. Never batch multiple questions into a single message — one plain, direct question per reply.

3. **Keep it short and wait.**
   Send short responses, and after each question stop and wait for the user's answer before asking the next one.

4. **At least 3-4 iterations.**
   Run this gather-ask-wait loop for at least 3-4 rounds before moving on, unless the user says to stop.

5. **Aim the questions at the hard parts.**
   - Hidden edge cases
   - Single point of failure
   - Scale boundaries and performance trade-offs
   - Data life-cycles, including mutation safety

6. **No reflexive agreement, no code.**
   Do not agree immediately or jump to solutions. Never write implementation code, boilerplate, or complete files during the session — the goal is a spec, not an implementation.

**Phase 2 — The report**

When the brainstorming is done — or enough clarity is reached — compile the collective discoveries into a single report at `plans/specs/<feature-slug>.md`, where the slug is the feature name in kebab-case; if the slug is ambiguous, ask the user before writing. If a report for the same feature already exists, update that file rather than creating a duplicate.

The report contains these four sections:

- **System Architecture Overview** — a clear structural breakdown of the design.
- **Data Models & State** — component boundaries, schemas, and how state is stored.
- **Edge Cases & Error Handling** — the concrete mitigation for each hard problem found in Phase 1.
- **Testing & Success Criteria** — clear definitions of done.

**Phase 3 — Sign-off, then issues**

1. **Present the report and ask for sign-off.**
   Present the finished report and ask for the user's absolute sign-off on it. Do not create anything until the user has given that sign-off — the report must be approved before any issue is created, raised, or published.

2. **Fraction the report into separate GitHub issues.**
   Once sign-off is given, break the report into separate GitHub issues — one issue per independently implementable piece of work.

3. **Follow the `/write-github-task` format.**
   Each issue follows the `/write-github-task` format: Context / Goal / Scope / Definition of Done. The repository name comes from `.roo/rules/AGENTS.md`, and the issues are published through the github MCP server.

4. **Then stop.**
   Once the issues are created, the session stops there. Execution is a separate, later command — hand the issues to the `execute-github-task` command or the tdd-manager pipeline. Do not implement anything in this session.
