# REST API endpoints for workflows — GitHub Docs

Source URL: https://docs.github.com/en/rest/actions/workflows
Fetched: 2026-11-05

Why this page is saved (it **refutes** the probe the issue #75 body proposed): the issue
suggests "a `workflows`-level call on the target (e.g. list workflows)". This page shows
that is wrong. **`GET /repos/{owner}/{repo}/actions/workflows` requires "Actions" repository
permissions (read) — not `workflows`.** The recipe in the same issue *grants* `actions=read`,
so a compliant Anvil token would get `200` from that call, which the proposed probe would
score as a `fail`. The probe as written would fail every correctly-created token.

Worse for the probe: the page states this endpoint "can be used without authentication or
the aforementioned permissions if only public resources are requested", so on a public
target repository even a zero-permission token gets `200`.

**There is no read endpoint gated on the `workflows` permission.** The permission table in
[`doc/external/github/fine-grained-personal-access-tokens.md`](fine-grained-personal-access-tokens.md)
lists `workflows` with access levels **`write` only** — it has no `read` form. `workflows`
governs *adding and updating workflow files*, which is a write path reached through the
Contents API, not through a readable Actions endpoint. A read-only probe therefore cannot
establish that `workflows` is withheld: the only call that would prove it is a write, which
the probes must not perform.

Under the #68 rule — a check that cannot run is `skipped`, never `passed` — the workflows
withholding is **unprovable read-only** and must be reported as `skipped` with that reason,
not as a passing probe.

## List repository workflows

Lists the workflows in a repository.

Anyone with read access to the repository can use this endpoint.

OAuth app tokens and personal access tokens (classic) need the `repo` scope to use this
endpoint with a private repository.

### Fine-grained access tokens for "List repository workflows"

This endpoint works with the following fine-grained token types:

* GitHub App user access tokens
* GitHub App installation access tokens
* Fine-grained personal access tokens

The fine-grained token must have the following permission set:

* **"Actions" repository permissions (read)**

**This endpoint can be used without authentication or the aforementioned permissions if only
public resources are requested.**

### HTTP response status codes

| Status code | Description |
| --- | --- |
| `200` | OK |

### Request

```
get /repos/{owner}/{repo}/actions/workflows
```

### Response

`Status: 200`

```json
{
  "total_count": 2,
  "workflows": [
    {
      "id": 161335,
      "node_id": "MDg6V29ya2Zsb3cxNjEzMzU=",
      "name": "CI",
      "path": ".github/workflows/blank.yaml",
      "state": "active",
      "created_at": "2020-01-08T23:48:37.000-08:00",
      "updated_at": "2020-01-08T23:50:21.000-08:00",
      "url": "https://api.github.com/repos/octo-org/octo-repo/actions/workflows/161335",
      "html_url": "https://github.com/octo-org/octo-repo/blob/master/.github/workflows/161335",
      "badge_url": "https://github.com/octo-org/octo-repo/workflows/CI/badge.svg"
    }
  ]
}
```

## Every endpoint on this page, with its fine-grained permission

Not one of them names `workflows`. The reads are "Actions" read; the state-changing calls are
"Actions" write.

| Endpoint | Fine-grained permission | Unauthenticated on public repos? |
| --- | --- | --- |
| `GET /repos/{owner}/{repo}/actions/workflows` | "Actions" repository permissions (read) | yes |
| `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}` | "Actions" repository permissions (read) | yes |
| `PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/disable` | "Actions" repository permissions (write) | no |
| `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` | "Actions" repository permissions (write) | no |
| `PUT /repos/{owner}/{repo}/actions/workflows/{workflow_id}/enable` | "Actions" repository permissions (write) | no |
| `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/timing` | "Actions" repository permissions (read) | yes |

`GET …/timing` ("Get workflow usage") carries a closing-down warning: "This endpoint is in
the process of closing down."

## The consequence for the Anvil recipe

`actions=read` is the permission that makes CI logs readable, and this page confirms it is
also what makes the workflow list readable. It does **not** open the CI *edit* path: that
needs "Actions" write for enable/disable/dispatch, or the `workflows` permission for editing
the workflow files themselves. Both stay withheld under the recipe.
