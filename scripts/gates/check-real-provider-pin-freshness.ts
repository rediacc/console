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
 * A SIBLING OF check-devcontainer-pin-freshness.ts and
 * check-embed-asset-freshness.ts, with the same policy:
 *  - FRESHNESS WINDOW: a release younger than the window in
 *    .ci/config/release-age.json is not a finding yet, and eligibility rounds to
 *    the next UTC day (scripts/lib/release-age.ts).
 *  - Drafts and pre-releases are ignored, as are tags that do not carry a plain
 *    x.y.z version after the prefix.
 *  - FAIL CLOSED ON NETWORK (operator ruling 2026-10-13). A pin whose release
 *    list was not obtained is a RED finding: DNS, connect and timeout failures,
 *    any HTTP error, a rate limit and a refused token all exit 1, and the
 *    finding names the pin, the host and path asked, the status or error code,
 *    and that the comparison did not happen. A green therefore always means
 *    every pin was compared. The request, its bounded retry (3 attempts, 15 s
 *    each, 2 s then 4 s between them) and the finding's wording are shared by
 *    every external gate, in scripts/lib/upstream.ts. The pins are asked
 *    concurrently, so the worst case is 51 s, inside the lane's 14 minutes.
 *
 * UPSTREAM ASKED: api.github.com, `GET /repos/<owner>/<repo>/releases` for
 * bitwarden/clients and dani-garcia/vaultwarden. Nothing else.
 *
 * WHERE IT DIFFERS:
 *  1. THE NEWEST ELIGIBLE RELEASE IS THE FINDING, not the newest release. The
 *     extension ships several times a month; a pin three releases behind stays
 *     red while the fourth release is still inside the window.
 *  2. A LISTING THAT HOLDS NO STABLE x.y.z RELEASE UNDER THE TAG PREFIX IS RED,
 *     as is a 200 that is not a release list: the gate has stopped seeing this
 *     upstream (a renamed tag scheme, a moved repository).
 *  3. NO HOLD LIST. A release that must not be adopted yet keeps pull requests
 *     red until it is; the `no-external-quality` label is the existing way to
 *     skip every external gate on one pull request.
 *  4. THE FIX IS NOT A REWRITE BY THIS GATE. The pins live in the account
 *     submodule and the hashes come from downloads, so the message names
 *     `npm run pins -- bump real-provider:<pin>`, whose driver runs
 *     `npm run real-provider:bump` there inside one transaction.
 *
 * HARD ON EVERY CADENCE (operator ruling 2026-10-13, "Everything fails closed,
 * nightly included"). The step runs `npm run check:ci-real-provider-pins`
 * directly, with no wrapper, so its exit 1 is red on a pull
 * request, on the nightly and on a dispatch alike. The one way it does not run
 * is the `no-external-quality` label on a pull request, and the job's
 * "Announce external gates held by label" step names this gate in the log when that
 * happens.
 *
 * Usage:
 *   npm run check:ci-real-provider-pins
 *
 * Exit codes: 0 = every pin was compared and is current or deferred; 1 = a pin
 * behind an eligible release, a pin that was not compared, an unreadable
 * listing, or an unreadable lock file.
 *
 * ---- gate ----
 * step: Check real-provider pin upstream freshness
 * needs: node, submodules
 * id: check:ci-real-provider-pins
 * lane: quality-go
 * env-GITHUB_TOKEN: ${{ github.token }}
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { errorLines, GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { bumpRemedy } from '../lib/pins/remedy.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import {
  emptyReleaseList,
  githubAsker,
  NotCompared,
  PinTally,
  UnreadableListing,
} from '../lib/upstream.js';

const CONSOLE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const LOCK_REL = 'private/account/e2e/real-provider.lock.json';
// Test seams: a fixture lock file, and a JSON map `{ "<owner>/<repo>": <the release list as the API returns it> }` read INSTEAD of the network. A repository absent from the map was not compared, which is red.
const LOCK_FILE = process.env.REAL_PROVIDER_LOCK_FILE || path.join(CONSOLE_ROOT, LOCK_REL);
const LISTING_FIXTURE = process.env.REAL_PROVIDER_FRESHNESS_FIXTURE;
// A third seam: another API base, so a test can stand a real HTTP server in for GitHub and an offline run can be driven by hand. The token is never sent to it.
const github = githubAsker(
  'rediacc-real-provider-pin-freshness',
  process.env.REAL_PROVIDER_API_BASE
);

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

/** The repository's release list. Throws NotCompared when it was not obtained (scripts/lib/upstream.ts holds the retry budget). */
async function fetchListing(src: PinSource): Promise<unknown> {
  if (LISTING_FIXTURE) {
    const fixture = JSON.parse(fs.readFileSync(LISTING_FIXTURE, 'utf-8')) as Record<
      string,
      unknown
    >;
    if (!(src.repo in fixture)) throw NotCompared.absentFromFixture(src.repo);
    return fixture[src.repo];
  }
  return github(`/repos/${src.repo}/releases?per_page=100`, src.display);
}

/** Every stable release under the source's tag prefix, newest version first. */
function stableReleases(listing: unknown, src: PinSource): StableRelease[] {
  if (!Array.isArray(listing)) throw new UnreadableListing('the response is not a release list');
  if (listing.length === 0) throw emptyReleaseList(src.repo);
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
  const tally = new PinTally('real-provider', SOURCES.length);
  const answers = await tally.askAll(SOURCES, fetchListing);

  for (const [index, src] of SOURCES.entries()) {
    const pin = pins[src.key];
    const answer = answers[index];
    let releases: StableRelease[];
    try {
      if (!answer || 'err' in answer) throw answer?.err ?? new Error('a pin was not asked');
      releases = stableReleases(answer.value, src);
    } catch (err) {
      tally.failed(`${src.display} (pinned ${pin.version})`, `${src.display} (${src.repo})`, err);
      continue;
    }
    tally.compared++;
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

  // The count is the claim: a green that compared fewer pins than SOURCES holds would be a pass without a check.
  const blind = tally.report({
    sources: 'SOURCES in scripts/gates/check-real-provider-pin-freshness.ts',
  });

  if (stale.length > 0) {
    console.error('');
    console.error(`${RED}✗ ${stale.length} real-provider pin(s) are behind upstream:${NC}`);
    for (const f of stale) {
      console.error(
        `  ${f.src.display}: pinned ${f.pin.version} (published ${f.pin.publishedAt})  ->  ${f.latest.version}, published ${f.latest.publishedAt} (${f.src.repo} release ${f.latest.tag})`
      );
    }
    // THE FIX, one line per stale pin (scripts/lib/pins/remedy.ts builds it). The real-provider driver runs `npm run real-provider:bump` in private/account/e2e inside the pins transaction, and its message draft carries the one step no gate can take: the spec against live providers.
    console.error('');
    console.error(`${YELLOW}TO FIX, per pin:${NC}`);
    for (const f of stale) console.error(bumpRemedy(`real-provider:${f.src.key}`));
    errorLines(
      '  then, before the commit, prove the new release against a running account backend:',
      '       (cd private/account/e2e && npm run test:real-provider)'
    );
  }

  if (stale.length > 0 || blind > 0) return 1;
  console.log(
    `${GREEN}✓ Every real-provider pin is current or deferred (${tally.compared} of ${SOURCES.length} compared with upstream).${NC}`
  );
  return 0;
}

// An unreadable lock file lands here, as does a defect in the gate itself: neither may read as a pass.
process.exitCode = await main().catch((err: unknown) => {
  console.error(`${RED}✗ real-provider pin freshness: ${String((err as Error).message)}${NC}`);
  return 1;
});
