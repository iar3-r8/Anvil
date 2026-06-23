---
description: Write GitHub tasks using a standardized template
mode: Architect
---

Writes GitHub tasks using a standardized template that can be directly pasted into GitHub.

## Workflow Steps

### 1. Gather Task Information
- Accept task description from user using: `/github-task-writing <description>`
- **Ask at least 1 clarifying question** from the Key Questions section to ensure task specificity
- Do not proceed with ambiguous tasks - scope must be clear and actionable

### 2. Format Task Template
- Use the standardized GitHub task template below
- Fill in all sections with specific, actionable information
- Follow all guidelines for quality and clarity

### 3. Publish to GitHub
- Use the `github` mcp to create the issue in the repository (name and repo found in .roo/rules/agent.md)
- If there is any error from the server, return it to the user and wait for instruction on what to do next.
- **This step should be executed automatically after the task is formatted**

## Key Questions to Ask (Minimum 1 Required)
- **Technical specifics**: Questions to provide better technical background
- **Requirements clarification**: Questions to better understand requirements
- **Dependencies**: Questions about dependencies or constraints
- **Priority/urgency**: Questions about priority or urgency
- **Testing requirements**: Questions about testing requirements
- **User impact**: Questions about user impact
- **Performance considerations**: Questions about performance considerations

## Task Template
```markdown
## Task

### Context
<1-3 sentences explaining why this change is needed, what problem it solves, and any relevant background>

### Goal
<1 short sentence>

### Scope
- <short bullet with specific file paths>
- <short bullet with specific file paths>
- <short bullet>

## Definition of Done
- [ ] <verifiable result>
- [ ] <verifiable result>
- [ ] <verifiable result>

## Solutions to explore
<text, links, code for potential solutions to explore or use>
```

## Guidelines
- **Always ask at least 1 clarifying question** before proceeding
- Keep the task short but complete - don't sacrifice clarity for brevity
- Make it directly copy-pasteable into GitHub
- Do not add any text before or after the task
- Do not over-explain
- Use concrete engineering language
- Prefer clear outcomes over design discussion
- Add precise file paths (local paths from repository root, e.g., "src/frontend/components/auth.py") to files that need modification
- Do not use general directions like "check X directory" - point to specific files
- Require the task creator to provide sufficient context (why this change is needed, what problem it solves, any relevant background)
- If a potential solution can be considered, mention it briefly
- **Critical**: Never proceed with ambiguous tasks - ask questions until the scope is clear and actionable
