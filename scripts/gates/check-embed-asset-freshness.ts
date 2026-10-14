#!/usr/bin/env node
/**
 * Embed-asset upstream freshness gate.
 *
 * renet embeds pinned upstream binaries — criu, rsync, zot, k3s and the
 * CSI sidecars — whose versions live as `ARG <BASE>_VERSION=` in
 * private/renet/Dockerfile (the single source of truth; check-embed-credits.ts
 * keeps embed.go + the credits inventories consistent with them). Nothing,
 * however, told us when those pins went STALE: a k3s or zot CVE could sit
 * un-upgraded indefinitely because npm/Go dep gates never see a Dockerfile ARG.
 * This gate closes that hole — it compares each pin against the upstream latest
 * and fails when one has fallen behind.
 *
 * DESIGN (mirrors scripts/gates/check-deps.ts conventions):
 *  - Versions are read via the SHARED parser (scripts/lib/dockerfile-versions.ts),
 *    the same one the credits gate uses — one definition of "what is pinned".
 *  - FRESHNESS WINDOW: a brand-new upstream release (younger than the window) is
 *    NOT flagged yet. This is self-healing against churn — we don't redden the
 *    build the instant upstream tags something, matching the release-age window
 *    posture used for npm deps.
 *  - BLOCKER-GATED HOLDS: .embed-assets-upgrade-blocklist deliberately pins a
 *    component back, each entry carrying a substantive BLOCKER reason (validated
 *    like every other suppression list in the repo).
 *  - FAIL CLOSED ON NETWORK (operator ruling 2026-10-13, "Everything fails
 *    closed, nightly included"). Until that ruling an unreachable upstream, a
 *    rate limit or a timeout was reported as could-not-check and EXITED 0, so a
 *    green did not mean the pins had been compared. Now a pin whose upstream
 *    answer was not obtained is a RED finding that names the pin, the host and
 *    path asked, the status or error code, and that this is an upstream
 *    reachability failure. The request, the bounded retry (3 attempts, 15 s
 *    each, 2 s then 4 s between them) and the finding's wording are shared with
 *    every external gate, in scripts/lib/upstream.ts. The pins are asked
 *    concurrently.
 *  - AN ANSWER THAT CANNOT BE USED IS RED TOO: a release with no tag, a tag
 *    list with no stable version, an rsync index with no tarball. The gate has
 *    stopped seeing that upstream.
 *  - A SOURCE WITH NO `ARG <BASE>_VERSION` IN THE DOCKERFILE IS RED on a check
 *    run: nothing was compared for it.
 *
 * UPSTREAMS ASKED, all of them:
 *  1. api.github.com `GET /repos/<owner>/<repo>/releases/latest`, for the six
 *     GitHub sources in scripts/lib/embed-asset-sources.ts.
 *  2. api.github.com `GET /repos/<owner>/<repo>/tags`, then
 *     `GET /repos/<owner>/<repo>/commits/<tag>` for the tag's date, when (1)
 *     answers 404: a project that tags without cutting releases (CRIU). A 404
 *     on (1) is that documented fallback and is not a finding by itself; any
 *     failure of the two follow-up requests is.
 *  3. download.samba.org `GET /pub/rsync/src/`, the rsync source index.
 *  4. download.samba.org `HEAD /pub/rsync/src/rsync-<v>.tar.gz`, for the
 *     tarball's Last-Modified. This one request is NOT a finding when it fails:
 *     the version comparison has already happened, a missing date means no soak,
 *     and no soak makes a newer rsync red sooner, never green. The failure is
 *     printed with its host.
 *  --upgrade also asks api.github.com for a tag's commit and github.com for a
 *  release's checksum file (scripts/lib/embed-pin-upgrade.ts); a failure there
 *  REFUSES the component and exits 1.
 *
 * HARD ON EVERY CADENCE. The step runs `npm run check:ci-embed-asset-freshness`
 * directly, with no wrapper, so an exit 1 is red on a pull
 * request, on the nightly and on a dispatch. The `no-external-quality` label on
 * a pull request is the one way the step does not run, and the job's "Announce
 * pin gates held by label" step names this gate in the log when that happens.
 *
 * Usage:
 *   npx tsx scripts/gates/check-embed-asset-freshness.ts            # check
 *   npx tsx scripts/gates/check-embed-asset-freshness.ts --upgrade  # rewrite pins
 *
 * --upgrade moves EVERY pin tied to a stale component, not just its VERSION ARG:
 * the Dockerfile `_COMMIT` / `_SHA256[_<ARCH>]` ARGs (resolved from the upstream
 * tag or the release's published checksum file), embed-assets.lock.json, and the
 * Go constants and unit goldens its `embed:<base>` entry in .ci/config/pins.json
 * places in private/renet (SOURCE_CONSTS in scripts/lib/embed-pin-upgrade.ts). A pin it cannot
 * resolve (rsync publishes no checksum file) makes it REFUSE that component and
 * exit 1; it never leaves a half-moved pin behind.
 *   npm run check:ci-embed-asset-freshness
 *
 * Exit codes: 0 = every pin that is not held was compared with upstream and is
 * current or deferred; 1 = a confirmed stale pin, a pin that was not compared,
 * an upstream answer that cannot be used, a source with no ARG, or a malformed
 * blocklist entry.
 *
 * ---- gate ----
 * step: Check embed-asset upstream freshness
 * needs: node, submodules
 * run: tsx scripts/gates/check-embed-asset-freshness.ts && tsx scripts/__tests__/github-token.control.ts
 * lane: quality-go
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WK_RENET_REPO } from '../../packages/shared/src/config/well-known.generated.js';
import { parseBlockeredList, verifyAllBlockers } from '../lib/blocker-validator.js';
import { errorLines, GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { parseDockerfileVersions } from '../lib/dockerfile-versions.js';
// Extracted so scripts/gates/check-suppression-liveness.ts can reuse the inventory without importing this module (which runs main() at import time).
import {
  EMBED_ASSET_SOURCES as SOURCES,
  type EmbedAssetSource as Source,
} from '../lib/embed-asset-sources.js';
import {
  CONST_FILES,
  type Fetchers,
  fixtureEntry,
  sharedCloneDrift,
  type UpgradeFiles,
  upgradeComponent,
} from '../lib/embed-pin-upgrade.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import {
  askUpstream,
  githubAsker,
  NotCompared,
  PinTally,
  UnreadableListing,
} from '../lib/upstream.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');
// Test seam: EMBED_RENET_DIR points --upgrade at a fixture renet tree (Dockerfile, embed-assets.lock.json, the Go files in SOURCE_CONSTS), so the gate test can prove an upgrade moves every tied pin without touching the real submodule.
const RENET_DIR = process.env.EMBED_RENET_DIR || path.join(CONSOLE_ROOT, 'private/renet');
const DOCKERFILE = path.join(RENET_DIR, 'Dockerfile');
const LOCKFILE = path.join(RENET_DIR, 'embed-assets.lock.json');
// Test seam: EMBED_BLOCKLIST_FILE points at a fixture blocklist so the gate test can prove the BLOCKER-reason validation fires without mutating the real, tracked .embed-assets-upgrade-blocklist.
const BLOCKLIST =
  process.env.EMBED_BLOCKLIST_FILE || policyPath('.embed-assets-upgrade-blocklist', CONSOLE_ROOT);
// Test seam: EMBED_UPSTREAM_BASE stands ONE base in for both hosts this gate asks, so its test can serve them from a stub HTTP server and an offline run can be driven by hand: the GitHub API is read at `<base>/repos/...` and the rsync index at `<base>/pub/rsync/src/`. The token is never sent to it.
const UPSTREAM_OVERRIDE = process.env.EMBED_UPSTREAM_BASE;
const RSYNC_INDEX = `${UPSTREAM_OVERRIDE || 'https://download.samba.org'}/pub/rsync/src/`;
const USER_AGENT = 'rediacc-embed-asset-freshness';

interface Latest {
  version: string;
  publishedAt: Date | null;
}

/** A version string -> comparable numeric segments (build metadata after +/- kept as a tiebreak). */
function toSegments(v: string): number[] {
  // Strip a leading v, split the k3s-style "1.36.2+k3s1" into ["1.36.2", "k3s1"].
  const cleaned = v.replace(/^v/i, '');
  const [core, meta = ''] = cleaned.split('+');
  const nums = core.split(/[.-]/).map((s) => Number.parseInt(s, 10) || 0);
  const metaNum = Number.parseInt(meta.replace(/\D/g, ''), 10) || 0;
  return [...nums, metaNum];
}

/** true when `latest` is strictly newer than `pinned`. */
function isNewer(latest: string, pinned: string): boolean {
  const a = toSegments(latest);
  const b = toSegments(pinned);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x !== y) return x > y;
  }
  return false;
}

/** One GitHub REST call for a pin, with the shared retry. The token goes to api.github.com and to nothing the seam points at. */
const githubJson = githubAsker(USER_AGENT, UPSTREAM_OVERRIDE);

/** A plain GET of a text resource, with the shared retry and no token. */
async function fetchText(url: string, who: string): Promise<string> {
  return (await askUpstream({ url, headers: { 'User-Agent': USER_AGENT }, who })).body;
}

/**
 * Test seam: EMBED_FRESHNESS_FIXTURE points at a JSON map
 * `{ "<base>": { "version": "x.y.z", "publishedAt"?: "ISO" } }` used INSTEAD of
 * hitting the network, so the gate test can prove it fires (stale) and passes
 * (current) deterministically. A base absent from the fixture was not compared,
 * which is red, and the test exercises that too.
 */
let fixtureCache: Record<string, { version: string; publishedAt?: string }> | null | undefined;
function loadFixture(): Record<string, { version: string; publishedAt?: string }> | null {
  const cached = fixtureCache;
  if (cached !== undefined) return cached;
  const p = process.env.EMBED_FRESHNESS_FIXTURE;
  const loaded = p ? JSON.parse(fs.readFileSync(p, 'utf-8')) : null;
  fixtureCache = loaded;
  return loaded;
}

/** Highest stable vX.Y.Z among a repository's tags, with the tag's commit date so the soak applies. */
async function latestTag(repo: string, who: string): Promise<Latest> {
  const tags = await githubJson(`/repos/${repo}/tags?per_page=100`, who);
  if (!Array.isArray(tags)) throw new UnreadableListing('the response is not a tag list');
  const stable = (tags as Array<{ name?: string } | null>)
    .map((t) => t?.name ?? '')
    .filter((n) => /^v?\d+\.\d+(\.\d+)?$/.test(n))
    .map((n) => n.replace(/^v/i, ''));
  if (stable.length === 0) throw new UnreadableListing('no stable tags found');
  stable.sort((a, b) => (isNewer(a, b) ? 1 : -1));
  const newest = stable[stable.length - 1];

  // Resolve the tag to its commit date so the soak applies here too.
  //
  // A tag carries no publish time of its own, and this gate treats a null date as NOT deferred, so CRIU, which tags but never cuts GitHub releases, was the one component that got NO grace period at all: the moment upstream pushed a tag, the very next CI run went red. Every other component soaked for a day. One extra request buys uniform behaviour.
  const commit = (await githubJson(
    `/repos/${repo}/commits/${encodeURIComponent(`v${newest}`)}`,
    who
  )) as { commit?: { committer?: { date?: string } } } | null;
  const date = commit?.commit?.committer?.date;
  return { version: newest, publishedAt: date ? new Date(date) : null };
}

/** The newest rsync in the Samba source index, dated by its tarball's Last-Modified. */
async function latestRsync(who: string): Promise<Latest> {
  const html = await fetchText(RSYNC_INDEX, who);
  const versions = [...html.matchAll(/rsync-(\d+\.\d+\.\d+)\.tar\.gz/g)].map((m) => m[1]);
  if (versions.length === 0) throw new UnreadableListing('no rsync tarballs found in index');
  versions.sort((a, b) => (isNewer(a, b) ? 1 : -1));
  const newestRsync = versions[versions.length - 1];

  // Same reasoning as the tag path: the Samba index has no publish column that can be trusted, so take the tarball's Last-Modified header. rsync would otherwise be the second component with no soak.
  let rsyncPublished: Date | null = null;
  try {
    const head = await askUpstream({
      url: `${RSYNC_INDEX}rsync-${newestRsync}.tar.gz`,
      headers: { 'User-Agent': USER_AGENT },
      who,
      method: 'HEAD',
    });
    const lastModified = head.headers.get('last-modified');
    if (lastModified) {
      const parsed = new Date(lastModified);
      if (!Number.isNaN(parsed.getTime())) rsyncPublished = parsed;
    }
  } catch (err) {
    if (!(err instanceof NotCompared)) throw err;
    // NOT a finding, and not a skipped comparison: the version above is already known. A null date means no soak, so a newer rsync is reported at once; this failure can only make the gate redder.
    console.log(
      `${YELLOW}? ${who}: no publish date for ${newestRsync} (${err.message}); judged without the soak${NC}`
    );
  }
  return { version: newestRsync, publishedAt: rsyncPublished };
}

/** Latest stable release for a source. Throws NotCompared when upstream's answer was not obtained and UnreadableListing when it cannot be used. */
async function latestFor(src: Source): Promise<Latest> {
  const fixture = loadFixture();
  if (fixture) {
    const hit = fixtureEntry(fixture, src.base);
    if (!hit) throw NotCompared.absentFromFixture(src.base);
    return {
      version: hit.version,
      publishedAt: hit.publishedAt ? new Date(hit.publishedAt) : null,
    };
  }
  if (src.kind !== 'github') return latestRsync(src.display);
  // /releases/latest excludes prereleases and drafts: the stable line this gate tracks.
  let rel: { tag_name?: string; published_at?: string } | null;
  try {
    rel = (await githubJson(`/repos/${src.repo}/releases/latest`, src.display)) as typeof rel;
  } catch (err) {
    // Projects that tag but never cut GitHub "releases" (e.g. CRIU) 404 on /releases/latest: fall back to the tags list and take the highest stable vX.Y.Z. Every other failure is a pin that was not compared.
    if (!(err instanceof NotCompared && err.status === 404)) throw err;
    return latestTag(src.repo ?? '', src.display);
  }
  if (!rel?.tag_name) throw new UnreadableListing('no tag_name in release');
  return {
    version: rel.tag_name.replace(/^v/i, ''),
    publishedAt: rel.published_at ? new Date(rel.published_at) : null,
  };
}

/** Test seam: EMBED_PIN_FIXTURE = { commits: { "<owner/repo>@<tag>": "<sha>" }, texts: { "<url>": "<body>" } }, used INSTEAD of the network for --upgrade's pin resolution. */
function pinFetchers(): Fetchers {
  const p = process.env.EMBED_PIN_FIXTURE;
  if (p) {
    const fx = JSON.parse(fs.readFileSync(p, 'utf-8')) as {
      commits?: Record<string, string>;
      texts?: Record<string, string>;
    };
    return {
      commitOf: async (repo, tag) => {
        const hit = fx.commits?.[`${repo}@${tag}`];
        if (!hit) throw new Error('not in pin fixture');
        return hit;
      },
      text: async (url) => {
        const hit = fx.texts?.[url];
        if (hit === undefined) throw new Error('not in pin fixture');
        return hit;
      },
    };
  }
  return {
    commitOf: async (repo, tag) => {
      const c = (await githubJson(
        `/repos/${repo}/commits/${encodeURIComponent(tag)}`,
        `${repo}@${tag}`
      )) as { sha?: string } | null;
      if (!c?.sha) throw new Error('no sha in commit response');
      return c.sha;
    },
    text: (url) => fetchText(url, url),
  };
}

/** Apply --upgrade to every stale finding; returns the exit code. A component whose pins cannot all be resolved is REFUSED and left untouched. */
async function runUpgrade(stale: Finding[], dockerfile: string): Promise<number> {
  const fetchers = pinFetchers();
  const before: UpgradeFiles = {
    dockerfile,
    lock: fs.existsSync(LOCKFILE) ? fs.readFileSync(LOCKFILE, 'utf-8') : null,
    consts: {},
  };
  for (const rel of CONST_FILES) {
    const abs = path.join(RENET_DIR, rel);
    if (fs.existsSync(abs)) before.consts[rel] = fs.readFileSync(abs, 'utf-8');
  }
  let files = before;
  const refused: string[] = [];
  const moved: string[] = [];
  for (const f of stale) {
    const repo = SOURCES.find((s) => s.base === f.base)?.repo;
    const res = await upgradeComponent(
      files,
      { base: f.base, display: f.display, pinned: f.pinned, latest: f.latest, repo },
      fetchers
    );
    if (!res.ok) {
      refused.push(res.reason);
      continue;
    }
    files = res.files;
    moved.push(
      `${GREEN}↑ ${f.display}: ${f.pinned} -> ${f.latest}${NC}`,
      ...res.changes.map((c) => `    ${c}`)
    );
  }
  const drift = sharedCloneDrift(files.dockerfile);
  if (drift) {
    refused.push(drift);
    files = before;
    // Every resolved component above is discarded with it, so none of them is reported as done.
    moved.length = 0;
    console.error(`${YELLOW}Nothing written: ${drift}${NC}`);
  }
  for (const line of moved) console.log(line);
  if (files.dockerfile !== before.dockerfile) fs.writeFileSync(DOCKERFILE, files.dockerfile);
  if (files.lock !== null && files.lock !== before.lock) fs.writeFileSync(LOCKFILE, files.lock);
  for (const [rel, text] of Object.entries(files.consts)) {
    if (text !== before.consts[rel]) fs.writeFileSync(path.join(RENET_DIR, rel), text);
  }
  if (refused.length > 0) {
    console.error('');
    console.error(
      `${RED}✗ --upgrade REFUSED ${refused.length} component(s); their pins are untouched:${NC}`
    );
    for (const r of refused) console.error(`  ${r}`);
    return 1;
  }
  console.log('');
  console.log(`${YELLOW}Pins rewritten. Still to do for the bumped components:${NC}`);
  console.log('  - `./build.sh embed_assets --force` (builds the pins and restages the assets);');
  console.log(
    '  - `npx tsx scripts/gen/generate-embed-credits.ts` (regenerates the credits inventories);'
  );
  console.log('  - hand-check prose that names the version (docs/design/spec, vendored CRDs).');
  return 0;
}

interface Finding {
  display: string;
  base: string;
  pinned: string;
  latest: string;
}

function loadBlocklist(): { held: Set<string>; errors: string[] } {
  if (!fs.existsSync(BLOCKLIST)) return { held: new Set(), errors: [] };
  const entries = parseBlockeredList(BLOCKLIST);
  const errors = verifyAllBlockers(entries, BLOCKLIST);
  return { held: new Set(entries.map((e) => e.entry.trim().toLowerCase())), errors };
}

async function main(): Promise<void> {
  const upgrade = process.argv.includes('--upgrade');
  const dockerfile = fs.readFileSync(DOCKERFILE, 'utf-8');
  const { versions, conflicts } = parseDockerfileVersions(dockerfile);
  const { held, errors: blockerErrors } = loadBlocklist();
  // Same soak as the npm-dep gate: a release that only just aged past the window is deferred to the next UTC day so a day's upgrades surface together.
  const minReleaseAgeMs = getMinReleaseAgeMs();
  const nowMs = Date.now();

  console.log('Embed-asset Freshness');
  console.log('='.repeat(60));

  if (blockerErrors.length > 0) {
    console.error(`${RED}✗ .ci/policy/.embed-assets-upgrade-blocklist has invalid entries:${NC}`);
    for (const e of blockerErrors) console.error(`  ${e}`);
    process.exit(1);
  }
  for (const c of conflicts) console.error(`${YELLOW}⚠ ${c}${NC}`);

  const stale: Finding[] = [];
  const deferred: string[] = [];
  const tally = new PinTally('embed-asset', SOURCES.length);
  // A held pin and a source with no ARG are not asked.
  const answers = await tally.askAll(SOURCES, (src) =>
    versions.has(src.base) && !held.has(src.base) ? latestFor(src) : null
  );

  for (const [index, src] of SOURCES.entries()) {
    const pinned = versions.get(src.base);
    const answer = answers[index];
    if (!pinned) {
      tally.noPin.push(`${src.display}: no ${src.base.toUpperCase()}_VERSION ARG in Dockerfile`);
      continue;
    }
    if (!answer) {
      tally.held.push(`${src.display} (pinned at ${pinned})`);
      continue;
    }
    if ('err' in answer) {
      const source = `${src.display} (${src.repo ?? 'rsync index'})`;
      tally.failed(`${src.display} (pinned ${pinned})`, source, answer.err);
      continue;
    }
    tally.compared++;
    const latest = answer.value;
    if (!isNewer(latest.version, pinned)) continue;
    // FAIL-OPEN on a missing publish date (git tags, the rsync index): unlike the npm-dep gate it is flagged, because a dateless source must still surface a stale pin. With a date, apply the shared soak.
    if (
      latest.publishedAt !== null &&
      isWithinFreshnessWindow(latest.publishedAt.getTime(), nowMs, minReleaseAgeMs)
    ) {
      deferred.push(
        `${src.display}: ${latest.version} just released — deferred to the next UTC day (soak)`
      );
      continue;
    }
    stale.push({ display: src.display, base: src.base, pinned, latest: latest.version });
  }

  for (const d of deferred) console.log(`${YELLOW}⏳ ${d}${NC}`);
  for (const h of tally.held) console.log(`${YELLOW}⏸ held: ${h}${NC}`);

  // What a green may not hide: a pin nobody compared. --upgrade rewrites the pins it can see, so a missing ARG is left to the check run.
  const blind = tally.report({
    sources: 'scripts/lib/embed-asset-sources.ts',
    noPinFix: [
      '  Restore the ARG in private/renet/Dockerfile, or drop the entry from',
      '  scripts/lib/embed-asset-sources.ts when the asset is no longer embedded.',
    ],
    noPinIsRed: !upgrade,
  });

  if (stale.length === 0) {
    if (blind > 0) process.exit(1);
    console.log(`${GREEN}✓ Every embed-asset pin is current or deferred (${tally.shape}).${NC}`);
    return;
  }

  if (upgrade) {
    // A pin that was not compared was not upgraded either, and that is not a clean run.
    process.exit((await runUpgrade(stale, dockerfile)) || (blind > 0 ? 1 : 0));
  }

  console.error('');
  console.error(`${RED}✗ ${stale.length} embed-asset pin(s) are behind upstream:${NC}`);
  for (const f of stale) {
    console.error(`  ${f.display}: pinned ${f.pinned}  ->  upstream ${f.latest}`);
  }
  // A prominent, copy-paste HOW-TO-FIX so a human or an AI agent can act without hunting: the exact upgrade command, then the follow-ups it can't do itself.
  console.error('');
  console.error(
    `${YELLOW}TO FIX: bump every pin tied to the component (VERSION, COMMIT, SHA256, lockfile, Go constants):${NC}`
  );
  console.error('    npx tsx scripts/gates/check-embed-asset-freshness.ts --upgrade');
  console.error('  then, for each bumped component:');
  console.error('    1. rebuild the builder image so the new binaries are pulled:');
  errorLines(
    `         (cd private/renet && docker build -t ${WK_RENET_REPO}:latest . && ./build.sh embed_assets --force)`,
    '    2. regenerate the credits inventories: npx tsx scripts/gen/generate-embed-credits.ts',
    '       (`npm run check:ci-embed-credits` tells you the exact expected versions);',
    '  A pin --upgrade cannot resolve (rsync publishes no checksum file) is REFUSED, not',
    '  skipped: bump it by hand, then re-run this gate to confirm.'
  );
  console.error('');
  console.error('TO HOLD one back instead: add its base name (e.g. `k3s`) with a `# BLOCKER:`');
  console.error('reason to .ci/policy/.embed-assets-upgrade-blocklist.');
  process.exit(1);
}

main().catch((err) => {
  // An unexpected error in the gate itself must not silently pass. A network failure is already a finding per source above, so reaching here is a real bug.
  console.error(`${RED}✗ freshness gate crashed: ${(err as Error).message}${NC}`);
  process.exit(1);
});
