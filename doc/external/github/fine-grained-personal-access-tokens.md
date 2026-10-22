# Managing your personal access tokens — GitHub Docs

Source URL: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
Fetched: 2026-10-20

Why this page is saved (abridged to the parts that decide the sandbox token): it answers
"can we give the agent a token that writes only to the repo being worked on?" — yes.
A **fine-grained** PAT is "limited to access resources owned by a single user or
organization" and "can be further limited to only access specific repositories", with
per-permission `read`/`write` levels. The minimum for our loop is `contents=write`,
`pull_requests=write`, `issues=write`, plus the implicit `metadata=read`; notably
`administration` and `workflows` are **separate permissions we can simply withhold** — so
the token cannot delete the repository or edit CI workflows. Two caveats that bear on the
design: "Tokens always include read-only access to all public repositories on GitHub", and
a classic PAT by contrast "will grant access to all repositories within the organizations
that you have access to, as well as all personal repositories" — so a classic token must
not be used here.

---

## About personal access tokens

Personal access tokens are an alternative to using passwords for authentication to GitHub when using the GitHub API or the command line.

A token has the same capabilities to access resources and perform actions on those resources that the owner of the token has, and is further limited by any scopes or permissions granted to the token. A token cannot grant additional access capabilities to a user.

### Types of personal access tokens

GitHub currently supports two types of personal access tokens: fine-grained personal access tokens and personal access tokens (classic). GitHub recommends that you use fine-grained personal access tokens instead of personal access tokens (classic) whenever possible.

#### Fine-grained personal access tokens

If you can use a fine-grained personal access token for your scenario, you'll benefit from these improvements:

* Each token is limited to access resources owned by a single user or organization.
* Each token can be further limited to only access specific repositories for that user or organization.
* Each token is granted specific, fine-grained permissions, which offer more control than the scopes granted to personal access tokens (classic).
* Organization owners can require approval for any fine-grained personal access tokens that can access resources in the organization.

##### Fine-grained personal access tokens limitations

Fine-grained personal access tokens do not support every feature of personal access tokens (classic). The major gaps are:

* Using fine-grained personal access token to contribute to public repos where the user is not a member.
* Using fine-grained personal access token to contribute to repositories where the user is an outside or repository collaborator.
* Using fine-grained personal access token to access multiple organizations at once.
* Using fine-grained personal access token to access Packages.
* Using fine-grained personal access token to call the Checks API.
* Using fine-grained personal access token to access Projects owned by a user account.

#### Personal access tokens (classic)

Personal access tokens (classic) are less secure. However, some features currently will only work with personal access tokens (classic):

* Only personal access tokens (classic) have write access for public repositories that are not owned by you or an organization that you are not a member of.
* Outside collaborators can only use personal access tokens (classic) to access organization repositories that they are a collaborator on.
* A few REST API endpoints are only available with a personal access tokens (classic).

> If you choose to use a personal access token (classic), keep in mind that it will grant access to all repositories within the organizations that you have access to, as well as all personal repositories in your personal account.

As a security precaution, GitHub automatically removes personal access tokens that haven't been used in a year. To provide additional security, we highly recommend adding an expiration to your personal access tokens.

## Creating a fine-grained personal access token

> Note: There is a limit of 50 fine-grained personal access tokens you can create. If you require more tokens or are building automations, consider using a GitHub App for better scalability and management.

1. Verify your email address, if it hasn't been verified yet.
2. In the upper-right corner of any page on GitHub, click your profile picture, then click **Settings**.
3. In the left sidebar, click **Developer settings**.
4. In the left sidebar, under **Personal access tokens**, click **Fine-grained tokens**.
5. Click **Generate new token**.
6. Under **Token name**, enter a name for the token.
7. Under **Expiration**, select an expiration for the token. Infinite lifetimes are allowed but may be blocked by a maximum lifetime policy set by your organization or enterprise owner.
8. Optionally, under **Description**, add a note to describe the purpose of the token.
9. Under **Resource owner**, select a resource owner. The token will only be able to access resources owned by the selected resource owner.
10. Optionally, if the resource owner is an organization that requires approval, enter a justification for the request.
11. Under **Repository access**, select which repositories you want the token to access. You should choose the minimal repository access that meets your needs. **Tokens always include read-only access to all public repositories on GitHub.**
12. If you selected **Only select repositories** in the previous step, under the **Selected repositories** dropdown, select the repositories that you want the token to access.
13. Under **Permissions**, select which permissions to grant the token. You should choose the minimal permissions necessary for your needs.
14. Click **Generate token**.

## Pre-filling fine-grained personal access token details using URL parameters

Each supported field can be set using a specific query parameter.

```http
https://github.com/settings/personal-access-tokens/new
  ?name=Repo-reading+token
  &description=Just+contents:read
  &target_name=octodemo
  &expires_in=45
  &contents=read
```

### Supported query parameters

| Parameter | Type | Example Value | Valid Values | Description |
| --- | --- | --- | --- | --- |
| `name` | string | `Deploy%20Bot` | ≤ 40 characters, URL-encoded | Pre-fills the token's display name. |
| `description` | string | `Used+for+deployments` | ≤ 1024 chars, URL-encoded | Pre-fills the description for the token. |
| `target_name` | string | `octodemo` | User or organization slug | Sets the token's resource target. This is the owner of the repositories that the token will be able to access. If not provided, defaults to the current user's account. |
| `expires_in` | integer | `30` or `none` | Integer between 1 and 366, or `none` | Days until expiration or `none` for non-expiring. If not provided, the default is 30 days. |
| `<permission>` | string | `contents=read` | A series of permission and access levels. | The permissions the token should have. Permissions can be set to `read`, `write`, or `admin`, but not every permission supports each of those levels. |

### Permissions

To set a permission, use its name as a query parameter, with the value specifying the desired access level. Valid access levels are `read`, `write`, and `admin`, but not every permission supports every level.

> Tip: You do not need to include both `read` and `write` for a permission in your URL — `write` always includes `read`, and `admin` always includes `write`.

#### Repository permissions

Repository permissions work for both user and organization resource owners.

| Parameter name | Display name | Access levels |
| --- | --- | --- |
| `actions` | Actions | `read`, `write` |
| `administration` | Administration | `read`, `write` |
| `artifact_metadata` | Artifact metadata | `read`, `write` |
| `attestations` | Attestations | `read`, `write` |
| `code_quality` | Code quality | `read`, `write` |
| `security_events` | Code scanning alerts | `read`, `write` |
| `codespaces` | Codespaces | `read`, `write` |
| `codespaces_lifecycle_admin` | Codespaces lifecycle admin | `read`, `write` |
| `codespaces_metadata` | Codespaces metadata | `read` |
| `codespaces_secrets` | Codespaces secrets | `write` |
| `statuses` | Commit statuses | `read`, `write` |
| `contents` | Contents | `read`, `write` |
| `repository_custom_properties` | Custom properties | `read`, `write` |
| `vulnerability_alerts` | Dependabot alerts | `read`, `write` |
| `dependabot_secrets` | Dependabot secrets | `read`, `write` |
| `deployments` | Deployments | `read`, `write` |
| `discussions` | Discussions | `read`, `write` |
| `environments` | Environments | `read`, `write` |
| `issues` | Issues | `read`, `write` |
| `merge_queues` | Merge queues | `read`, `write` |
| `metadata` | Metadata | `read` |
| `pages` | Pages | `read`, `write` |
| `pull_requests` | Pull requests | `read`, `write` |
| `repository_advisories` | Repository security advisories | `read`, `write` |
| `secret_scanning_alerts` | Secret scanning alerts | `read`, `write` |
| `secrets` | Secrets | `read`, `write` |
| `actions_variables` | Variables | `read`, `write` |
| `repository_hooks` | Webhooks | `read`, `write` |
| `workflows` | Workflows | `write` |

#### Account permissions (abridged)

Account permissions can only be used when the current user is the resource owner; they cover things such as `emails`, `gpg_keys`, `keys`, `profile`, `starring` and `gists`.

#### Organization permissions (abridged)

Organization permissions can only be used if the resource owner is an organization; they cover `organization_administration`, `members`, `organization_secrets`, `organization_hooks` and similar.

## Creating a personal access token (classic)

> Warning: Your personal access token (classic) can access every repository that you can access. GitHub recommends that you use fine-grained personal access tokens instead, which you can restrict to specific repositories.

## Deleting a personal access token

You should delete a personal access token if it is no longer needed. In **Settings → Developer settings → Personal access tokens**, click either **Fine-grained tokens** or **Tokens (classic)**, then **Delete** next to the token.

## Using a personal access token on the command line

Once you have a personal access token, you can enter it instead of your password when performing Git operations over HTTPS.

```
$ git clone https://github.com/USERNAME/REPO.git
Username: YOUR-USERNAME
Password: YOUR-PERSONAL-ACCESS-TOKEN
```

Personal access tokens can only be used for HTTPS Git operations. If your repository uses an SSH remote URL, you will need to switch the remote from SSH to HTTPS.
