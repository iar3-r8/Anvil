# pi-crew — `scripts/postinstall.mjs`

Source URL: https://github.com/baphuongna/pi-crew/blob/main/scripts/postinstall.mjs
Fetched: 2026-11-02 (via the GitHub contents API, `main` branch, blob
`84781afd312bedde4af7ffec4ff66087bd20095d`, 4499 bytes)

Why this page is saved: issue iar3-r8/anvil#84 finding 1 records
`"postinstall": "node scripts/postinstall.mjs"` in pi-crew's package.json and
notes that "whether pi-crew works without it is **unknown**". Every Anvil npm
global installs with `--ignore-scripts`
([`docker/Dockerfile.bakeoff`](../../../docker/Dockerfile.bakeoff),
[`docker/Dockerfile.sandbox`](../../../docker/Dockerfile.sandbox),
[`templates/devcontainer/Dockerfile`](../../../templates/devcontainer/Dockerfile)),
so the spike must decide whether that flag stays. This file is the whole
script, verbatim, so the decision is checkable without re-fetching.

The companion fact, from the same repo's `package.json` (blob
`471014e5ed31da73ba2d554d79cfc48ed854fc91`, same fetch): the published
`files` array ships `dist/index.mjs`, `index.ts`, `scripts/postinstall.mjs`,
`scripts/install-crew-vibes-font.mjs` and `skills/**` — but **not**
`scripts/build-bundle.mjs`, and not `devDependencies` such as `esbuild`.
That absence is what makes step 1 below a no-op in a published install.

## The script, verbatim

```js
#!/usr/bin/env node
/**
 * Cross-platform postinstall orchestrator.
 *
 *   1. Build the ESM bundle (best-effort; on failure we log a fallback and
 *      let Pi fall back to strip-types loading).
 *   2. Install the bundled crew-vibes.ttf into the user fonts directory so
 *      the crew-vibes speed/capacity PUA glyphs render.
 *   3. Remove stale skill copies from ~/.pi/agent/skills/ (migration from
 *      the v0.9.47 copySkills() bug — see cleanupStaleSkillCopies()).
 *
 * Replaces the old `postinstall` shell chain so the font install runs on
 * every platform without relying on shell-specific chaining (`;`/`&&`).
 *
 * NOTE: skills are NOT copied here. Pi discovers skills natively from the
 * npm package dir (`~/.pi/agent/npm/node_modules/pi-crew/skills/`); copying
 * them to ~/.pi/agent/skills/ only creates duplicate "collision" warnings.
 */
import { existsSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");

function run(scriptRel) {
	const abs = join(root, scriptRel);
	if (!existsSync(abs)) return 1;
	const result = spawnSync(process.execPath, [abs], { stdio: "inherit" });
	return result.status ?? 1;
}

/**
 * Remove stale skill copies from ~/.pi/agent/skills/ that are byte-identical
 * to the bundled skills/ — left over from the v0.9.47 copySkills() postinstall
 * (which redundantly copied all skills, causing "collision" warnings).
 *
 * Pi discovers skills natively from the npm package dir, so these copies only
 * create noise AND can shadow newer package versions on upgrade.
 *
 * SAFE: only removes EXACT (byte-identical) copies. A skill the user has
 * customized (differs from the package) is preserved. Best-effort, never
 * fails the install.
 */
function cleanupStaleSkillCopies() {
	const srcSkillsDir = join(root, "skills");
	if (!existsSync(srcSkillsDir)) return;

	const destSkillsDir = join(homedir(), ".pi", "agent", "skills");
	if (!existsSync(destSkillsDir)) return;

	let removed = 0;
	let kept = 0;
	for (const entry of readdirSync(srcSkillsDir, { withFileTypes: true })) {
		if (!entry.isDirectory()) continue;
		const srcSkillMd = join(srcSkillsDir, entry.name, "SKILL.md");
		if (!existsSync(srcSkillMd)) continue;
		const destSkillDir = join(destSkillsDir, entry.name);
		const destSkillMd = join(destSkillDir, "SKILL.md");
		if (!existsSync(destSkillMd)) continue;
		try {
			const srcContent = readFileSync(srcSkillMd, "utf8");
			const destContent = readFileSync(destSkillMd, "utf8");
			if (srcContent === destContent) {
				rmSync(destSkillDir, { recursive: true, force: true });
				removed++;
			} else {
				// User customized this skill — preserve it.
				kept++;
			}
		} catch {
			// best-effort: skip this skill on error
		}
	}
	if (removed > 0) {
		const note = kept > 0 ? ` (${kept} customized copy(ies) preserved)` : "";
		console.warn(
			`[pi-crew] postinstall: removed ${removed} stale skill cop${removed === 1 ? "y" : "ies"} from ~/.pi/agent/skills/${note}.`,
		);
	}
}

function main() {
	try {
		// Dev clones ship scripts/build-bundle.mjs and devDeps (esbuild) so the
		// bundle rebuilds; published packages omit both and rely on committed
		// dist/index.mjs, so this best-effort build simply no-ops.
		const bundleStatus = run("scripts/build-bundle.mjs");
		if (bundleStatus !== 0) {
			// TB-11: Surface bundle failures loudly to stderr instead of console.warn,
			// which can scroll off in noisy install logs. We still don't `process.exit(1)`
			// here — the install itself must succeed via the strip-types fallback —
			// but the failure must be obvious to whoever runs `npm install`.
			process.stderr.write(
				"\u001b[31m[pi-crew] postinstall: bundle build FAILED\u001b[0m — using committed dist/ (or strip-types fallback). Run 'npm run build:bundle' to retry. See logs above for esbuild errors.\n",
			);
		}
		// Font install is best-effort and must never fail the install.
		run("scripts/install-crew-vibes-font.mjs");
		// Migration cleanup: remove stale skill copies from v0.9.47's copySkills().
		cleanupStaleSkillCopies();
	} catch (err) {
		// Postinstall must NEVER fail the install (SEC-M2).
		console.warn("[pi-crew] postinstall: best-effort step failed:", err instanceof Error ? err.message : err);
	}
}

main();
```

## What it does, step by step

| Step | Effect in a published `npm install -g` | Needed for the `team` tool? |
|---|---|---|
| 1. `run("scripts/build-bundle.mjs")` | **No-op.** The script is absent from the published `files` array, so `run()` returns `1` at its `existsSync` guard without spawning anything; the handler writes a red warning to stderr and continues. The script's own comment states the intent: *"published packages omit both and rely on committed `dist/index.mjs`, so this best-effort build simply no-ops."* | No — `dist/index.mjs` ships committed. |
| 2. `run("scripts/install-crew-vibes-font.mjs")` | Installs `assets/crew-vibes.ttf` into the user fonts directory, for *"the crew-vibes speed/capacity PUA glyphs"*. Cosmetic terminal rendering. | No — glyph rendering, irrelevant to a non-interactive run. |
| 3. `cleanupStaleSkillCopies()` | **Returns early** on a fresh container: it `return`s unless `~/.pi/agent/skills/` already exists. It only deletes byte-identical leftovers of the v0.9.47 `copySkills()` bug. | No — a migration for upgraders. |

Two further guarantees come from the script's own structure:

- **`main()` wraps all three in `try { } catch { }`**, with the comment
  *"Postinstall must NEVER fail the install (SEC-M2)."* It never calls
  `process.exit(1)`.
- **Skills are not copied by this script at all.** The header note is
  explicit: *"skills are NOT copied here. Pi discovers skills natively from
  the npm package dir (`~/.pi/agent/npm/node_modules/pi-crew/skills/`)"*.

## The one consequence for Anvil's images

That last note names the discovery path Pi uses — the **`pi install npm:`
layout** under the agent directory, not the `npm install -g` layout Anvil's
three images use. A global install therefore lands pi-crew at
`/usr/local/lib/node_modules/pi-crew/`, which is outside Pi's package
discovery. The spike's run must load the extension explicitly with
`-e <path>/index.ts` and allowlist the tool in `--tools`, exactly as the
bake-off already does for `pi-ultrawork`
([`doc/pi-bakeoff/README.md`](../../pi-bakeoff/README.md) section 5,
`PI_EXTENSION_PATH`). This is an invocation fact, not a postinstall one, and
is verified by the spike's recorded run — not assumed here.
