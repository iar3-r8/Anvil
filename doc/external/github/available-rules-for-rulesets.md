# Available rules for rulesets — GitHub Docs

Source URL: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
Fetched: 2026-10-20

Why this page is saved (abridged to the rules that bear on an autonomous agent): it answers
"can we block critical git/GitHub operations?" — yes, and server-side, which is the only
place a guard cannot be argued around by the agent. The load-bearing facts: **Block force
pushes** "is enabled by default"; **Restrict deletions** "is selected by default";
**Restrict updates** means only bypass-holders can push to matching branches, so `main`
can be made unpushable while feature branches stay writable; **Require a pull request
before merging** forces every change through review; and **Restrict file paths** can block
pushes touching specified paths entirely (200 entries max, `fnmatch` syntax) — which is how
`.github/workflows/**` or `.roo/**` could be fenced off. Availability caveat: rulesets are
available in public repositories on Free, and in public and private repositories on Pro,
Team and Enterprise Cloud.

---

You can create branch or tag rulesets to control how users can interact with selected branches and tags in a repository. You can also create push rulesets to block pushes to a private or internal repository and that repository's entire fork network.

When you create a ruleset, you can allow certain users to bypass the rules in the ruleset. This can be users with certain roles, specific teams, or GitHub Apps.

Rulesets are available in public repositories with GitHub Free and GitHub Free for organizations, and in public and private repositories with GitHub Pro, GitHub Team, and GitHub Enterprise Cloud.

Push rulesets are available for the GitHub Team plan in internal and private repositories, and forks of repositories that have push rulesets enabled.

## Restrict creations

If selected, only users with bypass permissions can create branches or tags whose name matches the pattern you specify.

## Restrict updates

If selected, only users with bypass permissions can push to branches or tags whose name matches the pattern you specify.

## Restrict deletions

If selected, only users with bypass permissions can delete branches or tags whose name matches the pattern you specify. **This rule is selected by default.**

## Require linear history

Enforcing a linear commit history prevents collaborators from pushing merge commits to the targeted branches or tags. This means that any pull requests merged into the branch or tag must use a squash merge or a rebase merge.

## Require deployments to succeed before merging

You can require that changes are successfully deployed to specific environments before a branch can be merged.

## Require signed commits

When you enable required commit signing on a branch, contributors and bots can only push commits that have been signed and verified to the branch.

With rulesets, we check only the commits that aren't accessible from other branches, whereas with branch protection rules, we do not verify signed commits unless you restrict pushes that create matching branches.

If a collaborator pushes an unsigned commit to a branch that requires commit signatures, the collaborator will need to rebase the commit to include a verified signature, then force push the rewritten commit to the branch.

## Require a pull request before merging

You can require that all changes to the target branch be associated with a pull request. The pull request doesn't necessarily have to be approved, but it must be opened.

### Additional settings (abridged)

Repository administrators or custom roles with the "edit repository rules" permission can require that all pull requests receive a specific number of approving reviews before someone merges the pull request into a protected branch. You can require approving reviews from people with write permissions in the repository or from a designated code owner.

If you enable required reviews, collaborators can only push changes to a branch via a pull request that is approved by the required number of reviewers with write permissions.

Optionally, you can choose to dismiss stale pull request approvals when commits are pushed that affect the diff in the pull request.

Optionally, you can require an approval from someone other than the last person to push to a branch before a pull request can be merged.

Optionally, you can require all comments on the pull request to be resolved before it can be merged to a branch.

#### Additional approval for unattributed Copilot pull requests

> Note: This feature is in public preview and subject to change.

**Require an additional approval for unattributed Copilot pull requests** is enabled by default, for both new and existing rulesets. When Copilot opens a pull request that isn't attributed to a person, the ruleset requires one more approval than the number you configured.

Requiring one approval usually means two people are involved in a change: the person who wrote it and the person who approved it. That assumption doesn't hold when Copilot opens a pull request under its own app identity instead of on behalf of a person.

#### Required reviewers

Optionally, you can require review or approval from specific teams when a pull request changes certain files or directories. You can specify up to 15 different teams, and for each team you can require a certain number of approvals from team members.

For each team, you can specify a list of file patterns which determines what files the setting applies to. The format of this file list is the same as a standard `.gitignore` file.

## Require status checks to pass before merging

Required status checks ensure that all required CI tests are passing before collaborators can make changes to a branch or tag targeted by your ruleset. Required status checks can be checks or statuses.

After enabling required status checks, all required status checks must pass before collaborators can merge changes into the branch or tag.

Any person or integration with write permissions to a repository can set the state of any status check in the repository, but in some cases you may only want to accept a status check from a specific GitHub App.

| Type of required status check | Setting | Merge requirements |
| --- | --- | --- |
| **Strict** | The **Require branches to be up to date before merging** checkbox is checked. | The topic branch **must** be up to date with the base branch before merging. |
| **Loose** | The checkbox is **not** checked. | The branch **does not** have to be up to date with the base branch before merging. |
| **Disabled** | **Require status checks to pass before merging** is **not** checked. | The branch has no merge restrictions. |

## Block force pushes

You can prevent users from force pushing to the targeted branches or tags. **This rule is enabled by default.**

If someone force pushes to a branch or tag, commits that other collaborators have based their work on may be removed from the history of the branch or tag. This may lead to merge conflicts or corrupted pull requests. Force pushing can also be used to delete branches or point a branch to commits that were not approved in a pull request.

> Note: If force pushes are blocked, organization owners or repository administrators will be unable to change or rename the default branch unless they are authorized to bypass the ruleset.

Enabling force pushes will not override any other rules. For example, if a branch requires a linear commit history, you cannot force push merge commits to that branch.

## Require secret scanning alerts are resolved

> Note: in public preview and subject to change.

If your repositories use secret scanning, you can prevent a pull request from merging when either of these conditions applies:

* A secret scanning scan has not completed for the head commit of the pull request.
* A commit in the pull request introduced an open secret scanning alert that matches a secret type selected in the ruleset.

## Require code scanning results

If your repositories are configured with code scanning, you can use rulesets to prevent pull requests from being merged when a required tool finds an alert of a defined severity, analysis is still in progress, or a required tool is not configured.

## Require code quality results

If your repositories are configured with GitHub Code Quality, you can prevent merges when analysis is in progress, analysis fails, or a result meets the defined severity.

## Require license compliance results before merging

License compliance checks added or changed dependencies against a policy of permitted licenses and will block pull requests which add dependencies whose licenses are not allowed.

## Restrict code coverage

> Note: in public preview and subject to change.

Blocks a pull request when the aggregated line coverage is below a configured percentage, or line coverage drops by more than a configured number of percentage points relative to the default branch.

## Restrict file paths

Prevent commits that include changes in specified file paths from being pushed to the repository. Limit is 200 entries and up to 200 characters in each entry.

You can use `fnmatch` syntax for this. For example, a restriction targeting `test/demo/**/*` prevents any pushes to files or folders in the `test/demo/` directory. A restriction targeting `test/docs/pushrules.md` prevents pushes specifically to the `pushrules.md` file.

You can also add allowed exceptions to this rule. A file matching an allowed exception can be pushed even when it also matches a restricted path.

## Restrict file path length

Prevent commits that include file paths that exceed a specified character limit from being pushed to the repository.

## Restrict file extensions

Prevent commits that include files with specified file extensions from being pushed to the repository. Limit is 200 entries and up to 200 characters in each entry.

## Restrict file size

Prevent commits that exceed a specified file size limit from being pushed to the repository. You can also add allowed exceptions.
