# REST API endpoints for GitHub Actions permissions — GitHub Docs

Source URL: https://docs.github.com/en/rest/actions/permissions
Fetched: 2026-11-05

Why this page is saved (it answers the question the issue #75 intake flagged as unresolved —
**which documented endpoint actually requires `administration: read`?**): the repository-level
Actions permissions endpoints are explicitly gated on the **"Administration" repository
permission**, and `GET /repos/{owner}/{repo}/actions/permissions` is a **read** at that level.
That makes it the administration-withheld probe endpoint, and it is read-only, so running it
against the real target mutates nothing.

This also confirms the intake's correction: `GET /repos/{owner}/{repo}/rulesets` needs only
`Metadata: read`
([`doc/external/github/rest-api-endpoints-for-rules.md`](rest-api-endpoints-for-rules.md)) and
is **not** an administration-level probe.

## The probe endpoint

### Get GitHub Actions permissions for a repository

Gets the GitHub Actions permissions policy for a repository, including whether GitHub Actions
is enabled and the actions and reusable workflows allowed to run in the repository.

OAuth tokens and personal access tokens (classic) need the `repo` scope to use this endpoint.

#### Fine-grained access tokens

This endpoint works with the following fine-grained token types:

* GitHub App user access tokens
* GitHub App installation access tokens
* Fine-grained personal access tokens

The fine-grained token must have the following permission set:

* **"Administration" repository permissions (read)**

Note this endpoint's page does **not** say "This endpoint can be used without authentication
if only public resources are requested" — unlike `GET /repos/{owner}/{repo}/actions/workflows`
on [`doc/external/github/rest-api-endpoints-for-workflows.md`](rest-api-endpoints-for-workflows.md),
which does carry that sentence.

#### Parameters

Path parameters:

| Name, Type, Description |
| --- |
| `owner` string Required — The account owner of the repository. The name is not case sensitive. |
| `repo` string Required — The name of the repository without the `.git` extension. The name is not case sensitive. |

#### HTTP response status codes

| Status code | Description |
| --- | --- |
| `200` | OK |

**Only `200` is documented.** The page lists no `403` and no `404` for this endpoint. What a
token lacking `Administration: read` receives is therefore **not documented on this page** —
GitHub's general behaviour for a fine-grained token outside its permission or repository scope
is `403` or `404`, but this page does not state which applies here. A probe must classify on
what it observes and must not assert an undocumented status code.

#### Request

```
get /repos/{owner}/{repo}/actions/permissions
```

```
curl -L \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  https://api.github.com/repos/OWNER/REPO/actions/permissions
```

#### Response

`Status: 200`

```json
{
  "enabled": true,
  "allowed_actions": "selected",
  "selected_actions_url": "https://api.github.com/repositories/42/actions/permissions/selected-actions",
  "sha_pinning_required": true
}
```

## Every repository-level endpoint on this page, with its fine-grained permission

The administration-level reads are the candidate probe endpoints; the writes are listed to
show what an `administration: write` grant would unlock — the danger the probe reports.

| Endpoint | Fine-grained permission |
| --- | --- |
| `GET /repos/{owner}/{repo}/actions/permissions` | "Administration" repository permissions (**read**) |
| `PUT /repos/{owner}/{repo}/actions/permissions` | "Administration" repository permissions (write) |
| `GET /repos/{owner}/{repo}/actions/permissions/access` | "Administration" repository permissions (read) |
| `PUT /repos/{owner}/{repo}/actions/permissions/access` | "Administration" repository permissions (write) |
| `GET /repos/{owner}/{repo}/actions/permissions/artifact-and-log-retention` | "Administration" repository permissions (read) |
| `PUT /repos/{owner}/{repo}/actions/permissions/artifact-and-log-retention` | "Administration" repository permissions (write) |
| `GET /repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval` | "Administration" repository permissions (read) |
| `PUT /repos/{owner}/{repo}/actions/permissions/fork-pr-contributor-approval` | "Administration" repository permissions (write) |
| `GET /repos/{owner}/{repo}/actions/permissions/fork-pr-workflows-private-repos` | "Administration" repository permissions (read) |
| `PUT /repos/{owner}/{repo}/actions/permissions/fork-pr-workflows-private-repos` | "Administration" repository permissions (write) |
| `GET /repos/{owner}/{repo}/actions/permissions/selected-actions` | "Administration" repository permissions (read) |
| `PUT /repos/{owner}/{repo}/actions/permissions/selected-actions` | "Administration" repository permissions (write) |
| `GET /repos/{owner}/{repo}/actions/permissions/workflow` | "Administration" repository permissions (read) |
| `PUT /repos/{owner}/{repo}/actions/permissions/workflow` | "Administration" repository permissions (write) |

The organization-level endpoints on the same page are gated on **"Administration"
organization permissions**, which a repo-scoped fine-grained PAT does not carry at all; they
are therefore not usable as a repository-token probe.

## What `administration: write` would let an agent do (the danger text's basis)

From the write endpoints above, an `administration: write` grant can set the repository's
Actions policy (`enabled`, `allowed_actions`, `sha_pinning_required`), set the default
`GITHUB_TOKEN` workflow permissions to `write`, and allow Actions to approve pull requests
(`can_approve_pull_request_reviews` — "Enabling this can be a security risk", in GitHub's own
words). Repository deletion is governed by the same Administration permission; see
[`doc/external/github/fine-grained-personal-access-tokens.md`](fine-grained-personal-access-tokens.md).
