#!/usr/bin/env node
/**
 * Embed-asset upstream freshness gate.
 *
 * renet embeds pinned upstream binaries — criu, rsync, rclone, zot, k3s and the
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
 *  - FAIL SOFT ON NETWORK: an unreachable upstream / rate-limit / timeout is
 *    reported and EXITS 0. Only a CONFIRMED stale pin (past the window, not held)
 *    fails the build. A GitHub API blip must never be somebody's red build.
 *
 * Usage:
 *   npx tsx scripts/gates/check-embed-asset-freshness.ts            # check
 *   npx tsx scripts/gates/check-embed-asset-freshness.ts --upgrade  # rewrite pins
 *
 * --upgrade moves EVERY pin tied to a stale component, not just its VERSION ARG:
 * the Dockerfile `_COMMIT` / `_SHA256[_<ARCH>]` ARGs (resolved from the upstream
 * tag or the release's published checksum file), embed-assets.lock.json, and the
 * Go constants in scripts/lib/embed-pin-upgrade.ts SOURCE_CONSTS. A pin it cannot
 * resolve (rsync publishes no checksum file) makes it REFUSE that component and
 * exit 1; it never leaves a half-moved pin behind.
 *   npm run check:ci-embed-asset-freshness
 *
 * Exit codes: 0 = fresh / deferred / held / could-not-check; 1 = a confirmed
 * stale pin (or a malformed blocklist entry).
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
import {
  WK_GH_API_BASE,
  WK_RENET_REPO,
} from '../../packages/shared/src/config/well-known.generated.js';
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
  sharedCloneDrift,
  type UpgradeFiles,
  upgradeComponent,
} from '../lib/embed-pin-upgrade.js';
import { githubToken } from '../lib/github-token.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');
// Test seam: EMBED_RENET_DIR points --upgrade at a fixture renet tree (Dockerfile, embed-assets.lock.json, the Go files in SOURCE_CONSTS), so the gate test can prove an upgrade moves every tied pin without touching the real submodule.
const RENET_DIR = process.env.EMBED_RENET_DIR || path.join(CONSOLE_ROOT, 'private/renet');
const DOCKERFILE = path.join(RENET_DIR, 'Dockerfile');
const LOCKFILE = path.join(RENET_DIR, 'embed-assets.lock.json');
// Test seam: EMBED_BLOCKLIST_FILE points at a fixture blocklist so the gate test can prove the BLOCKER-reason validation fires without mutating the real, tracked .embed-assets-upgrade-blocklist.
const BLOCKLIST =
  process.env.EMBED_BLOCKLIST_FILE || policyPath('.embed-assets-upgrade-blocklist', CONSOLE_ROOT);

const HTTP_TIMEOUT_MS = 15_000;

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

async function fetchJson(url: string): Promise<unknown> {
  const headers: Record<string, string> = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'rediacc-embed-asset-freshness',
  };
  const token = githubToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), HTTP_TIMEOUT_MS);
  try {
    const res = await fetch(url, { headers, signal: ctl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(t);
  }
}

/** HEAD a URL and return its response headers (used for Last-Modified dates). */
async function fetchHead(url: string): Promise<Headers> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), HTTP_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: 'HEAD',
      headers: { 'User-Agent': 'rediacc-embed-asset-freshness' },
      signal: ctl.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.headers;
  } finally {
    clearTimeout(t);
  }
}

async function fetchText(url: string): Promise<string> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), HTTP_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': 'rediacc-embed-asset-freshness' },
      signal: ctl.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally {
    clearTimeout(t);
  }
}

/**
 * Test seam: EMBED_FRESHNESS_FIXTURE points at a JSON map
 * `{ "<base>": { "version": "x.y.z", "publishedAt"?: "ISO" } }` used INSTEAD of
 * hitting the network, so the gate test can prove it fires (stale) and passes
 * (current) deterministically. A base absent from the fixture throws (→ the
 * could-not-check / fail-soft path), which the test also exercises.
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

/** Latest stable release for a source, or throws (caught as could-not-check). */
async function latestFor(src: Source): Promise<Latest> {
  const fixture = loadFixture();
  if (fixture) {
    const hit = fixture[src.base];
    if (!hit) throw new Error('not in fixture');
    return {
      version: hit.version,
      publishedAt: hit.publishedAt ? new Date(hit.publishedAt) : null,
    };
  }
  if (src.kind === 'github') {
    // /releases/latest excludes prereleases/drafts — the stable line we track.
    try {
      const rel = (await fetchJson(`${WK_GH_API_BASE}/repos/${src.repo}/releases/latest`)) as {
        tag_name?: string;
        published_at?: string;
      };
      if (!rel.tag_name) throw new Error('no tag_name in release');
      return {
        version: rel.tag_name.replace(/^v/i, ''),
        publishedAt: rel.published_at ? new Date(rel.published_at) : null,
      };
    } catch (err) {
      // Projects that tag but never cut GitHub "releases" (e.g. CRIU) 404 on /releases/latest — fall back to the tags list and take the highest stable vX.Y.Z. Tags carry no publish date, so the freshness window can't apply (treated as old enough).
      if (!/HTTP 404/.test((err as Error).message)) throw err;
      const tags = (await fetchJson(
        `${WK_GH_API_BASE}/repos/${src.repo}/tags?per_page=100`
      )) as Array<{ name?: string }>;
      const stable = tags
        .map((t) => t.name ?? '')
        .filter((n) => /^v?\d+\.\d+(\.\d+)?$/.test(n))
        .map((n) => n.replace(/^v/i, ''));
      if (stable.length === 0) throw new Error('no stable tags found');
      stable.sort((a, b) => (isNewer(a, b) ? 1 : -1));
      const newest = stable[stable.length - 1];

      // Resolve the tag to its commit date so the soak applies here too.
      //
      // A tag carries no publish time of its own, and this gate treats a null date as NOT deferred, so CRIU — which tags but never cuts GitHub releases — was the one component that got NO grace period at all: the moment upstream pushed a tag, the very next CI run went red. Every other component soaked for a day. One extra request buys uniform behaviour.
      const commit = (await fetchJson(
        `${WK_GH_API_BASE}/repos/${src.repo}/commits/${encodeURIComponent(`v${newest}`)}`
      )) as { commit?: { committer?: { date?: string } } };
      const date = commit.commit?.committer?.date;
      return { version: newest, publishedAt: date ? new Date(date) : null };
    }
  }
  // rsync: parse the Samba source index for the highest rsync-X.Y.Z.tar.gz.
  const html = await fetchText('https://download.samba.org/pub/rsync/src/');
  const versions = [...html.matchAll(/rsync-(\d+\.\d+\.\d+)\.tar\.gz/g)].map((m) => m[1]);
  if (versions.length === 0) throw new Error('no rsync tarballs found in index');
  versions.sort((a, b) => (isNewer(a, b) ? 1 : -1));
  const newestRsync = versions[versions.length - 1];

  // Same reasoning as the tag path above: the Samba index has no publish column we can trust, so take the tarball's Last-Modified header. rsync would otherwise be the second component with no soak.
  let rsyncPublished: Date | null = null;
  try {
    const head = await fetchHead(
      `https://download.samba.org/pub/rsync/src/rsync-${newestRsync}.tar.gz`
    );
    const lastModified = head.get('last-modified');
    if (lastModified) {
      const parsed = new Date(lastModified);
      if (!Number.isNaN(parsed.getTime())) rsyncPublished = parsed;
    }
  } catch {
    // Fall through with a null date: the gate's existing policy is that a dateless source still surfaces a stale pin rather than hiding it.
  }
  return { version: newestRsync, publishedAt: rsyncPublished };
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
      const c = (await fetchJson(
        `${WK_GH_API_BASE}/repos/${repo}/commits/${encodeURIComponent(tag)}`
      )) as { sha?: string };
      if (!c.sha) throw new Error('no sha in commit response');
      return c.sha;
    },
    text: fetchText,
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
    console.log(`${GREEN}↑ ${f.display}: ${f.pinned} -> ${f.latest}${NC}`);
    for (const c of res.changes) console.log(`    ${c}`);
  }
  const drift = sharedCloneDrift(files.dockerfile);
  if (drift) {
    refused.push(drift);
    files = before;
  }
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
  const unchecked: string[] = [];
  const heldOut: string[] = [];

  for (const src of SOURCES) {
    const pinned = versions.get(src.base);
    if (!pinned) {
      unchecked.push(`${src.display}: no ${src.base.toUpperCase()}_VERSION ARG in Dockerfile`);
      continue;
    }
    if (held.has(src.base)) {
      heldOut.push(`${src.display} (pinned at ${pinned})`);
      continue;
    }
    let latest: Latest;
    try {
      latest = await latestFor(src);
    } catch (err) {
      // FAIL SOFT: never redden the build over a network / rate-limit blip.
      unchecked.push(`${src.display}: could not check (${(err as Error).message})`);
      continue;
    }
    if (!isNewer(latest.version, pinned)) continue;
    // FAIL-OPEN on a missing publish date (git tags, the rsync index): unlike the npm-dep gate we flag it, because a dateless source must still surface a stale pin. With a date, apply the shared soak.
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
  for (const u of unchecked) console.log(`${YELLOW}? ${u}${NC}`);
  for (const h of heldOut) console.log(`${YELLOW}⏸ held: ${h}${NC}`);

  if (stale.length === 0) {
    console.log(
      `${GREEN}✓ Every embed-asset pin is current (or deferred / held / uncheckable).${NC}`
    );
    return;
  }

  if (upgrade) {
    process.exit(await runUpgrade(stale, dockerfile));
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
  // An unexpected error in the gate itself must not silently pass — but a network failure is already caught per-source above, so reaching here is a real bug.
  console.error(`${RED}✗ freshness gate crashed: ${(err as Error).message}${NC}`);
  process.exit(1);
});
