---
description: code style guidelines
trigger: always_on
---

## Code language and compliances
<any specific code guidelines to follow>


## Documentation guidelines
<ASK USER the information about how to document the project. how much inline comments, how mych docstrings, any specific documentation to maintain>


## Test guidelines
<ASK USER about test guidelines, how to run tests, you can ask some questions related to:
- Generate code that is easily testable
- Create well-structured functions and classes rather than large, monolithic blocks
- Focus on writing pure functions where possible
- Avoid side effects in functions unless necessary
- Use dependency injection for better testability
>

## Additional Guidelines
<ASK USER for any specific guides like
- Keep functions focused on a single responsibility
- Use descriptive variable names that indicate purpose
- Limit line length to 88 characters (Black standard)
- Use explicit imports over wildcard imports
- Follow naming conventions: snake_case for variables/functions, PascalCase for classes
- Favor short, readable functions and simplicity over complexity; if a change needs a long function full of small edits, factor the decision out into a small helper
- Make the code self-documenting: if a comment or docstring has to restate what the code already shows (a count, a key list, a structure), the code is not clear enough - improve the code rather than add the comment
- Docstrings should help a new reader understand what the thing does and, where genuinely non-obvious, why - not narrate the code, and not carry development history (behaviour numbers, plan references, phase/slice identifiers)>

## Documentation Finalisation
- Once all tests are written and passing, ask the user whether to switch to **Docs Manager** mode to finalize documentation (README, doc/ directory, usage guides).
- Always ask the user whether to document the current commit or the current branch before starting documentation work.

## Where guidance belongs
Mode-specific guidance (rules that only one mode needs) belongs in that mode's `rules-{slug}/` directory, not in these shared always-on files.



