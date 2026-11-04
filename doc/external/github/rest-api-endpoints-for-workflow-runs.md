# REST API endpoints for workflow runs — GitHub Docs

Source URL: https://docs.github.com/en/rest/actions/workflow-runs
Fetched: 2026-11-04

Why this page is saved (abridged to the one endpoint the phase-10 loop reads): the run
reports the CI outcome of the pull request it just opened by listing
`GET /repos/{owner}/{repo}/actions/runs` filtered by **`head_sha`** — the commit SHA the
create-PR response returned — on **Actions: read**. Two facts decide the whole behaviour:
the response is an **envelope**, `{"total_count": N, "workflow_runs": [...]}`, not a bare
array (unlike the rules endpoint `piguard` reads); and `status` and `conclusion` are two
different fields, with **`conclusion` `null` until `status` is `completed`** — so "the CI
passed" is `status == "completed" and conclusion == "success"`, and an in-progress run is
pending, not a failure.

Every write endpoint on this page — re-run, cancel, delete, delete-logs — requires
**Actions: write**, which the phase-10 token does not carry. Read-only is sufficient for
this slice and the CI edit path stays closed.

---

## List workflow runs for a repository

`GET /repos/{owner}/{repo}/actions/runs`

> Lists all workflow runs for a repository. You can use parameters to narrow the list of
> results. Anyone with read access to the repository can use this endpoint.
>
> This endpoint will return up to 1,000 results for each search when using the following
> parameters: `actor`, `branch`, `check_suite_id`, `created`, `event`, `head_sha`, `status`.

### Fine-grained access tokens for "List workflow runs for a repository"

The fine-grained token must have the following permission set:

* "Actions" repository permissions (**read**)

This endpoint can be used without authentication or the aforementioned permissions if only
public resources are requested.

### Parameters

Path parameters

| Name, Type, Description |
| --- |
| `owner` string Required — The account owner of the repository. |
| `repo` string Required — The name of the repository without the `.git` extension. |

Query parameters (abridged)

| Name, Type, Description |
| --- |
| `head_sha` string — Only returns workflow runs that are associated with the specified `head_sha`. |
| `branch` string — Returns workflow runs associated with a branch. Use the name of the branch of the `push`. |
| `status` string — Returns workflow runs with the check run `status` or `conclusion` that you specify. Can be one of: `completed`, `action_required`, `cancelled`, `failure`, `neutral`, `skipped`, `stale`, `success`, `timed_out`, `in_progress`, `queued`, `requested`, `waiting`, `pending` |
| `event` string — Returns workflow run triggered by the event you specify, e.g. `push`, `pull_request`. |
| `per_page` integer — Results per page (max 100). Default: `30` |
| `page` integer — Page number. Default: `1` |
| `exclude_pull_requests` boolean — If `true` pull requests are omitted from the response (empty array). Default: `false` |

### HTTP response status codes

| Status code | Description |
| --- | --- |
| `200` | OK |

A repository with no Actions runs for that SHA answers `200` with `total_count: 0` and an
empty `workflow_runs` array — not a `404`.

### Request example

```
curl -L \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR-TOKEN>" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/OWNER/REPO/actions/runs
```

### Response (abridged to the fields the loop reads)

`Status: 200`

```json
{
  "total_count": 1,
  "workflow_runs": [
    {
      "id": 30433642,
      "name": "Build",
      "head_branch": "master",
      "head_sha": "acb5820ced9479c074f688cc328bf03f341a511d",
      "path": ".github/workflows/build.yml@main",
      "run_number": 562,
      "event": "push",
      "display_title": "Update README.md",
      "status": "queued",
      "conclusion": null,
      "workflow_id": 159038,
      "url": "https://api.github.com/repos/octo-org/octo-repo/actions/runs/30433642",
      "html_url": "https://github.com/octo-org/octo-repo/actions/runs/30433642",
      "run_attempt": 1,
      "run_started_at": "2020-01-22T19:33:08Z",
      "jobs_url": "https://api.github.com/repos/octo-org/octo-repo/actions/runs/30433642/jobs",
      "logs_url": "https://api.github.com/repos/octo-org/octo-repo/actions/runs/30433642/logs"
    }
  ]
}
```

Note the queued example: `status` is `"queued"` and `conclusion` is `null`. The
`conclusion` field only carries a verdict once the run has completed.

## Get a workflow run (adjacent, not used by this slice)

`GET /repos/{owner}/{repo}/actions/runs/{run_id}` — Actions **read**; `200`. Returns one
run object with the same `status`/`conclusion` pair, no envelope. The phase-10 loop lists by
`head_sha` instead, because it knows the SHA it pushed but not the run id.

## Download workflow run logs (adjacent, not used by this slice)

`GET /repos/{owner}/{repo}/actions/runs/{run_id}/logs` — Actions **read**; answers **`302`**
with a `Location:` header to an archive URL that "expires after 1 minute". Fetching the log
archive is not part of this slice, which reports the run's conclusion rather than its text.

## Write endpoints (withheld by the phase-10 token)

Re-run a workflow, re-run failed jobs, re-run a job, cancel, force-cancel, approve a fork
run, delete a run and delete run logs **all require "Actions" repository permissions
(write)**. The phase-10 token grants Actions `read` only.
