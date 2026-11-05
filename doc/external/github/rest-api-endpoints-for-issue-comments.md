# REST API endpoints for issue comments — GitHub Docs

Source URL: https://docs.github.com/en/rest/issues/comments
Fetched: 2026-11-04

Why this page is saved (abridged to the one endpoint the intake loop writes): progress is
posted with `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`, whose **only**
required body parameter is `body` (a string) and whose success code is **`201`, not `200`** —
so a driver that treats 200 as success would silently never see its own comment land. The
same endpoint serves pull requests, because every pull request is an issue. The explicit
secondary-rate-limit warning is why progress comments are few and short rather than chatty.

---

## About issue and pull request comments

> You can use the REST API to create and manage comments on issues and pull requests. Every
> pull request is an issue, but not every issue is a pull request. For this reason, "shared"
> actions for both features, like managing assignees, labels, and milestones, are provided
> within the Issues endpoints.

## Create an issue comment

`POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

> You can use the REST API to create comments on issues and pull requests. Every pull request
> is an issue, but not every issue is a pull request.
>
> This endpoint triggers notifications. **Creating content too quickly using this endpoint may
> result in secondary rate limiting.**

### Fine-grained access tokens for "Create an issue comment"

The fine-grained token must have at least one of the following permission sets:

* "Issues" repository permissions (write)
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
| `issue_number` integer Required — The number that identifies the issue. |

Body parameters

| Name, Type, Description |
| --- |
| `body` string **Required** — The contents of the comment. |

`body` is the only body parameter. There is no title, no author and no type field.

### HTTP response status codes

| Status code | Description |
| --- | --- |
| `201` | Created |
| `403` | Forbidden |
| `404` | Resource not found |
| `410` | Gone |
| `422` | Validation failed, or the endpoint has been spammed. |

### Request example

```
curl -L \
  -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/OWNER/REPO/issues/ISSUE_NUMBER/comments \
  -d '{"body":"Me too"}'
```

### Response (abridged to the fields the loop reads)

`Status: 201`

```json
{
  "id": 1,
  "node_id": "MDEyOklzc3VlQ29tbWVudDE=",
  "url": "https://api.github.com/repos/octocat/Hello-World/issues/comments/1",
  "html_url": "https://github.com/octocat/Hello-World/issues/1347#issuecomment-1",
  "body": "Me too",
  "created_at": "2011-04-14T16:00:49Z",
  "updated_at": "2011-04-14T16:00:49Z",
  "issue_url": "https://api.github.com/repos/octocat/Hello-World/issues/1347",
  "author_association": "COLLABORATOR"
}
```

## List issue comments (adjacent, not used by the intake loop)

`GET /repos/{owner}/{repo}/issues/{issue_number}/comments` — "Issues" read **or** "Pull
requests" read; `200`, `404`, `410`. Comments are ordered by ascending ID. Not consumed by
the intake loop, which writes progress rather than re-reading it.
