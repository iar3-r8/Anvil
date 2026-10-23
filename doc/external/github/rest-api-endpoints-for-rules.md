# REST API endpoints for rules — GitHub Docs

Source: https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28
Fetched: 2026-10-22 (Oxylabs universal scraper, rendered)

Use the REST API to manage rulesets for repositories. Rulesets control how people can
interact with selected branches and tags in a repository.

---

## The two findings that decide the design

**1. Reading the effective rules needs only `Metadata: read`.** Both
`GET /repos/{owner}/{repo}/rules/branches/{branch}` and
`GET /repos/{owner}/{repo}/rulesets` state the same requirement:

> The fine-grained token must have the following permission set:
> * "Metadata" repository permissions (read)
>
> This endpoint can be used without authentication or the aforementioned permissions if
> only public resources are requested.

Only the mutating endpoints (create, update, delete) and the history endpoints require
`Administration`. So a verification-only check needs no new token scope — `metadata:
read` is implicit on every fine-grained token
(`doc/external/github/fine-grained-personal-access-tokens.md`).

**2. `rules/branches/{branch}` answers "is this branch actually protected", not "does a
ruleset exist".** Its own description:

> Returns all active rules that apply to the specified branch. The branch does not need
> to exist; rules that would apply to a branch with that name will be returned. All
> active rules that apply will be returned, regardless of the level at which they are
> configured (e.g. repository or organization). Rules in rulesets with "evaluate" or
> "disabled" enforcement statuses are not returned.

Three consequences: org-level rulesets are included, so a repo protected from above is
not reported as unprotected; a ruleset left at `evaluate` or `disabled` is correctly
absent, which is the "believed-on, actually-off" case issue #50 warns about; and the
branch need not exist, so the check works before `main` has commits.

---

## Get rules for a branch

`GET /repos/{owner}/{repo}/rules/branches/{branch}`

### Parameters

| Kind | Name | Notes |
|---|---|---|
| Header | `accept` | `application/vnd.github+json` recommended |
| Path | `owner` | Required. Not case sensitive. |
| Path | `repo` | Required. Without the `.git` extension. |
| Path | `branch` | Required. **Cannot contain wildcard characters** — for wildcards use the GraphQL API. |
| Query | `per_page` | Max 100, default 30 |
| Query | `page` | Default 1 |

### Status codes

| Status code | Description |
|---|---|
| `200` | OK |

Note there is no documented 404 for this endpoint — a repository with no rules returns
`200` with an empty array.

### Request

```
curl -L \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/OWNER/REPO/rules/branches/BRANCH
```

### Example response

```json
[
  {
    "type": "commit_message_pattern",
    "ruleset_source_type": "Repository",
    "ruleset_source": "monalisa/my-repo",
    "ruleset_id": 42,
    "parameters": { "operator": "starts_with", "pattern": "issue" }
  },
  {
    "type": "commit_author_email_pattern",
    "ruleset_source_type": "Organization",
    "ruleset_source": "my-org",
    "ruleset_id": 73,
    "parameters": { "operator": "contains", "pattern": "github" }
  }
]
```

Each element carries `type`, `ruleset_source_type` (`Repository` or `Organization`),
`ruleset_source`, `ruleset_id` and a rule-specific `parameters` object. **Matching is on
the `type` string.**

---

## Get all repository rulesets

`GET /repos/{owner}/{repo}/rulesets`

Permission: `Metadata: read`. Query parameters include `includes_parents` (boolean,
**default `true`** — include rulesets configured at higher levels) and `targets` (a
comma-separated list such as `branch,tag,push`).

Status codes: `200` OK, `404` Resource not found, `500` Internal Error.

Returns ruleset summaries — `id`, `name`, `source_type`, `source`, `enforcement`,
`node_id`, `_links`, `created_at`, `updated_at`. **The summary carries `enforcement` but
not `rules`**, so determining which rules are in force requires either
`rules/branches/{branch}` or a per-ruleset fetch.

`enforcement` is one of `disabled`, `active`, `evaluate` — and `evaluate` "allows admins
to test rules before enforcing them" and is "only available with GitHub Enterprise".

---

## Rule type names

The rule `type` strings relevant to an agent-safety check, taken from the create/update
body parameter documentation:

| `type` | What it does (GitHub's wording) |
|---|---|
| `non_fast_forward` | "Prevent users with push access from force pushing to refs." |
| `deletion` | "Only allow users with bypass permissions to delete matching refs." |
| `update` | "Only allow users with bypass permission to update matching refs." Takes `parameters.update_allows_fetch_and_merge` (boolean, required). |
| `creation` | "Only allow users with bypass permission to create matching refs." |
| `pull_request` | "Require all commits be made to a non-target branch and submitted via a pull request before they can be merged." Parameters include `required_approving_review_count`, `dismiss_stale_reviews_on_push`, `require_code_owner_review`, `require_last_push_approval`, `required_review_thread_resolution`, `allowed_merge_methods`. |
| `file_path_restriction` | "Prevent commits that include changes in specified file and folder paths from being pushed to the commit graph." Takes `parameters.restricted_file_paths` (array of strings, required). |
| `required_signatures` | "Commits pushed to matching refs must have verified signatures." |
| `required_linear_history` | "Prevent merge commits from being pushed to matching refs." |
| `required_status_checks` | "Choose which status checks must pass before the ref is updated." |
| `file_extension_restriction` | Takes `parameters.restricted_file_extensions`. |
| `max_file_size` | Takes `parameters.max_file_size` in megabytes. |

**Naming caution:** the UI label "Block force pushes" is `non_fast_forward` in the API,
and "Restrict updates" is `update`. The API name is what a response carries.

---

## Mutating endpoints — Administration: write

| Endpoint | Method | Permission | Status codes |
|---|---|---|---|
| `/repos/{owner}/{repo}/rulesets` | POST | `Administration` (write) | 201, 404, 422, 500 |
| `/repos/{owner}/{repo}/rulesets/{ruleset_id}` | GET | `Metadata` (read) | 200, 404, 500 |
| `/repos/{owner}/{repo}/rulesets/{ruleset_id}` | PUT | `Administration` (write) | 200, 404, 422, 500 |
| `/repos/{owner}/{repo}/rulesets/{ruleset_id}` | DELETE | `Administration` (write) | 204, 404, 500 |
| `/repos/{owner}/{repo}/rulesets/{ruleset_id}/history` | GET | `Administration` (write) | 200, 404, 500 |

On `GET /rulesets/{ruleset_id}`:

> **Note:** To prevent leaking sensitive information, the `bypass_actors` property is
> only returned if the user making the API request has write access to the ruleset.

So a read-only token can confirm a rule is present but **cannot see who may bypass it** —
a gap worth stating rather than silently reporting "protected".

### Create body shape, for reference

`name` (required), `target` (`branch` | `tag` | `push`, default `branch`), `enforcement`
(required, one of `disabled` | `active` | `evaluate`), `bypass_actors`, `conditions`,
`rules`.

`conditions.ref_name.include` accepts ref names or patterns, "Also accepts
`~DEFAULT_BRANCH` to include the default branch or `~ALL` to include all branches", and
`conditions.ref_name.exclude` where "The condition will not pass if any of these patterns
match".

```
curl -L -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/OWNER/REPO/rulesets \
  -d '{"name":"super cool ruleset","target":"branch","enforcement":"active",
       "conditions":{"ref_name":{"include":["refs/heads/main"],"exclude":[]}},
       "rules":[{"type":"non_fast_forward"}]}'
```
