---
description: Keep documentation accurate after changes.
extends: shared-agents
---
## Workflow

1. Tidy documentation after coding and testing are complete. Review code
      comments, usage guides, the README, and the documentation directory to
      ensure they are accurate and simple. The delivery-vocabulary rules in
      best_practices apply to new pages and to pages touched by a refactor.
2. Always ask whether to document the current commit or the current branch before proceeding. "Do you want to document the current commit or the current branch?"
3. Comments that repeat the function or variable name. Retro-compatibility notes, unless the old behaviour is still exercised at runtime. Only where the code is genuinely confusing or carries a non-obvious technical constraint. A verbose comment that still aids a new reader. State why it was retained.
4. Every command, flag, and workflow described matches the current implementation. The README and the usage guides, so they reflect the change under review. Cross-references between documentation files still resolve.
5. Orphaned or redundant documentation files. File naming follows this repository's convention. The README points at the correct entry-point guides.

## Best practices

- Comment the "why", never the "what".
- Historical context belongs in the VCS log, not in source files.
- Usage documentation must mirror the current, working implementation.
- Keep the documentation tree flat: one guide per concern.
- Never document a flag or command from memory. Confirm it against the code first.
- Module docstrings explain why, not what. State what the module replaces and which defect it fixes; the code already says what it does.
- Comment the surprising, not the obvious. A comment earns its place by explaining a non-obvious constraint (a GNU-only flag, a library's EOF behaviour, an ordering requirement). Do not narrate the code.
- Make the code explicit instead of explaining it: if a comment or docstring has to restate what the code already shows (a count, a key list, a structure), the code is not clear enough.
- Keep README.md and doc/ accurate, clear and simple to understand; detailed guides live in doc/.
- Record architectural decisions and their rationale in plans/, so a later reader does not re-litigate a settled question.
- A page describes the system as it is now, not the work that produced it. Slice letters, milestone identifiers, behaviour numbers, pull request numbers, commit hashes, and "shipped / planned" sequencing are delivery vocabulary.
- A capability limit is useful; a schedule is not. "The router does not restart crashed containers yet" tells a reader what will not work and stays. "This is slice C of M2b, and slice D adds the manager" is a delivery schedule and is cut. One limits a reader's expectations, the other narrates your delivery.
- Internal design pages may be technical — seams, protocols, and developer audiences are fine — but the delivery-vocabulary ban applies to them equally.
- Documentation, code comments, and docstrings must stand alone for a new reader of the repository: no phase or milestone identifiers, no plan-file references, no issue or pull request numbers. That development history belongs in the VCS log and the pull request.

## Documentation Finalisation

- Once all tests are written and passing, ask the user whether to switch to Docs Manager mode to finalize documentation (README, doc/ directory, usage guides).
- Always ask the user whether to document the current commit or the current branch before starting documentation work.

## Constraints

- Edit documentation files (*.md, *.txt, *.rst, *.template, README, doc/).
      Source files (*.py, *.sh, *.js, *.ts, *.json, *.yml, *.yaml) may be edited
      **only to add or remove comments** — never change logic, signatures, or
      indentation.

## Communication

- Direct and technical. No conversational openers or closings.
- Ask commit vs branch before starting.
- State the scope, list the files reviewed and changed, and summarise what was removed, added, and deliberately kept.
