# External documentation manifest

Third-party documentation gathered while planning, so a plan's claims about an external
library, API or service can be checked rather than trusted.

The agent modes treat an unknown third-party interface as a blocking condition: rather
than guessing at a method signature, the architect fetches the real documentation with
the Oxylabs MCP server, records it here, and cites it in the plan.

## Format

**One line per entry**, in the table below:

```text
| URL | Title | Description |
```

* **URL** — the canonical source, linked so a reader can open it.
* **Title** — the page's own title, not a paraphrase.
* **Description** — one sentence on what the page covers. One sentence, not a summary.

## What gets saved in full, and what does not

| Case | Action |
| --- | --- |
| The page answers the question being planned | Save it in full at `doc/external/<vendor>/<page-slug>.md`, link it from the entry below |
| The page is adjacent, but not needed right now | Record the link and the one-sentence description only |

`<vendor>` is the owner of the documentation, lowercase (`oxylabs`, `stripe`, `vllm`).
`<page-slug>` is a kebab-case slug derived from the page title. One page per file, with
the source URL recorded at the top of the file, so an entry can cite a single path.

Saving a vendor's whole site is not the goal: it buries the page that mattered and makes
the diff unreviewable. Saving a fragment is not either, because the next reader re-fetches
it. Save what answers the question, in full.

## Why this is committed

The research is a team asset and is reviewable in the pull request that relies on it. A
gitignored cache would be re-scraped by every developer and would silently rot.

Two rules follow from that:

* Update this manifest in the same change that saves a page — a saved page absent from
  the manifest is unfindable.
* Never commit credentials, tokens or private endpoints into `doc/external/`.

## Entries

| URL | Title | Description |
| --- | --- | --- |
| [https://dashboard.oxylabs.io/en/overview/scraper](https://dashboard.oxylabs.io/en/overview/scraper) | Oxylabs Web Scraper API dashboard | Where Anvil users create the credentials that `setup-repo` writes to `.env` as `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`. |

<!-- Append new entries above this line, one per row, newest last. -->
