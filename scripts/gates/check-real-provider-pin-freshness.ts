#!/usr/bin/env node
/**
 * Real-provider pin freshness gate.
 *
 * The account E2E suite runs config-storage setup against a real passkey
 * provider: the Bitwarden browser extension, logged in to a throwaway
 * Vaultwarden server. Both are pinned by version and content hash in
 * private/account/e2e/real-provider.lock.json. A pin that stays put while
 * upstream moves tests a provider nobody runs any more, so this gate compares
 * each pin with upstream's releases and fails when one is behind.
 *
 * A SIBLING OF check-devcontainer-pin-freshness.ts, with the same policy:
 *  - FRESHNESS WINDOW: a release younger than the window in
 *    .ci/config/release-age.json is not a finding yet, and eligibility rounds to
 *    the next UTC day (scripts/lib/release-age.ts).
 *  - FAIL SOFT ON NETWORK: an upstream that cannot be reached, a rate limit and
 *    a 5xx are reported as could-not-check and exit 0. Every CI run asks again,
 *    so an outage delays a finding and never hides one for good.
 *  - Drafts and pre-releases are ignored, as are tags that do not carry a plain
 *    x.y.z version after the prefix.
 *
 * WHERE IT DIFFERS:
 *  1. THE NEWEST ELIGIBLE RELEASE IS THE FINDING, not the newest release. The
 *     extension ships several times a month; a pin three releases behind stays
 *     red while the fourth release is still inside the window.
 *  2. A LISTING THAT ANSWERS BUT CANNOT BE READ IS RED, not soft. A 200 that is
 *     not a release list, or holds no stable release under the tag prefix at
 *     all, means the gate has stopped seeing this upstream (a renamed tag
 *     scheme, a moved repository). Soft-failing that would pass forever.
 *  3. NO HOLD LIST. A release that must not be adopted yet keeps pull requests
 *     red until it is; the `no-external-quality` label is the existing way to
 *     skip every external gate on one pull request.
 *  4. THE FIX IS NOT A REWRITE BY THIS GATE. The pins live in the account
 *     submodule and the hashes come from downloads, so the message names the
 *     command there: `npm run real-provider:bump`.
 *
 * Usage:
 *   npm run check:ci-real-provider-pins
 *
 * Exit codes: 0 = current / deferred / could-not-check; 1 = a pin behind an
 * eligible release, an unreadable listing, or an unreadable lock file.
 *
 * ---- gate ----
 * step: Check real-provider pin upstream freshness
 * needs: node, submodules
 * id: check:ci-real-provider-pins
 * lane: quality-go
 * env-EXTERNAL_QUALITY_MODE: ${{ inputs.external_quality }}
 * env-GITHUB_TOKEN: ${{ github.token }}
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WK_GH_API_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { errorLines, GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { githubApiHeaders } from '../lib/github-token.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';

const CONSOLE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const LOCK_REL = 'private/account/e2e/real-provider.lock.json';
// Test seams: a fixture lock file, and a JSON map `{ "<owner>/<repo>": <the release list as the API returns it> }` read INSTEAD of the network. A repository absent from the map is the could-not-check case.
const LOCK_FILE = process.env.REAL_PROVIDER_LOCK_FILE || path.join(CONSOLE_ROOT, LOCK_REL);
const LISTING_FIXTURE = process.env.REAL_PROVIDER_FRESHNESS_FIXTURE;

const HTTP_TIMEOUT_MS = 15_000;
const STABLE_VERSION = /^\d+\.\d+\.\d+$/;

interface PinSource {
  /** The key of the pin in the lock file, and the bump command's flag. */
  key: 'bitwarden' | 'vaultwarden';
  display: string;
  /** owner/repo on github.com. */
  repo: string;
  /** What precedes the version in a release tag. bitwarden/clients is a monorepo, so its browser releases are told apart from web, desktop and cli by this. */
  tagPrefix: string;
}

const SOURCES: PinSource[] = [
  {
    key: 'bitwarden',
    display: 'Bitwarden browser extension',
    repo: 'bitwarden/clients',
    tagPrefix: 'browser-v',
  },
  { key: 'vaultwarden', display: 'Vaultwarden', repo: 'dani-garcia/vaultwarden', tagPrefix: '' },
];

interface Pin {
  version: string;
  publishedAt: string;
}

interface StableRelease {
  version: string;
  tag: string;
  /** Epoch ms, or null when the release carries no usable date. */
  publishedMs: number | null;
  publishedAt: string;
}

/** The listing answered and cannot be used: red, unlike an upstream that did not answer. */
class UnreadableListing extends Error {}

function readPins(): Record<PinSource['key'], Pin> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(LOCK_FILE, 'utf-8'));
  } catch (err) {
    throw new Error(
      `cannot read ${LOCK_FILE} (${(err as Error).message}); the account submodule must be checked out`
    );
  }
  const pins = {} as Record<PinSource['key'], Pin>;
  for (const src of SOURCES) {
    const entry = (parsed as Record<string, Partial<Pin> | undefined>)[src.key];
    if (typeof entry?.version !== 'string' || !STABLE_VERSION.test(entry.version)) {
      throw new Error(`${LOCK_FILE}: ${src.key}.version is not an x.y.z version`);
    }
    if (typeof entry.publishedAt !== 'string' || Number.isNaN(Date.parse(entry.publishedAt))) {
      throw new Error(`${LOCK_FILE}: ${src.key}.publishedAt is not a date`);
    }
    pins[src.key] = { version: entry.version, publishedAt: entry.publishedAt };
  }
  return pins;
}

/** x.y.z as three numbers; callers pass only strings STABLE_VERSION accepts. */
function triple(version: string): [number, number, number] {
  const [major, minor, patch] = version.split('.').map(Number);
  return [major, minor, patch];
}

/** Negative when `a` is older than `b`, positive when newer, 0 when equal. */
function compareVersions(a: string, b: string): number {
  const left = triple(a);
  const right = triple(b);
  return left[0] - right[0] || left[1] - right[1] || left[2] - right[2];
}

/** The repository's release list. Throws a plain Error when upstream cannot be reached. */
async function fetchListing(repo: string): Promise<unknown> {
  if (LISTING_FIXTURE) {
    const fixture = JSON.parse(fs.readFileSync(LISTING_FIXTURE, 'utf-8')) as Record<
      string,
      unknown
    >;
    if (!(repo in fixture)) throw new Error('not in fixture');
    return fixture[repo];
  }
  const res = await fetch(`${WK_GH_API_BASE}/repos/${repo}/releases?per_page=100`, {
    headers: githubApiHeaders('rediacc-real-provider-pin-freshness'),
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  try {
    return await res.json();
  } catch {
    throw new UnreadableListing('the response is not JSON');
  }
}

/** Every stable release under the source's tag prefix, newest version first. */
function stableReleases(listing: unknown, src: PinSource): StableRelease[] {
  if (!Array.isArray(listing)) throw new UnreadableListing('the response is not a release list');
  const out: StableRelease[] = [];
  for (const raw of listing as Array<Record<string, unknown> | null>) {
    const tag = typeof raw?.tag_name === 'string' ? raw.tag_name : '';
    if (!raw || raw.draft === true || raw.prerelease === true || !tag.startsWith(src.tagPrefix)) {
      continue;
    }
    const version = tag.slice(src.tagPrefix.length);
    if (!STABLE_VERSION.test(version)) continue;
    const publishedAt = typeof raw.published_at === 'string' ? raw.published_at : '';
    const publishedMs = Date.parse(publishedAt);
    out.push({
      version,
      tag,
      publishedMs: Number.isNaN(publishedMs) ? null : publishedMs,
      publishedAt: publishedAt || 'publish date unknown',
    });
  }
  if (out.length === 0) {
    throw new UnreadableListing(
      `the newest 100 releases hold no stable release tagged "${src.tagPrefix}<x.y.z>"`
    );
  }
  return out.sort((a, b) => compareVersions(b.version, a.version));
}

interface Finding {
  src: PinSource;
  pin: Pin;
  latest: StableRelease;
}

/** Judge every pin; the return value is the exit code. */
async function main(): Promise<number> {
  console.log('Real-provider pin freshness');
  console.log('='.repeat(60));

  const pins = readPins();
  const minReleaseAgeMs = getMinReleaseAgeMs();
  const nowMs = Date.now();

  const stale: Finding[] = [];
  const unreadable: string[] = [];

  for (const src of SOURCES) {
    const pin = pins[src.key];
    let releases: StableRelease[];
    try {
      releases = stableReleases(await fetchListing(src.repo), src);
    } catch (err) {
      const reason = (err as Error).message;
      if (err instanceof UnreadableListing) {
        unreadable.push(`${src.display} (${src.repo}): ${reason}`);
      } else {
        // FAIL SOFT: upstream did not answer. The next CI run asks again.
        console.log(`${YELLOW}? ${src.display}: could not check (${reason})${NC}`);
      }
      continue;
    }
    const newer = releases.filter((r) => compareVersions(r.version, pin.version) > 0);
    // A release with no date is treated as old enough: a dateless source must still surface a stale pin (the embed gate's rule).
    const eligible = newer.find(
      (r) =>
        r.publishedMs === null || !isWithinFreshnessWindow(r.publishedMs, nowMs, minReleaseAgeMs)
    );
    for (const r of newer) {
      if (eligible && compareVersions(r.version, eligible.version) <= 0) break;
      console.log(
        `${YELLOW}⏳ ${src.display}: ${r.version} (published ${r.publishedAt}) is inside the release-age window, deferred to the next UTC day after it${NC}`
      );
    }
    if (eligible) stale.push({ src, pin, latest: eligible });
    else
      console.log(`${GREEN}✓ ${src.display}: ${pin.version} is the newest eligible release${NC}`);
  }

  if (unreadable.length > 0) {
    console.error('');
    console.error(`${RED}✗ upstream answered with a release list this gate cannot use:${NC}`);
    for (const line of unreadable) console.error(`  ${line}`);
    errorLines(
      '  This is not a network failure, so it is not soft: the gate would never see a new',
      '  release again. Check the repository and its tag scheme against SOURCES in',
      '  scripts/gates/check-real-provider-pin-freshness.ts.'
    );
  }

  if (stale.length > 0) {
    console.error('');
    console.error(`${RED}✗ ${stale.length} real-provider pin(s) are behind upstream:${NC}`);
    for (const f of stale) {
      console.error(
        `  ${f.src.display}: pinned ${f.pin.version} (published ${f.pin.publishedAt})  ->  ${f.latest.version}, published ${f.latest.publishedAt} (${f.src.repo} release ${f.latest.tag})`
      );
    }
    const flags = stale.map((f) => `--${f.src.key} ${f.latest.version}`).join(' ');
    console.error('');
    console.error(`${YELLOW}TO FIX: bump ${LOCK_REL}, then prove the spec.${NC}`);
    errorLines(
      '  1. Rewrite the pin (version, every sha256, the image index digest, publishedAt):',
      `       (cd private/account/e2e && npm run real-provider:bump -- ${flags})`,
      '  2. Run the spec five times against a running account backend:',
      '       (cd private/account/e2e && npm run test:real-provider)',
      '     A failure saying the provider and "providesPrf" disagree lists its own steps.',
      '  3. Commit the lock file in private/account once the spec passes, then move the',
      "     console's submodule pointer. private/account/e2e/README.md, section",
      '     "Bumping a pin", has the details.'
    );
  }

  if (stale.length > 0 || unreadable.length > 0) return 1;
  console.log(`${GREEN}✓ Every real-provider pin is current (or deferred / uncheckable).${NC}`);
  return 0;
}

// An unreadable lock file lands here, as does a defect in the gate itself: neither may read as a pass.
process.exitCode = await main().catch((err: unknown) => {
  console.error(`${RED}✗ real-provider pin freshness: ${String((err as Error).message)}${NC}`);
  return 1;
});
