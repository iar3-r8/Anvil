# Scopes for OAuth apps — GitHub Docs

Source URL: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
Fetched: 2026-11-05

Why this page is saved (it supplies the mechanism issue #75's probe 3 actually needs): the
scope list of a classic token is read from a **response header**, not a response body.
GitHub's own example is reproduced verbatim below:

```
$ curl -H "Authorization: Bearer OAUTH-TOKEN" https://api.github.com/users/codertocat -I
HTTP/2 200
X-OAuth-Scopes: repo, user
X-Accepted-OAuth-Scopes: user
```

* `X-OAuth-Scopes` lists the scopes your token has authorized.
* `X-Accepted-OAuth-Scopes` lists the scopes that the action checks for.

For the classic-vs-fine-grained probe this gives a header, `X-OAuth-Scopes`, whose
**presence and contents** are the discriminator. Together with
[`doc/external/github/rest-api-endpoints-for-users.md`](rest-api-endpoints-for-users.md) —
which shows the `GET /user` body has no `scopes` key at all — this page is the reason the
probe must read `response.headers`, not `json.loads(body)`.

Note the page documents what `X-OAuth-Scopes` means **when present**. It does not state
what a fine-grained PAT returns for that header; GitHub documents no `X-OAuth-Scopes`
semantics for fine-grained tokens anywhere on this page. A probe must therefore treat
**absent header** and **present-but-empty header** as distinct from **present and
non-empty**, and must not assert a fine-grained token yields any particular one of the
first two without observing it.

## The two scopes that matter to the Anvil design

| Name | Description |
| --- | --- |
| `repo` | Grants full access to public and private repositories including read and write access to code, commit statuses, repository invitations, collaborators, deployment statuses, and repository webhooks. **Note:** In addition to repository related resources, the `repo` scope also grants access to manage organization-owned resources including projects, invitations, team memberships and webhooks. This scope also grants the ability to manage projects owned by users. |
| `workflow` | Grants the ability to add and update GitHub Actions workflow files. Workflow files can be committed without this scope if the same file (with both the same path and contents) exists on another branch in the same repository. Workflow files can expose `GITHUB_TOKEN` which may have a different set of scopes. |

`(no scope)` grants read-only access to public information (including user profile info,
repository info, and gists).

## Full available-scope table

| Name | Description |
| --- | --- |
| `(no scope)` | Grants read-only access to public information (including user profile info, repository info, and gists) |
| `repo` | Full access to public and private repositories (see above). |
| `repo:status` | Grants read/write access to commit statuses in public and private repositories. |
| `repo_deployment` | Grants access to deployment statuses for public and private repositories. |
| `public_repo` | Limits access to public repositories. |
| `repo:invite` | Grants accept/decline abilities for invitations to collaborate on a repository. |
| `security_events` | Read and write access to security events in the code scanning API. |
| `admin:repo_hook` | Grants read, write, ping, and delete access to repository hooks. |
| `write:repo_hook` | Grants read, write, and ping access to hooks. |
| `read:repo_hook` | Grants read and ping access to hooks. |
| `admin:org` | Fully manage the organization and its teams, projects, and memberships. |
| `write:org` | Read and write access to organization membership and organization projects. |
| `read:org` | Read-only access to organization membership, organization projects, and team membership. |
| `admin:public_key` | Fully manage public keys. |
| `write:public_key` | Create, list, and view details for public keys. |
| `read:public_key` | List and view details for public keys. |
| `admin:org_hook` | Grants read, write, ping, and delete access to organization hooks. |
| `gist` | Grants write access to gists. |
| `notifications` | Read access to notifications, mark-as-read, watch/unwatch, thread subscriptions. |
| `user` | Grants read/write access to profile info only. Includes `user:email` and `user:follow`. |
| `read:user` | Grants access to read a user's profile data. |
| `user:email` | Grants read access to a user's email addresses. |
| `user:follow` | Grants access to follow or unfollow other users. |
| `project` | Grants read/write access to user and organization projects. |
| `read:project` | Grants read only access to user and organization projects. |
| `delete_repo` | Grants access to delete adminable repositories. |
| `write:packages` | Grants access to upload or publish a package in GitHub Packages. |
| `read:packages` | Grants access to download or install packages from GitHub Packages. |
| `delete:packages` | Grants access to delete packages from GitHub Packages. |
| `admin:gpg_key` | Fully manage GPG keys. |
| `write:gpg_key` | Create, list, and view details for GPG keys. |
| `read:gpg_key` | List and view details for GPG keys. |
| `codespace` | Grants the ability to create and manage codespaces. |
| `workflow` | Grants the ability to add and update GitHub Actions workflow files (see above). |
| `read:audit_log` | Read audit log data. |
| `offline_access` | Requests an expiring access token and a refresh token. |

## Normalized scopes

When requesting multiple scopes, the token is saved with a normalized list of scopes,
discarding those that are implicitly included by another requested scope. For example,
requesting `user,gist,user:email` will result in a token with `user` and `gist` scopes only
since the access granted with `user:email` scope is included in the `user` scope.

**Bearing on the probe:** the header's contents are normalized, so a classic token created
with `repo` reports `repo` and not its implied sub-scopes. A probe that matched an exact
scope string would be brittle; the honest discriminator is "the header is present and
non-empty", with the specific scopes reported verbatim in the finding.
