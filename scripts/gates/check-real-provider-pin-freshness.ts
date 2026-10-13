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
 *  - Drafts and pre-releases are ignored, as are tags that do not carry a plain
 *    x.y.z version after the prefix.
 *
 * WHERE IT DIFFERS:
 *  1. FAIL CLOSED ON NETWORK (operator ruling 2026-10-13). The two siblings
 *     report an upstream that cannot be reached as could-not-check and exit 0.
 *     Here a pin whose release list was not obtained is a RED finding: DNS,
 *     connect and timeout failures, any HTTP error, a rate limit and a refused
 *     token all exit 1, and the finding names the pin, the host and path asked,
 *     the status or error code, and that the comparison did not happen. A green
 *     therefore always means every pin was compared. The price is stated in the
 *     ruling: a GitHub outage or rate limit blocks every pull request until it
 *     clears.
 *  2. A BOUNDED RETRY COMES FIRST. A request is tried up to MAX_ATTEMPTS (3)
 *     times, HTTP_TIMEOUT_MS (15 s) each, with BACKOFF_MS (2 s, then 4 s)
 *     between tries, for a failure that can clear in seconds: a network error,
 *     a timeout, 408, 429, a 5xx, and a 403 that carries Retry-After. A primary
 *     rate limit (403 with x-ratelimit-remaining 0), 401, and every other
 *     status are answered at once, as is a Retry-After above MAX_RETRY_AFTER_S.
 *     The pins are fetched concurrently, so the worst case is 51 s for the whole
 *     gate, inside the lane's 14 minutes.
 *  3. THE NEWEST ELIGIBLE RELEASE IS THE FINDING, not the newest release. The
 *     extension ships several times a month; a pin three releases behind stays
 *     red while the fourth release is still inside the window.
 *  4. A LISTING THAT ANSWERS BUT CANNOT BE READ IS RED. A 200 that is not a
 *     release list, or holds no stable release under the tag prefix at all,
 *     means the gate has stopped seeing this upstream (a renamed tag scheme, a
 *     moved repository).
 *  5. NO HOLD LIST. A release that must not be adopted yet keeps pull requests
 *     red until it is; the `no-external-quality` label is the existing way to
 *     skip every external gate on one pull request.
 *  6. THE FIX IS NOT A REWRITE BY THIS GATE. The pins live in the account
 *     submodule and the hashes come from downloads, so the message names the
 *     command there: `npm run real-provider:bump`.
 *
 * WHAT THE WRAPPER DOES WITH THE EXIT CODE. The step runs behind
 * rediacc_ci.quality.run_external_gate: `hard` on a pull request keeps the 1,
 * `soft` on the nightly and on a dispatch turns ANY 1 from this gate into a
 * warning and a step summary, a pin that was not compared included, and the
 * `no-external-quality` label keeps the step from running at all.
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
 * env-EXTERNAL_QUALITY_MODE: ${{ inputs.external_quality }}
 * env-GITHUB_TOKEN: ${{ github.token }}
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { WK_GH_API_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { errorLines, GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { githubApiHeaders } from '../lib/github-token.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';

const CONSOLE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const LOCK_REL = 'private/account/e2e/real-provider.lock.json';
// Test seams: a fixture lock file, and a JSON map `{ "<owner>/<repo>": <the release list as the API returns it> }` read INSTEAD of the network. A repository absent from the map was not compared, which is red.
const LOCK_FILE = process.env.REAL_PROVIDER_LOCK_FILE || path.join(CONSOLE_ROOT, LOCK_REL);
const LISTING_FIXTURE = process.env.REAL_PROVIDER_FRESHNESS_FIXTURE;
// A third seam: another API base, so a test can stand a real HTTP server in for GitHub and an offline run can be driven by hand. The token is never sent to it.
const API_BASE_OVERRIDE = process.env.REAL_PROVIDER_API_BASE;
const API_BASE = API_BASE_OVERRIDE || WK_GH_API_BASE;

// The retry budget. Worst case for one pin: 3 x 15 s of timeouts plus 2 s + 4 s of backoff = 51 s. The pins are fetched concurrently, so that is also the worst case for the gate.
const HTTP_TIMEOUT_MS = 15_000;
const MAX_ATTEMPTS = 3;
const BACKOFF_MS = [2_000, 4_000];
// A server that asks for a longer wait than this is not retried: the wait would not fit the budget above.
const MAX_RETRY_AFTER_S = 10;
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

/** The listing answered and cannot be used: red, with its own message about the tag scheme. */
class UnreadableListing extends Error {}

/** The listing was not obtained, so the pin was not compared: red. */
class NotCompared extends Error {
  constructor(
    /** The status or error code of the last attempt. */
    readonly what: string,
    /** host and path, with no query, no token and no header. */
    readonly asked: string,
    readonly attempts: number
  ) {
    super(what);
  }
}

/** One failed attempt: what answered, and whether asking again within the budget can help. */
interface Failure {
  what: string;
  retry: boolean;
  /** Seconds the server asked for, when it did. */
  retryAfterS: number | null;
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

/** What an HTTP status that is not 2xx means for this gate. */
function classifyStatus(res: Response): Failure {
  const header = res.headers.get('retry-after');
  const retryAfterS = header !== null && /^\d+$/.test(header) ? Number(header) : null;
  const status = res.status;
  if (status === 403 && res.headers.get('x-ratelimit-remaining') === '0') {
    const resetS = Number(res.headers.get('x-ratelimit-reset'));
    const reset =
      Number.isFinite(resetS) && resetS > 0
        ? `, resets ${new Date(resetS * 1000).toISOString()}`
        : '';
    // The primary limit resets on the hour, so no wait inside the budget clears it.
    return { what: `HTTP 403 (rate limit${reset})`, retry: false, retryAfterS };
  }
  if (status === 429 || (status === 403 && retryAfterS !== null)) {
    return { what: `HTTP ${status} (rate limit)`, retry: true, retryAfterS };
  }
  if (status === 401 || status === 403) {
    return { what: `HTTP ${status} (the token was refused)`, retry: false, retryAfterS };
  }
  return { what: `HTTP ${status}`, retry: status === 408 || status >= 500, retryAfterS };
}

/** What a request that never produced a response means: the error's own code, never its message, which can carry a URL. */
function classifyThrown(err: unknown): Failure {
  const name = err instanceof Error ? err.name : 'Error';
  if (name === 'TimeoutError' || name === 'AbortError') {
    return { what: `timeout after ${HTTP_TIMEOUT_MS / 1000} s`, retry: true, retryAfterS: null };
  }
  const cause = err instanceof Error ? (err.cause as { code?: unknown } | undefined) : undefined;
  const code = typeof cause?.code === 'string' ? cause.code : name;
  return { what: `network error ${code}`, retry: true, retryAfterS: null };
}

/** One request. Returns the parsed body, or the failure; throws UnreadableListing for a 200 that is not JSON. */
async function attemptListing(url: URL): Promise<{ listing: unknown } | Failure> {
  const headers = githubApiHeaders('rediacc-real-provider-pin-freshness');
  // The token belongs to api.github.com and to nothing a seam points at.
  if (API_BASE_OVERRIDE) delete headers.Authorization;
  let res: Response;
  try {
    res = await fetch(url, { headers, signal: AbortSignal.timeout(HTTP_TIMEOUT_MS) });
  } catch (err) {
    return classifyThrown(err);
  }
  if (!res.ok) return classifyStatus(res);
  try {
    return { listing: await res.json() };
  } catch {
    throw new UnreadableListing('the response is not JSON');
  }
}

/** The repository's release list, asked for up to MAX_ATTEMPTS times. Throws NotCompared when it was not obtained. */
async function fetchListing(src: PinSource): Promise<unknown> {
  if (LISTING_FIXTURE) {
    const fixture = JSON.parse(fs.readFileSync(LISTING_FIXTURE, 'utf-8')) as Record<
      string,
      unknown
    >;
    if (!(src.repo in fixture)) {
      throw new NotCompared('no entry in the fixture', `fixture ${src.repo}`, 0);
    }
    return fixture[src.repo];
  }
  const url = new URL(`${API_BASE}/repos/${src.repo}/releases?per_page=100`);
  const asked = `${url.host}${url.pathname}`;
  for (let attempt = 1; ; attempt++) {
    const answer = await attemptListing(url);
    if ('listing' in answer) return answer.listing;
    const waitMs = Math.max(BACKOFF_MS[attempt - 1] ?? 0, (answer.retryAfterS ?? 0) * 1000);
    const fits = (answer.retryAfterS ?? 0) <= MAX_RETRY_AFTER_S;
    if (attempt >= MAX_ATTEMPTS || !answer.retry || !fits) {
      throw new NotCompared(answer.what, asked, attempt);
    }
    console.log(
      `${YELLOW}? ${src.display}: attempt ${attempt} of ${MAX_ATTEMPTS} failed (${answer.what}), asking again in ${waitMs / 1000} s${NC}`
    );
    await sleep(waitMs);
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
  const notCompared: string[] = [];
  let compared = 0;

  // Asked concurrently so the retry budget is spent once, not once per pin; judged in SOURCES order below.
  const answers = await Promise.all(
    SOURCES.map((src) =>
      fetchListing(src).then(
        (listing) => ({ listing }),
        (err: unknown) => ({ err })
      )
    )
  );

  for (const [index, src] of SOURCES.entries()) {
    const pin = pins[src.key];
    const answer = answers[index];
    let releases: StableRelease[];
    try {
      if ('err' in answer) throw answer.err;
      releases = stableReleases(answer.listing, src);
    } catch (err) {
      if (err instanceof UnreadableListing) {
        unreadable.push(`${src.display} (${src.repo}): ${err.message}`);
      } else if (err instanceof NotCompared) {
        // FAIL CLOSED: a pin that was not compared is a finding, not a note.
        notCompared.push(
          `${src.display} (pinned ${pin.version}): GET ${err.asked} -> ${err.what}, after ${err.attempts} attempt(s)`
        );
      } else {
        throw err;
      }
      continue;
    }
    compared++;
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

  if (notCompared.length > 0) {
    console.error('');
    console.error(
      `${RED}✗ ${notCompared.length} real-provider pin(s) were NOT compared with upstream:${NC}`
    );
    for (const line of notCompared) console.error(`  ${line}`);
    errorLines(
      '  The comparison did not happen, so this run says nothing about whether these pins',
      '  are current, and it fails closed instead of passing unchecked. Nothing in the tree',
      '  needs a change for this finding: run the gate again once GitHub answers',
      '  (https://www.githubstatus.com). A rate limit locally means the request went out',
      '  without a token; `gh auth login` or GITHUB_TOKEN supplies one.'
    );
  }

  if (unreadable.length > 0) {
    console.error('');
    console.error(`${RED}✗ upstream answered with a release list this gate cannot use:${NC}`);
    for (const line of unreadable) console.error(`  ${line}`);
    errorLines(
      '  The comparison did not happen for these pins, and this is not a network failure:',
      '  the gate would never see a new release again. Check the repository and its tag',
      '  scheme against SOURCES in scripts/gates/check-real-provider-pin-freshness.ts.'
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

  // The count is the claim: a green that compared fewer pins than SOURCES holds would be a pass without a check.
  if (stale.length > 0 || unreadable.length > 0 || notCompared.length > 0) return 1;
  if (compared !== SOURCES.length) {
    console.error(`${RED}✗ compared ${compared} of ${SOURCES.length} pins and found nothing${NC}`);
    return 1;
  }
  console.log(
    `${GREEN}✓ Every real-provider pin is current or deferred (${compared} of ${SOURCES.length} compared with upstream).${NC}`
  );
  return 0;
}

// An unreadable lock file lands here, as does a defect in the gate itself: neither may read as a pass.
process.exitCode = await main().catch((err: unknown) => {
  console.error(`${RED}✗ real-provider pin freshness: ${String((err as Error).message)}${NC}`);
  return 1;
});
