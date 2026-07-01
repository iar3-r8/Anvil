---
description: Create a pull request with auto-generated description from branch changes
trigger: user
---

## Create Pull Request

**Usage:**
- Ask the user for the GitHub issue number after the command: `/create-pull-request <issue-number>`
- Fetch the issue title from GitHub to use as the PR title
- Analyze branch changes using the Git MCP server
- Generate a PR description based on the changes
- Create the PR using the GitHub MCP server

**Prerequisites:**
- Current branch is pushed to remote
- GitHub MCP server and Git MCP server are available

**Workflow Steps:**

1. **Ask for Issue Number**
   - Prompt user: "What is the GitHub issue number for this PR?"
   - Example: "47"

2. **Fetch Issue Title from GitHub**
   - Use GitHub MCP server to get issue details:
   ```
   mcp--github--get_issue(owner="owner name", repo="repo name", issue_number=<issue-number>)
   ```
   - Use the fetched title/body as the PR title and context

3. **Detect Base Branch and Analyze Changes Using Git MCP**
    - Get current branch and detected base branch from upstream:
    ```
    mcp--git--git_branch(repo_path=".", branch_type="local", contains="<head_sha>")
    ```
    - Or use `git status` to detect upstream: `mcp--git--git_status(repo_path=".")` → look for `[origin/<branch>]` pattern
    - Extract base branch name from the upstream tracking reference (strip `origin/` prefix)
    - Get diff between base and current branch:
    ```
    mcp--git--git_diff(repo_path=".", target="<detected_base_branch>")
    ```
   - Or get commit log:
   ```
   mcp--git--git_log(repo_path=".", max_count=10)
   ```

4. **Generate PR Description**
   - Structure according to `.roo/commands/pull-request-builder.md` guidelines:
   ```
   ### Context
   [One sentence explaining the problem/reason for changes based on issue title]
   
   ### Changes
   - **<file_path>**: Brief description of what was changed
   - **<file_path>**: Brief description of what was changed
   ```
   - Group changes by file/directory from git diff output
   - Focus on key modifications, not every detail
   - Keep it concise with bullet points

5. **Create Pull Request**
    - Use GitHub MCP server to create PR:
    ```
    mcp--github--create_pull_request(
      owner="<owner name>",
      repo="<repo name>",
      title="<issue_title>",
      body="<generated_description>",
      head="<current_branch>",
      base="<detected_base_branch>",
      draft=false,
      maintainer_can_modify=true
    )
    ```

6. **Report Result**
   - Provide the PR URL to the user
   - Summary of changes included

**Example Execution:**
1. User: `/create-pull-request 47`
2. Fetch issue #47 via `mcp--github--get_issue(owner="<owner name>", repo="<repo name>", issue_number=47)`
    - Title: "Fix stale edge filtering for missing target node"
3. Detect base branch and analyze branch via Git MCP:
    - `mcp--git--git_status(repo_path=".")` → shows branch: `* mathieu/gpu-unload-call-on-local-engine  123456 [origin/mathieu/bugfix-reference-missing-target-node]`
    - Extract base branch: `mathieu/bugfix-reference-missing-target-node`
    - `mcp--git--git_diff(repo_path=".", target="mathieu/bugfix-reference-missing-target-node")` → shows changed files and diffs
    - `mcp--git--git_log(repo_path=".", max_count=5)` → shows commit history
4. Generate description from diff output:
    ```
    ### Context
    Fix stale edge filtering for missing target node
    
    ### Changes
    - **src/frontend/workflow/ui_converter.py**: Added source node check in `_build_workflow_edge()` to filter stale edges with missing source nodes
    - **tests/frontend/workflow/test_ui_converter.py**: Added regression tests for stale edge filtering scenarios
    ```
5. Create PR via `mcp--github--create_pull_request(base="mathieu/bugfix-reference-missing-target-node", ...)`
6. Report: "PR created: https://github.com/iar3-r8/Healthcare-Systems-R8/pull/47"

**Important Rules:**
- Always detect base branch from local git upstream tracking (`[origin/<branch>]`) shown in `git status`
- Use detected base branch for the PR, do not hardcode `main`
- Always match the PR title to the GitHub issue title
- Keep descriptions concise and focused on what changed
- Use relative file paths (e.g., `src/frontend/workflow/ui_converter.py`)
- Do not include test pass results in the description
- Do not include impact/results fields
- Use Git MCP server for all git operations (git_diff, git_log, git_status)
- Use GitHub MCP server for all GitHub operations (get_issue, create_pull_request)
