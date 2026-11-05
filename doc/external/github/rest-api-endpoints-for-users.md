# REST API endpoints for users — GitHub Docs

Source URL: https://docs.github.com/en/rest/users/users
Fetched: 2026-11-05

Why this page is saved (abridged to the parts that decide the classic-vs-fine-grained probe
of issue #75): it is the authoritative reference for `GET /user`, and it establishes a
**negative** fact that the issue's probe 3 depends on — **the `GET /user` response body has
no `scopes` field.** The full documented example response is reproduced verbatim below and
contains no such key; neither the public nor the private user response carries one. A probe
that reads `payload["scopes"]` would therefore read `None` against every token, classic and
fine-grained alike, and could never distinguish them.

The scope list travels in a **response header**, `X-OAuth-Scopes`, documented on
[`doc/external/github/scopes-for-oauth-apps.md`](scopes-for-oauth-apps.md) — not in this
endpoint's body.

Two further facts that bear on the probe:

* **The fine-grained token does not require any permissions** for `GET /user`, so the probe
  runs against a minimally-scoped token rather than needing a permission the recipe withholds.
* Documented status codes are `200`, `304`, `401` (requires authentication) and `403`
  (forbidden). An unauthenticated call is therefore `401`, not `200`.

---

## Get the authenticated user

OAuth app tokens and personal access tokens (classic) need the `read:user` scope, or the
broader `user` scope, for this endpoint to return the private user response. The private user
response includes additional fields such as `private_gists`, `total_private_repos`,
`owned_private_repos`, `disk_usage`, `collaborators`, and `two_factor_authentication`. Tokens
without these scopes receive the public user response.

The private and public user response types are unrelated to the private profile setting. A
token without scopes still authenticates as the token's owner, so values subject to private
profile visibility, such as `followers` and `following`, may differ from an unauthenticated
response.

For enterprise-managed users, if their email is unverified, this endpoint will return a
placeholder email in the format `email+shortcode@domain.com` instead of their actual email.

### Fine-grained access tokens for "Get the authenticated user"

This endpoint works with the following fine-grained token types:

* GitHub App user access tokens
* Fine-grained personal access tokens

**The fine-grained token does not require any permissions.**

### HTTP response status codes for "Get the authenticated user"

| Status code | Description |
| --- | --- |
| `200` | OK |
| `304` | Not modified |
| `401` | Requires authentication |
| `403` | Forbidden |

### Request

```
get /user
```

```
curl -L \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  https://api.github.com/user
```

### Response with public and private profile information

`Status: 200`

```json
{
  "login": "octocat",
  "id": 1,
  "node_id": "MDQ6VXNlcjE=",
  "avatar_url": "https://github.com/images/error/octocat_happy.gif",
  "gravatar_id": "",
  "url": "https://api.github.com/users/octocat",
  "html_url": "https://github.com/octocat",
  "followers_url": "https://api.github.com/users/octocat/followers",
  "following_url": "https://api.github.com/users/octocat/following{/other_user}",
  "gists_url": "https://api.github.com/users/octocat/gists{/gist_id}",
  "starred_url": "https://api.github.com/users/octocat/starred{/owner}{/repo}",
  "subscriptions_url": "https://api.github.com/users/octocat/subscriptions",
  "organizations_url": "https://api.github.com/users/octocat/orgs",
  "repos_url": "https://api.github.com/users/octocat/repos",
  "events_url": "https://api.github.com/users/octocat/events{/privacy}",
  "received_events_url": "https://api.github.com/users/octocat/received_events",
  "type": "User",
  "site_admin": false,
  "name": "monalisa octocat",
  "company": "GitHub",
  "blog": "https://github.com/blog",
  "location": "San Francisco",
  "email": "octocat@github.com",
  "hireable": false,
  "bio": "There once was...",
  "twitter_username": "monatheoctocat",
  "public_repos": 2,
  "public_gists": 1,
  "followers": 20,
  "following": 0,
  "created_at": "2008-01-14T04:33:35Z",
  "updated_at": "2008-01-14T04:33:35Z",
  "private_gists": 81,
  "total_private_repos": 100,
  "owned_private_repos": 100,
  "disk_usage": 10000,
  "collaborators": 8,
  "two_factor_authentication": true,
  "plan": {
    "name": "Medium",
    "space": 400,
    "private_repos": 20,
    "collaborators": 0
  }
}
```

**Note for issue #75:** no `scopes` key appears anywhere in the documented response. This is
the whole of the documented `200` body.

## Other endpoints on this page (abridged)

| Endpoint | Fine-grained permission | Note |
| --- | --- | --- |
| `PATCH /user` (Update the authenticated user) | "Profile" user permissions (write) | A write; not used by the probes. |
| `GET /user/{account_id}` (Get a user using their ID) | none required | Works unauthenticated for public resources. |
| `GET /users` (List users) | none required | Works unauthenticated. |
| `GET /users/{username}` (Get a user) | none required | Works unauthenticated for public resources. |
| `GET /users/{username}/hovercard` | **does not work with fine-grained PATs at all** | Classic `repo` scope only. |
