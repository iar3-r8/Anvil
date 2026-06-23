---
description: Create a structured GitHub bug report with clear description, reproduction steps, and diagnostic hypotheses
mode: Code
---

Creates a comprehensive GitHub bug report with structured sections for clear communication and efficient debugging.

## Workflow Steps

### 1. Gather Bug Information
- Accept bug description from user
- **Ask at least 2 clarifying questions** to ensure thorough understanding:
  - What environment/conditions trigger the bug?
  - What is the expected vs actual behavior?
  - Any recent changes that may have introduced the issue?
  - Are there error logs, stack traces, or screenshots available?
- Collect reproduction steps the user has already identified

### 2. Format Bug Report Template
- Use the standardized GitHub bug report template below
- Fill in all sections with specific, actionable information
- Include file paths, error messages, and relevant code snippets

### 3. Publish to GitHub
- Use the `github` mcp to create the issue in the repository (the repo name and user should be in .roo/rules/agent.md, else ask the user.)
- If there is any error from the server, return it to the user and wait for instruction on what to do next.
- **This step should be executed automatically after the bug report is formatted**

## Bug Report Template

```markdown
## Bug Report

### Description
<Bug title - concise, specific one-liner summarizing the issue>

<1-3 sentences describing:
- What the bug is (clear, factual description)
- Expected vs actual behavior
- Impact on users/system>

### Environment
<Only include this section if environment details are relevant to the bug (e.g., environment-specific issues, compatibility problems, Docker/OS-specific behavior). Omit entirely if the bug is not environment-dependent.>

### Reproduction Steps
<Numbered list of steps to reproduce the bug>
1. <First action/setup step>
2. <Second action/setup step>
3. <Observe the bug/incorrect behavior>
4. <Expected vs actual output>

**Minimal Reproducible Example** (if applicable):
```python
<code snippet that demonstrates the bug>
```

### Error Logs / Screenshots
<Paste relevant error messages, stack traces, or describe screenshots>
```
<file:path:line> <error details>
```

### Potential Hypotheses
<2-3 educated guesses on root cause and where to investigate>

**Hypothesis 1**: <Likely cause>
- **Where to look**: `specific/file/path.py:line_number`
- **Why**: <reasoning based on evidence>
- **How to fix**: <suggested approach>

**Hypothesis 2**: <Alternative cause>
- **Where to look**: `specific/file/path.py:line_number`
- **Why**: <reasoning based on evidence>
- **How to fix**: <suggested approach>

```

## Guidelines
- **Always ask at least 2 clarifying questions** before proceeding
- **Never invent facts** - only include information you can verify from the code, error messages, or user inputs
- Only include environment details when they are relevant to the bug (e.g., environment-specific issues, compatibility problems)
- Be specific and factual - describe what happens, not assumptions about why
- Include exact error messages and stack traces when available
- Point to specific files and line numbers (e.g., `src/core/tools/compass.py:42`)
- Provide a minimal reproducible example when possible
- Offer hypotheses even if uncertain - they guide investigation
- Keep hypotheses actionable with clear "where to look" guidance
- Use concrete engineering language
- Reference existing issues if this bug is related to a known problem
- **Critical**: Never create a bug report without clear reproduction steps or without attempting to understand the root cause
