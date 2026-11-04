# REST API endpoints for pull requests — GitHub Docs

Source URL: https://docs.github.com/en/rest/pulls/pulls
Fetched: 2026-11-04

Why this page is saved (abridged to the one endpoint the phase-10 loop writes): delivery is
`POST /repos/{owner}/{repo}/pulls`, whose required body parameters are **`head` and `base`**,
with `title` required "unless `issue` is specified" and `body` optional — so the PR
description is a plain `body` string, built from the project's own pull-request shape rather
than from any GitHub template. Success is **`201`**, and the response carries `number` and
`html_url` (what a human opens) plus `head.sha` (the commit the CI read in the next step
keys on).

---

## Create a pull request

`POST /repos/{owner}/{repo}/pulls`

> To open or update a pull request in a public repository, you must have write access to the
> head or the source branch.
>
> This endpoint triggers notifications. Creating content too quickly using this endpoint may
> result in secondary rate limiting.

### Fine-grained access tokens for "Create a pull request"

The fine-grained token must have the following permission set:

* "Pull requests" repository permissions (write)

### Parameters

Headers

| Name, Type, Description |
| --- |
| `accept` string — Setting to `application/vnd.github+json` is recommended. |

Path parameters

| Name, Type, Description |
| --- |
| `owner` string Required — The account owner of the repository. The name is not case sensitive. |
| `repo` string Required — The name of the repository without the `.git` extension. |

Body parameters

| Name, Type, Description |
| --- |
| `title` string — The title of the new pull request. **Required unless `issue` is specified.** |
| `head` string **Required** — The name of the branch where your changes are implemented. For cross-repository pull requests in the same network, namespace `head` with a user like this: `username:branch`. |
| `head_repo` string — The name of the repository where the changes in the pull request were made. Required for cross-repository pull requests if both repositories are owned by the same organization. |
| `base` string **Required** — The name of the branch you want the changes pulled into. This should be an existing branch on the current repository. |
| `body` string — The contents of the pull request. |
| `maintainer_can_modify` boolean — Indicates whether maintainers can modify the pull request. |
| `draft` boolean — Indicates whether the pull request is a draft. |
| `issue` integer — An issue in the repository to convert to a pull request. The issue title, body, and comments will become the title, body, and comments on the new pull request. **Required unless `title` is specified.** |

### HTTP response status codes

| Status code | Description |
| --- | --- |
| `201` | Created |
| `403` | Forbidden |
| `422` | Validation failed, or the endpoint has been spammed. |

A `422` is what an already-open pull request for the same head/base, or a head branch that
was never pushed, answers with.

### Request example

```
curl -L \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/OWNER/REPO/pulls \
  -d '{"title":"Amazing new feature","body":"Please pull these awesome changes in!","head":"octocat:new-feature","base":"master"}'
```

### Response (abridged to the fields the loop reads)

`Status: 201`

```json
{
  "url": "https://api.github.com/repos/octocat/Hello-World/pulls/1347",
  "id": 1,
  "html_url": "https://github.com/octocat/Hello-World/pull/1347",
  "issue_url": "https://api.github.com/repos/octocat/Hello-World/issues/1347",
  "number": 1347,
  "state": "open",
  "title": "Amazing new feature",
  "body": "Please pull these awesome changes in!",
  "head": {
    "label": "octocat:new-topic",
    "ref": "new-topic",
    "sha": "6dcb09b5b57875f334f61aebed695e2e4193db5e"
  },
  "base": {
    "label": "octocat:master",
    "ref": "master",
    "sha": "6dcb09b5b57875f334f61aebed695e2e4193db5e"
  },
  "draft": false,
  "merged": false,
  "mergeable": true
}
```

`head.sha` is "the most recent commit on the pull request's branch" — the value the Actions
run lookup filters on as `head_sha`.

## Get a pull request (adjacent, not used by this slice)

`GET /repos/{owner}/{repo}/pulls/{pull_number}` — "Pull requests" read **or** "Contents"
read; `200`, `304`, `404`, `406`, `422`, `500`, `503`. `mergeable` may be `null` while
GitHub computes it in the background. The phase-10 loop does not poll mergeability.
