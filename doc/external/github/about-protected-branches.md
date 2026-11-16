# About protected branches

Source URL: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
Fetched: 2026-11-16 (oxylabs `universal_scraper`, output_format=md)

## Who can use this feature?
Protected branches are available in public repositories with GitHub Free and GitHub Free for organizations. Protected branches are also available in public and private repositories with GitHub Pro, GitHub Team, GitHub Enterprise Cloud, and GitHub Enterprise Server.

## About branch protection rules
Branch protection rules define whether collaborators can delete or force push to a branch and set requirements for any pushes, such as passing status checks or a linear commit history. By default, each branch protection rule disables force pushes and prevents deletion. By default the restrictions do not apply to people with admin permissions or custom roles with the "bypass branch protections" permission, unless enabled.

## Require pull request reviews before merging
Repository administrators or custom roles with the "edit repository rules" permission can require that all pull requests receive a specific number of approving reviews before someone merges the pull request into a protected branch. You can require approving reviews from people with write permissions in the repository or from a designated code owner.

- If a person with admin permissions chooses the **Request changes** option in a review, then that person must approve the pull request before the pull request can be merged. If a reviewer who requests changes isn't available, anyone with write permissions can dismiss the blocking review.
- **Require reviews from code owners** (optional): "any pull request that affects code with a code owner must be approved by that code owner before the pull request can be merged into the protected branch."
- **Require approval of the most recent reviewable push** (optional): "you can require that the most recent reviewable push must be approved by **someone other than the person who pushed it**. This means at least one other authorized reviewer has approved any changes." This is the option that blocks a code owner from approving their own most recent change.

(From the About code owners page, cross-reference): when reviews from code owners are required, an approval from *any* of the owners is sufficient to meet the requirement.

## Related settings (summary)
Require status checks before merging (strict/loose/disabled); require conversation resolution; require signed commits; require linear history; require merge queue; require deployments to succeed; lock branch; "Do not allow bypassing the above settings" (apply restrictions to admins too); restrict who can push; allow force pushes (off by default); allow deletions (off by default).

## The rulesets equivalent
The same options exist as ruleset `pull_request` parameters (see doc/external/github/rest-api-endpoints-for-rules.md): `required_approving_review_count`, `dismiss_stale_reviews_on_push`, `require_code_owner_review`, `require_last_push_approval`, `required_review_thread_resolution`, `allowed_merge_methods`. In the ruleset UI, "Require review from Code Owners" sits under "Require a pull request before merging".
