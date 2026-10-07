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
