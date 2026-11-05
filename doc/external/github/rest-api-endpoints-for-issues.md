# REST API endpoints for issues — GitHub Docs

Source URL: https://docs.github.com/en/rest/issues/issues
Fetched: 2026-11-04

Why this page is saved (abridged to the one endpoint the intake loop reads): the run's
**intake** is an issue, read with `GET /repos/{owner}/{repo}/issues/{issue_number}` on a
fine-grained token carrying **Issues: read** — which the repo-scoped token already has at
`write`, and `write` includes `read`. The response fields the loop consumes are `number`,
`title` and `body`; `body` is the untrusted text that must reach the model as quoted data.
The status codes matter because every one of them becomes a `reason` string rather than an
exception: a transferred issue answers `301`, a deleted-but-readable one `410`, and an
unreadable one `404`.

---

## Get an issue

`GET /repos/{owner}/{repo}/issues/{issue_number}`

> The API returns a `301 Moved Permanently` status if the issue was transferred to another
> repository. If the issue was transferred to or deleted from a repository where the
> authenticated user lacks read access, the API returns a `404 Not Found` status. If the
> issue was deleted from a repository where the authenticated user has read access, the API
> returns a `410 Gone` status.

> Note: GitHub's REST API considers every pull request an issue, but not every issue is a
> pull request. For this reason, "Issues" endpoints may return both issues and pull requests
> in the response. You can identify pull requests by the `pull_request` key.

### Fine-grained access tokens for "Get an issue"

The fine-grained token must have the following permission set:

* "Issues" repository permissions (read)

This endpoint can be used without authentication or the aforementioned permissions if only
public resources are requested.

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
| `issue_number` integer Required — The number that identifies the issue. |

### HTTP response status codes

| Status code | Description |
| --- | --- |
| `200` | OK |
| `301` | Moved permanently |
| `304` | Not modified |
| `404` | Resource not found |
| `410` | Gone |

### Request example

```
curl -L \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/OWNER/REPO/issues/ISSUE_NUMBER
```

### Response (abridged to the fields the loop reads)

`Status: 200`

```json
{
  "id": 1,
  "node_id": "MDU6SXNzdWUx",
  "url": "https://api.github.com/repos/octocat/Hello-World/issues/1347",
  "html_url": "https://github.com/octocat/Hello-World/issues/1347",
  "number": 1347,
  "state": "open",
  "title": "Found a bug",
  "body": "I'm having a problem with this.",
  "comments": 0,
  "pull_request": {
    "url": "https://api.github.com/repos/octocat/Hello-World/pulls/1347",
    "html_url": "https://github.com/octocat/Hello-World/pull/1347"
  },
  "created_at": "2011-04-22T13:33:48Z",
  "updated_at": "2011-04-22T13:33:48Z",
  "author_association": "COLLABORATOR",
  "state_reason": "completed"
}
```

The full response additionally carries `user`, `labels`, `assignee`, `assignees`,
`milestone`, `locked`, `active_lock_reason`, `closed_at`, `closed_by`, `repository_url`,
`labels_url`, `comments_url`, `events_url` and `pinned_comment`. None of them is read by
the intake loop.
