#!/usr/bin/env node
/**
 * Devcontainer pin freshness gate.
 *
 * The devcontainer image pins third-party CLIs as `ARG <BASE>_VERSION=` in
 * .devcontainer/Dockerfile, and until this file existed NOTHING watched a single
 * one of them. check-deps.ts sees npm; check-go-deps.sh sees go.mod;
 * check-embed-asset-freshness.ts sees private/renet/Dockerfile and says the hole
 * out loud in its own header -- "npm/Go dep gates never see a Dockerfile ARG".
 * This is that same hole, one Dockerfile over. It was noticed when the Bitwarden
 * CLI was pinned at 2026.8.0 and there was no answer to "what tells us when that
 * goes stale?"
 *
 * WHY A SIBLING OF check-embed-asset-freshness.ts RATHER THAN AN ARM OF IT. That
 * gate is narrowly about the binaries renet EMBEDS: its name, its blocklist and
 * every line of its --upgrade advice ("re-run ./build.sh embed_assets --force",
 * "update the credits inventories") are about that pipeline. Devcontainer tools
 * share none of it, and folding them in would make each of those sentences
 * half-true. What IS shared -- the parser, the soak, the BLOCKER validator -- is
 * imported rather than copied.
 *
 * POLICY, inherited deliberately from that gate because it is what makes a
 * freshness gate liveable rather than a thing people disable:
 *  - FRESHNESS WINDOW: a release younger than `minimum-release-age` in .npmrc
 *    (1440 min) is NOT flagged yet, and eligibility is rounded to the next UTC
 *    day so a day's upgrades surface together. Not a new knob: it is the same
 *    number check-deps.ts, audit.sh and check-go-deps.sh already read.
 *  - FAIL SOFT ON NETWORK: a rate-limit, timeout or 5xx is reported and EXITS 0.
 *    Only a CONFIRMED stale pin fails. A GitHub API blip must never be somebody's
 *    red build.
 *  - BLOCKER-GATED HOLDS: .devcontainer-upgrade-blocklist, each entry carrying a
 *    substantive reason, validated like every other suppression list here.
 *
 * WHAT IT DOES THAT THE EMBED GATE DOES NOT:
 *  1. Filters release TAGS by prefix. bitwarden/clients is a monorepo, so
 *     /releases/latest answers with whichever of web/desktop/browser/cli shipped
 *     last -- a question nobody asked. See DevcontainerPinSource.tagPrefix.
 *  2. Rewrites the sha256 ARGs with the version. The embed gate rewrites the ARG
 *     and tells a human to go refresh the hashes; here that would hand back a
 *     tree whose next `docker build` dies at `sha256sum -c -`. The digests are
 *     already on the release JSON this gate is holding, so it writes them.
 *
 * Usage:
 *   npx tsx scripts/check-devcontainer-pin-freshness.ts            # check
 *   npx tsx scripts/check-devcontainer-pin-freshness.ts --upgrade  # rewrite pins
 *   npm run check:ci-devcontainer-pins
 *
 * Exit codes: 0 = fresh / deferred / held / could-not-check; 1 = a confirmed
 * stale pin, a malformed blocklist entry, or an --upgrade that could not resolve
 * every digest it needed.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';
import {
  DEVCONTAINER_PIN_SOURCES as SOURCES,
  type DevcontainerPinSource as Source,
} from './lib/devcontainer-pin-sources.js';
import { parseDockerfileVersions } from './lib/dockerfile-versions.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from './lib/release-age.js';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';
import { githubToken } from './lib/github-token.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
// Test seams, mirroring check-embed-asset-freshness.ts: point the gate at fixture
// files so its test can prove the BLOCKER validation fires and that a stale pin
// is caught, without mutating the tracked blocklist or hitting the network.
//
// DEVCONTAINER_DOCKERFILE is the seam this file was MISSING, and its absence had
// a cost. --upgrade rewrites the Dockerfile in place, so the gate's test drove it
// against the REAL tracked file and restored it from a trap. That mutation is
// visible to every other gate sharing the tree: on 2026-09-03 it reddened
// check:ci-setup-idempotency in the pre-push lane, which reported
// "setup --check changed the working tree" over `.devcontainer/Dockerfile` -- a
// file run.sh never writes, naming the wrong command and sending the reader into
// run.sh. It is also a hazard beyond CI: this repo's working tree usually holds
// another session's uncommitted work, and a gate that rewrites a tracked file,
// however briefly, can be interrupted.
const DOCKERFILE =
  process.env.DEVCONTAINER_DOCKERFILE || path.join(CONSOLE_ROOT, '.devcontainer/Dockerfile');
const BLOCKLIST =
  process.env.DEVCONTAINER_BLOCKLIST_FILE ||
  path.join(CONSOLE_ROOT, '.devcontainer-upgrade-blocklist');

const HTTP_TIMEOUT_MS = 15_000;

interface Latest {
  version: string;
  publishedAt: Date | null;
  /** asset filename -> bare sha256 hex, from the release API's `digest` field. */
  digests: Map<string, string>;
}

/** A version string -> comparable numeric segments. */
function toSegments(v: string): number[] {
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
    'User-Agent': 'rediacc-devcontainer-pin-freshness',
  };
  // Unauthenticated GitHub is 60 requests/hour per IP, which one CI runner shared
  // between jobs can exhaust. A token raises it; its absence is not fatal because
  // the caller treats a rate-limit as could-not-check.
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

/**
 * Test seam: DEVCONTAINER_FRESHNESS_FIXTURE points at a JSON map
 * `{ "<base>": { "version": "x.y.z", "publishedAt"?: "ISO",
 *                "digests"?: { "<asset>": "<sha256>" } } }`
 * used INSTEAD of the network. A base absent from the fixture throws, which is
 * how the test exercises the could-not-check / fail-soft path.
 */
let fixtureCache: Record<string, FixtureEntry> | null | undefined;
interface FixtureEntry {
  version: string;
  publishedAt?: string;
  digests?: Record<string, string>;
}
function loadFixture(): Record<string, FixtureEntry> | null {
  const cached = fixtureCache;
  if (cached !== undefined) return cached;
  const p = process.env.DEVCONTAINER_FRESHNESS_FIXTURE;
  const loaded = p ? JSON.parse(fs.readFileSync(p, 'utf-8')) : null;
  fixtureCache = loaded;
  return loaded;
}

interface GithubRelease {
  tag_name?: string;
  published_at?: string;
  draft?: boolean;
  prerelease?: boolean;
  assets?: Array<{ name?: string; digest?: string }>;
}

/** Newest stable release matching the source's tag prefix, or throws. */
async function latestFor(src: Source): Promise<Latest> {
  const fixture = loadFixture();
  if (fixture) {
    const hit = fixture[src.base];
    if (!hit) throw new Error('not in fixture');
    return {
      version: hit.version,
      publishedAt: hit.publishedAt ? new Date(hit.publishedAt) : null,
      digests: new Map(Object.entries(hit.digests ?? {})),
    };
  }

  // NOT /releases/latest. On a monorepo that endpoint answers with whichever
  // COMPONENT shipped last -- for bitwarden/clients that is web-*, desktop-*,
  // browser-* or cli-* depending on the week -- so it would compare the CLI pin
  // against a browser-extension version and produce nonsense in both directions.
  // The list endpoint is ordered newest-first, so the first prefix match is the
  // answer.
  const rels = (await fetchJson(
    `https://api.github.com/repos/${src.repo}/releases?per_page=100`
  )) as GithubRelease[];
  const hit = rels.find(
    (r) => !r.draft && !r.prerelease && (r.tag_name ?? '').startsWith(src.tagPrefix)
  );
  if (!hit?.tag_name) {
    throw new Error(`no released tag starting with "${src.tagPrefix}" in the newest 100`);
  }

  const digests = new Map<string, string>();
  for (const a of hit.assets ?? []) {
    // `digest` is "sha256:<hex>". Bitwarden publishes no .sha256 sidecars and no
    // GPG/cosign signatures, so this is the only machine-readable checksum there
    // is -- an integrity check against the same API that serves the download,
    // not an independent trust root. Worth knowing; still better than no pin.
    if (a.name && a.digest?.startsWith('sha256:')) {
      digests.set(a.name, a.digest.slice('sha256:'.length));
    }
  }

  return {
    version: hit.tag_name.slice(src.tagPrefix.length),
    publishedAt: hit.published_at ? new Date(hit.published_at) : null,
    digests,
  };
}

interface Finding {
  src: Source;
  pinned: string;
  latest: string;
  digests: Map<string, string>;
}

function loadBlocklist(): { held: Set<string>; errors: string[] } {
  if (!fs.existsSync(BLOCKLIST)) return { held: new Set(), errors: [] };
  const entries = parseBlockeredList(BLOCKLIST);
  const errors = verifyAllBlockers(entries, BLOCKLIST);
  return { held: new Set(entries.map((e) => e.entry.trim().toLowerCase())), errors };
}

/**
 * Rewrite one source's version ARG and every hash ARG it declares.
 *
 * ALL-OR-NOTHING per source. A missing digest returns null and the caller leaves
 * that pin alone, because writing the version without its hash produces a tree
 * that fails `docker build` at `sha256sum -c -` -- and an operator who ran
 * --upgrade and got a broken build learns to distrust the gate, not the release.
 */
function rewriteSource(src: string, f: Finding): { text: string } | { error: string } {
  const arg = `${f.src.base.toUpperCase()}_VERSION`;
  let out = src.replace(new RegExp(`(^ARG\\s+${arg}=)\\S+`, 'gm'), `$1${f.latest}`);

  for (const [arch, spec] of Object.entries(f.src.hashArgs ?? {})) {
    const assetName = spec.asset(f.latest);
    const digest = f.digests.get(assetName);
    if (!digest) {
      return {
        error: `${f.src.display}: release ${f.latest} has no digest for ${assetName} (arch ${arch}); refusing to move the version without its hash.`,
      };
    }
    out = out.replace(new RegExp(`(^ARG\\s+${spec.arg}=)\\S+`, 'gm'), `$1${digest}`);
  }
  return { text: out };
}

async function main(): Promise<void> {
  const upgrade = process.argv.includes('--upgrade');
  const dockerfile = fs.readFileSync(DOCKERFILE, 'utf-8');
  const { versions, conflicts } = parseDockerfileVersions(dockerfile);
  const { held, errors: blockerErrors } = loadBlocklist();
  const minReleaseAgeMs = getMinReleaseAgeMs();
  const nowMs = Date.now();

  console.log('Devcontainer pin freshness');
  console.log('='.repeat(60));

  if (blockerErrors.length > 0) {
    console.error(`${RED}✗ ${path.basename(BLOCKLIST)} has invalid entries:${NC}`);
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
      // A source naming an ARG the Dockerfile no longer has is a real defect --
      // the gate would silently watch nothing -- but it is not a STALENESS
      // failure, and reporting it as one would be the wrong sentence. The
      // suppression-liveness probe is what turns this into a hard error.
      unchecked.push(`${src.display}: no ${src.base.toUpperCase()}_VERSION ARG in the Dockerfile`);
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
      unchecked.push(`${src.display}: could not check (${(err as Error).message})`);
      continue;
    }
    if (!isNewer(latest.version, pinned)) continue;
    if (
      latest.publishedAt !== null &&
      isWithinFreshnessWindow(latest.publishedAt.getTime(), nowMs, minReleaseAgeMs)
    ) {
      deferred.push(
        `${src.display}: ${latest.version} just released — deferred to the next UTC day (soak)`
      );
      continue;
    }
    stale.push({ src, pinned, latest: latest.version, digests: latest.digests });
  }

  for (const d of deferred) console.log(`${YELLOW}⏳ ${d}${NC}`);
  for (const u of unchecked) console.log(`${YELLOW}? ${u}${NC}`);
  for (const h of heldOut) console.log(`${YELLOW}⏸ held: ${h}${NC}`);

  if (stale.length === 0) {
    console.log(
      `${GREEN}✓ Every devcontainer pin is current (or deferred / held / uncheckable).${NC}`
    );
    return;
  }

  if (upgrade) {
    let text = dockerfile;
    const errors: string[] = [];
    for (const f of stale) {
      const result = rewriteSource(text, f);
      if ('error' in result) {
        errors.push(result.error);
        continue;
      }
      text = result.text;
      const alsoHashes = Object.keys(f.src.hashArgs ?? {}).length;
      console.log(
        `${GREEN}↑ ${f.src.display}: ${f.pinned} -> ${f.latest}${NC}` +
          (alsoHashes > 0 ? ` (and ${alsoHashes} sha256 pin(s))` : '')
      );
    }
    if (text !== dockerfile) fs.writeFileSync(DOCKERFILE, text);
    if (errors.length > 0) {
      console.error('');
      for (const e of errors) console.error(`${RED}✗ ${e}${NC}`);
      console.error('  Check the release assets by hand, then set the ARGs yourself:');
      console.error(
        '    curl -s https://api.github.com/repos/<repo>/releases/tags/<tag> | jq -r \'.assets[]|"\\(.name) \\(.digest)"\''
      );
      process.exit(1);
    }
    console.log('');
    console.log(`${YELLOW}Dockerfile ARGs rewritten. Now REBUILD the image and verify:${NC}`);
    console.log(
      '  docker build -t rediacc/devcontainer:bump -f .devcontainer/Dockerfile .devcontainer'
    );
    console.log('  A wrong hash fails that build at `sha256sum -c -`, which is the point.');
    console.log('  The published image only changes when .github/workflows/ci-build-docker.yml');
    console.log('  runs on the merge; developers pick it up with `./run.sh setup --pull`.');
    return;
  }

  console.error('');
  console.error(`${RED}✗ ${stale.length} devcontainer pin(s) are behind upstream:${NC}`);
  for (const f of stale) {
    console.error(`  ${f.src.display}: pinned ${f.pinned}  ->  upstream ${f.latest}`);
  }
  // A copy-pasteable fix, for the same reason check-embed-asset-freshness.ts has
  // one: a human or an agent reading this should be able to act without hunting.
  console.error('');
  console.error(`${YELLOW}TO FIX — bump the pin and its hashes together:${NC}`);
  console.error('    npm run check:ci-devcontainer-pins -- --upgrade');
  console.error('  then rebuild the image to prove the new hashes are right:');
  console.error(
    '    docker build -t rediacc/devcontainer:bump -f .devcontainer/Dockerfile .devcontainer'
  );
  console.error('');
  console.error('TO HOLD one back instead: add its base name (e.g. `bw`) with a `# BLOCKER:`');
  console.error(`reason to ${path.basename(BLOCKLIST)}.`);
  process.exit(1);
}

main().catch((err) => {
  // Per-source network failures are caught above, so reaching here is a real bug
  // in the gate -- which must not be indistinguishable from a pass.
  console.error(`${RED}✗ freshness gate crashed: ${(err as Error).message}${NC}`);
  process.exit(1);
});
