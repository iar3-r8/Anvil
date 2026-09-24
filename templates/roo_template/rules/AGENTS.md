---
description: Agent guidelines
trigger: always_on
---

## Code Change Process

When asked to change code, follow these principles:

- **Do not jump to conclusions**: Avoid assuming the best solution without context
- **Ask for clarification**: If there are multiple possible solutions, always ask the user for more context or information before implementing
- **Collaborate first**: Always collaborate with the user rather than making unilateral decisions about implementation approach
- **Present options**: When multiple valid approaches exist, outline the options and let the user decide


## MCP server or tool usage
When using a tool with unknown argument, ask the user to get missing information

- **Prefer narrow queries**: ask for only what the question needs; a broad query returns more context than gets read.
- **Request the smallest page size that answers the question**: extra pages cost context without adding signal.
- **Keep issue comments short**: because every `add_issue_comment` echoes the body back, a long comment is paid for on arrival and again on every later turn.

### Github
When using the github MCP, use the user <Github user> and repository <Repository Name>

### Oxylabs
The oxylabs MCP fetches third-party documentation from the web. Use it to close a
knowledge gap, not to browse.

- **Unknown third-party documentation is a blocking condition.** Before planning or
  coding against an external library, API or service, decide whether its interface is
  actually known — not plausible, known. If it is not, say so, then either ask the user
  for the documentation or fetch it with oxylabs. Never guess a method, argument or
  response field.
- **Save in full what answers the question**, under `doc/external/<vendor>/<page-slug>.md`,
  with the source URL recorded at the top of the file. One page per file.
- **Save only a link for everything adjacent** — one line in `doc/external/index.md` with
  the URL, the title and a one-sentence description. Do not mirror a vendor's whole site.
- **`doc/external/` is committed**, so the research is reviewable in the pull request and
  is not re-fetched by every developer. Never write credentials or private endpoints into it.
- **Cite the saved file or the URL** wherever a third-party fact is asserted, so a reviewer
  can check the claim without re-deriving it.
- **If oxylabs is unavailable** — disabled, or missing credentials — say so and ask the user
  for the documentation rather than proceeding on assumption.

## Keep It Simple (KISS)

- **The simplest solution wins**: The simplest solution that meets the requirement is the right one — do not add complexity nothing asks for.
- **Optimise only when asked or measured**: Optimise only when the user asks or a measured problem demands it — never pre-emptively.
- **Build the happy path first**: Deliver the main feature before the rare case.
- **Fail safely**: On an unexpected state, raise a clear controlled error or return a safe default — never a silent bug, never a crash that loses data.
- **Log unexpected states**: Log unexpected states, so how often a rare case really happens is known, not guessed.
- **Handle a rare edge case only when real users or real data hit it** — exception: a data-loss or security risk is fixed immediately.

## Communication

- **Lead with the concrete thing**: the specific value, path or failure first; the general comes after.
- **Consequence before mechanism**: say what happens and why it matters before explaining how it happens.
- **Name what is at stake**: the cost, data or trust that is lost if the reader gets it wrong.
- **It applies everywhere a reader meets this work**: chat replies, subtask reports and pull request descriptions.
- **The clarity-versus-brevity tension**: clearer writing is usually shorter, so this and the cost goal mostly agree — where they conflict, clarity wins for anything a human reads and brevity wins for anything only a model reads.
