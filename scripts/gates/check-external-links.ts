/**
 * External link validator for documentation.
 *
 * Extracts all external URLs from every markdown tree listed in SCAN_ROOTS and
 * verifies each one returns a successful HTTP status.
 *
 * Run: npx tsx scripts/gates/check-external-links.ts
 *
 * Features:
 * - Extracts URLs from markdown links [text](url) and bare https:// references
 * - Drops placeholder URLs (angle brackets, braces, shell vars, ellipses) BEFORE
 *   they are cleaned, so a truncated template is never mistaken for a real link
 * - Deduplicates URLs across all files
 * - Concurrent validation with rate limiting
 * - Allowlist for known-flaky URLs (e.g., sites that block bots)
 * - Liveness audit of the allowlist itself, so an exemption cannot outlive its
 *   reason unnoticed (see "ALLOWLIST LIVENESS" below)
 * - Reports broken links with file location
 * - Exit code 1 on any broken link (CI-friendly)
 *
 * FAILS CLOSED ON EVERY CADENCE (operator ruling 2026-10-14, "Extend to all
 * seven"). Each request goes through scripts/lib/upstream.ts: three attempts,
 * 15 s each, 2 s then 4 s between them. A link whose host gave a definite
 * answer (a 404, a 410, a 403 after the GET fallback) is BROKEN, a finding in
 * the tree. A link whose host gave no answer (a network error, a timeout, a 5xx,
 * a 429 or rate limit) was NOT checked, and is a red finding with the sentence
 * `UPSTREAM REACHABILITY FAILURE`, so `ci-trace.py --why` reads it as the
 * outage it is. The step runs the gate with no wrapper, so
 * both are red on the nightly too; the `no-external-quality` label on a pull
 * request is the one hold, and its job's announcer names this gate.
 * `EXTERNAL_LINKS_FIXTURE_ROOT` is the gate test's seam: the scan runs over that
 * tree instead, with an EMPTY allowlist and KNOWN_BROKEN (a fixture carries none
 * of the real tree's exemptions, and the liveness audit would otherwise fail on
 * every entry the fixture does not cite), and a 127.0.0.1 URL is checked rather
 * than skipped, so a link can point at the test's stub server. The run prints
 * that it is a fixture run.
 *
 * ---- gate ----
 * step: External links
 * selftest: true
 * needs: node
 * lane: quality-content
 * slow: true
 * when: inputs.external_quality != 'skip'
 * env-GITHUB_TOKEN: ${{ github.token }}
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { globSync } from 'glob';
import {
  WK_GH_API_BASE,
  WK_GH_ORIGIN,
  WK_GH_REPO,
  WK_RELEASES_ORIGIN,
  WK_SITE_ORIGIN,
} from '../../packages/shared/src/config/well-known.generated.js';
import { emitFinding } from '../ci-runner/findings.js';
import { githubToken } from '../lib/github-token.js';
import { askUpstream, NotCompared, reportUnreachable } from '../lib/upstream.js';

// Every markdown tree whose external links are load-bearing. Each root is guarded independently below: a root that matches zero files is a moved or renamed path, never a legitimate state, and it fails the run rather than silently shrinking the corpus (root pattern 1 in `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`).
//
// packages/www/src/content/{docs,blog} are published to the website; docs/,
// .ci/docs/ and .github/ are the operator-facing runbooks whose links get followed under time pressure; packages/cli/README.md ships in the npm tarball. Measured at the time of writing: 781 + 66 + 66 + 2 + 2 + 3 files.
const SCAN_ROOTS = [
  'packages/www/src/content/docs',
  'packages/www/src/content/blog',
  'docs',
  '.ci/docs',
  '.github',
  'packages/cli',
];

// The gate test's seam; see the header.
const FIXTURE_ROOT = process.env.EXTERNAL_LINKS_FIXTURE_ROOT || undefined;

const CONCURRENCY = 5;
// THE OUTAGE BREAKER. With no network every link spends the full retry budget, which over this corpus outlasts the job's timeout and would end the run as a cancelled step rather than as the finding below. Once this many links in a row have come back unreachable and not one host has answered, the rest are not asked: the run is red either way, and the finding names the hosts that were tried.
const OUTAGE_BREAKER = 20;

// The liveness re-probe is a hint for a human, not a build verdict, so it gets a tighter budget and no retries: we only want to know whether the host answers cleanly right now.
const LIVENESS_TIMEOUT_MS = 8_000;

// Sites that aggressively block all automated requests (403 even with browser UA + curl). Verified manually with a real browser. Keep this list minimal.
const TREE_ALLOWLISTED_DOMAINS = new Set([
  'www.hhs.gov', // US HHS - blocks all automated requests
  'www.sec.gov', // US SEC - blocks all automated requests
  'pd.rkn.gov.ru', // Russia Roskomnadzor - unreachable from most locations
  'sdaia.gov.sa', // Saudi SDAIA - connection refused from non-Saudi IPs
  'www.pipc.go.kr', // South Korea PIPC - extremely slow, times out in CI
  'www.legislation.gov.au', // Australia legislation - intermittent timeouts from CI runners
  // billauer.co.il - the MIRROR IMAGE of every other entry here, which is why it is in this list rather than KNOWN_BROKEN. Measured 2026-09-16 from three vantage points: a GitHub runner fetched it fine (the liveness audit reported `1 sampled URL(s) all returned 2xx` and told us to drop the KNOWN_BROKEN entry), while this dev network answered HTTP 000 with no TCP connect at all --
  // three times from the host and twice more from a container on a separate egress path. So the host is selectively reachable BY SOURCE NETWORK, and "fixed upstream" is not what happened.
  //
  // Deleting the KNOWN_BROKEN entry on the runner's word alone would have traded a CI warning for a permanent local red: verified by doing it, after which the gate reported `BROKEN [fetch failed]` and exit 1 here while CI was green. An IP-dependent block is what this list is for; KNOWN_BROKEN means the link is broken, and it is not.
  //
  // Cited once, docs/code-signing-guide.md:309, as attribution for the eSigner overage claim -- a citation, not an instruction, so the URL stays in prose.
  'billauer.co.il',
  'ariregister.rik.ee', // Estonia e-Business Register - intermittent from CI runners: TIMEOUT against the 15s budget on one run and 503 on the next (jobs 104615289932, 104616780132); answers 200 from a non-datacenter IP but slowly, 9.7s and 13.9s in three probes that also returned one 500, so it is unstable rather than dead
  'www.iso.org', // ISO standards - returns 403 to non-browser User-Agent (anti-scraping)
  'www.meity.gov.in', // India MeitY - intermittent fetch failures from CI runners (Azure US-East), reachable from browsers
  'eur-lex.europa.eu', // EU EUR-Lex - returns 403 to CI runners (Cloudflare/anti-scraping), reachable from browsers
  'www.ftc.gov', // US FTC - returns 503/403 to CI runners (Akamai anti-bot), reachable from browsers
  // GnuPG handbook - `fetch failed` from a GitHub-hosted runner (run for 07c5e1c76, Quality/Content 'External links'), after this checker's own two retries AND its last-chance GET.
  //
  // MEASURED, AND THE MEASUREMENT IS THE POINT: from a non-datacenter IP the same URL answered 200 once and then 000 six times running (three HEAD, three GET, 20s timeouts). Not "live" and not "dead" -- INTERMITTENT, which is why one probe would have justified either verdict. docs/ci-overhaul/ 06-progress.md:3201 records the same host answering 000 from two networks on 2026-07-30,
  // so this is a standing property of gnupg.org rather than one bad afternoon.
  //
  // Two things I checked before believing any of it, because both would have made the reading a lie: this sandbox has NO IPv6 egress at all (v6 to debian.org and cloudflare.com also answers 000), so nothing here can be concluded about gnupg's AAAA record; and the IPv4 path is the one all the numbers above come from. Recheck by removing this line -- if the host starts answering CI
  // reliably the gate passes without it.
  'www.gnupg.org',
  // Debian securing-debian-manual - `fetch failed` from GitHub-hosted runners on 2026-08-05 (run 30990002964), after this checker's own two retries AND its last-chance GET, so not a one-shot blip. Measured rather than assumed: the same URL answers 200 six times out of six (three HEAD, three GET) from a non-datacenter IP, in ~0.6s. The page is live; debian.org simply does not
  // answer this runner. Recheck by removing this line -- if the host starts answering CI again the gate will pass without it.
  'www.debian.org',
  // Apple's D-U-N-S enrolment page - returns HTTP 500 to GitHub-hosted runners (run 33463..., Quality/Content 'External links'), and 403 to a HEAD request
  // from anywhere. Measured rather than assumed, with this file's own browser
  // User-Agent from a non-datacenter IP: HEAD 403/403/403, GET 200/200/200, all in ~0.7-0.95s. So the page is live and Apple simply refuses HEAD outright and refuses datacenter IPs with a server error rather than a 403 -- the same shape as www.sectigo.com below, where a 500 reads as "the page is broken" instead of "you are a bot". The link is correct; it is cited three times in
  // docs/code-signing-guide.md as the free route to a D-U-N-S number. Recheck by removing this line -- if the host starts answering CI the gate passes without it.
  'developer.apple.com',
  // Sectigo code-signing product page - returns HTTP 500 to GitHub-hosted runners (run 31916185063, Quality/Content), which is a server error rather than a 403, so it reads as "the page is broken" instead of "you are a bot". Measured rather than assumed: the same URL answers 200 six times out of six
  // from a non-datacenter IP -- three HEAD in ~1.8s, three GET in ~0.2s -- with
  // this file's own browser User-Agent. The link is correct and the page is live. It predates this wave (b8e332b73, on main); nothing here changed it. Recheck by removing this line: the liveness audit below already warns when an allowlisted domain starts answering CI again, so the exemption cannot outlive its reason quietly.
  'www.sectigo.com',
  'www.dataprotection.ie', // Ireland DPC - whole domain unreachable from CI/datacenter IPs (connection fails at site root, not just deep links); the Meta-fine press release resolves from browsers
  // Brazil Planalto (LGPD, Lei 13.709/2018 full text) - ECONNRESET to GitHub-hosted runners, reported by this checker as `fetch failed`. Measured rather than assumed: the SAME request, using this file's own buildHeaders() UA and Accept, returns 200 six times out of six (three HEAD, three GET) from a non-datacenter IP. Without a browser UA the same host times out, and the domain
  // root answers 200 either way. So the deep path is filtered by source IP and by client fingerprint, not dead.
  'www.planalto.gov.br',
  // Microsoft Azure marketing/pricing pages - TIMEOUT from GitHub-hosted runners, twice in a row (runs 30445030549 and 30445586347), including after the last-chance GET fallback was added. Measured from a non-datacenter IP: the host root answers 200 in 6.3s and the page itself 200 in 4.2s, and the page answers 404 to HEAD three times out of three while serving GET fine. So two
  // separate things are true and only one of them is fixable here: the page does not implement HEAD (fixed generally by the GET fallback), and the host is unreachable from runner IPs (not fixable, hence this entry). Same class as www.planalto.gov.br above.
  'azure.microsoft.com',
  // VS Code Marketplace extension pages - BROKEN [503] on run 32000731266 (Quality/Content), after this checker's own two retries and its last-chance GET. Measured rather than assumed, with this file's own browser User-Agent: HEAD answers 404 three times out of three (~0.2s) and GET times out at 20s three times out of three, while the domain ROOT answers 503 -- so this is the
  // whole host refusing automated clients, not a dead item page. An unauthenticated GET without the UA returned 200 once and 503 twice in the same minute, which is the same refusal arriving non-deterministically. The URL itself is correct: ms-vscode-remote.remote-ssh is the canonical Remote-SSH extension id, referenced from the cli-contract i18n data in all 13 locales. It predates
  // this wave; nothing in 09654cc45 touched those files. Same class as azure.microsoft.com above -- HEAD unimplemented AND the host unreachable from automated clients, and only the first half is fixable here. Recheck by removing this line: the liveness audit below warns when an allowlisted domain starts answering again, so the exemption cannot outlive its reason quietly.
  'marketplace.visualstudio.com',
  // Own infrastructure -- only available after releases, not during CI
  new URL(WK_RELEASES_ORIGIN).host,
  // SSL.com's reseller site. Surfaced by widening the scan to docs/. Measured 2026-07-29 with this file's own headers: BOTH the deep resource page and the bare domain root answer 403, so it is a whole-domain WAF block on the client rather than a dead page; it renders in a browser.
  'signmycode.com',
]);
const ALLOWLISTED_DOMAINS: ReadonlySet<string> = FIXTURE_ROOT
  ? new Set()
  : TREE_ALLOWLISTED_DOMAINS;

// Links that are KNOWN DEAD and cannot be fixed from this file, keyed by the exact URL rather than by domain so the exemption cannot spread. Each entry is a work order, not an exemption: auditAllowlist() FAILS the build when the URL stops appearing in the docs (the doc got fixed, so delete the entry) and WARNS when the URL starts answering 200 again (fixed upstream).
const TREE_KNOWN_BROKEN = new Map<string, string>([
  // A DEAD COMMAND, not just a dead link, and the widened scan is what found it. Both docs used to tell the operator to run:
  //   ACCOUNT_ED25519_PUBLIC_KEY="$(curl -fsS https://www.rediacc.com/api/public/account-key)"
  // Measured 2026-07-29 and again 2026-08-05: that path is 404 on www, edge, eu, us and asia, and the string "account-key" appears nowhere in private/account/src, so the route does not exist rather than having moved. www.rediacc.com no longer serves the account API at all -- /account/api/v1/** answers 410 with "Account API is served by regional workers (eu/us/asia.rediacc.com)".
  // Because of `-f`, the documented command exits 22 and the variable is assigned the EMPTY string, so the build succeeds and every prod-signed license fails as invalid_signature -- precisely the
  // failure the RDC_RENET_LICENSE=1 repro exists to diagnose.
  //
  // BOTH CALL SITES ARE NOW FIXED, which is why this reason no longer names a line number: CLAUDE.md corrected its copy 2026-07-29, and docs/dev-environments.md was corrected 2026-08-05 (it had been missed, and still shipped the failing one-liner for a week after the other was fixed). The answer was not a replacement URL but the absence of one: the value is a GitHub organisation
  // secret, which is write-only, so it must be pasted locally and referenced directly in CI. There is no live endpoint to point at -- the regional https://eu.rediacc.com/account/api/v1/.well-known/server-info (200) publishes the X25519 config key, not the Ed25519 signing key.
  //
  // The entry STAYS because both files still name the dead URL in prose, while explaining why not to call it. Removing it would re-red the link check.
  [
    `${WK_SITE_ORIGIN}/api/public/account-key`,
    'route does not exist on any host (404 on www/edge/eu/us/asia); both docs now cite it only to warn against it, never as a command',
  ],
  // NOTE: a comment block for a gnupg.org entry used to sit here, describing the domain as unreachable from two networks on 2026-07-30. Its ENTRY is gone -- removed when the host came back -- and the prose outlived it, ending mid-sentence where the deleted line used to be. A reason with no entry reads as an entry to a skimming reader, so it is removed rather than left as
  // furniture. gnupg.org is handled in ALLOWLIST_DOMAINS above, where the current measurement lives.
]);
const KNOWN_BROKEN: ReadonlyMap<string, string> = FIXTURE_ROOT ? new Map() : TREE_KNOWN_BROKEN;

// Patterns matched against the RAW regex capture, before any punctuation cleaning. A template that the URL regex truncated mid-token (it stops at `>` and whitespace) still carries its opening delimiter here, and the cleaning step would otherwise destroy the evidence: `https://media.rediacc.com/...` becomes `https://media.rediacc.com/` once trailing dots are stripped, which looks
// like a perfectly real link and 404s.
const PLACEHOLDER_PATTERNS = [
  /[<>]/, // <node-ip>, <some-path>.mp4, <port>
  /[{}]/, // {service}.{repo}, ${SERVICE_IP}
  /\$\{?[A-Za-z_]/, // BARE shell vars too: $CLOUDFLARE_ACCOUNT_ID, $ZONE
  /\.\.\./, // https://media.rediacc.com/...  (elided path)
];

// URL patterns that are not real links (examples, templates, localhost). These appear in documentation code blocks and should never be fetched.
const SKIP_PATTERNS = [
  // RFC 2606 reserved domains/TLDs: example.com/net/org and any host ending in .example/.invalid/.test never resolve by design (this is the whole point of reserving them), so a fetch failure there is not a broken link.
  /^https?:\/\/(?:[^/]*\.)?example\.(com|net|org)/,
  /^https?:\/\/[^/]*\.(example|invalid|test)(:\d+)?(\/|$)/,
  ...(FIXTURE_ROOT ? [] : [/^https?:\/\/127\.\d+\.\d+\.\d+/, /^https?:\/\/localhost/]),
  // Inline-code artifact. A URL captured with a backtick anywhere in it came out of `...` in prose, which in these docs always means an API base, a host to configure, or an endpoint template -- never a navigable page. Measured, not assumed: the two such URLs that resolve at all, https://media.rediacc.com and https://eu.rediacc.com/account/api/v1, both answer 404 by design
  // (object-store root and API root, no index document). The previous form of this pattern was `^https?://[^/]*\`` and so only caught a backtick before the first slash, which is why the deeper ones were being reported as broken.
  /`/,
  // GitHub placeholder URLs used in API examples (org/repo, OAuth endpoints)
  /^https:\/\/github\.com\/org\//,
  /^https:\/\/github\.com\/login\/oauth\//,
  /^https:\/\/api\.github\.com\/user$/,
  // Government/regulatory sites that block CI runners (403/geo-restricted/fetch failed)
  /^https?:\/\/www\.edpb\.europa\.eu/,
  /^https?:\/\/kvkk\.gov\.tr/,
  /^https?:\/\/oag\.ca\.gov/,
  // Internal rediacc.io subdomains used in code examples (not reachable from CI)
  /^https?:\/\/[^/]*\.rediacc\.io/,
  // Internal docker-compose service names referenced in collector config snippets
  /^https?:\/\/otel-collector(:\d+)?/,
  // UAE gov site is intermittently blocked by Cloudflare to CI runners
  /^https?:\/\/u\.ae\//,
  // Self-references to rediacc/console main: feature branches reference paths
  // that only exist after the PR merges, so verifying them in pre-merge CI
  // produces a false 404. GitHub's repo is ours; treat as trusted.
  /^https?:\/\/github\.com\/rediacc\/console/,
  // Authenticated API endpoints quoted verbatim from runbooks. These are not
  // pages and cannot answer 200 to an anonymous GET by construction:
  //   api.cloudflare.com/client/v4/**      -> 400 without a bearer token
  //   <account>.r2.cloudflarestorage.com   -> 400, S3 API needs a SigV4 signature
  // Both measured 2026-07-29. Fetching them would only ever assert that
  // Cloudflare still rejects unauthenticated callers.
  /^https:\/\/api\.cloudflare\.com\/client\/v4\//,
  /^https:\/\/[a-f0-9]{32}\.r2\.cloudflarestorage\.com/,
];

interface LinkLocation {
  file: string;
  line: number;
}

interface LinkEntry {
  url: string;
  locations: LinkLocation[];
}

function isPlaceholder(raw: string): boolean {
  return PLACEHOLDER_PATTERNS.some((p) => p.test(raw));
}

function extractLinks(filePath: string): {
  links: Map<string, LinkLocation[]>;
  placeholders: number;
} {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const links = new Map<string, LinkLocation[]>();
  const relPath = path.relative(process.cwd(), filePath);
  let placeholders = 0;

  // Match markdown links [text](https://...) and bare URLs https://...
  const urlRegex = /https?:\/\/[^\s)\]>"',]+/g;

  for (let i = 0; i < lines.length; i++) {
    const matches = lines[i].matchAll(urlRegex);
    for (const match of matches) {
      // Placeholder detection runs on the RAW capture. Cleaning below is
      // lossy and would hide the very characters that mark a template.
      if (isPlaceholder(match[0])) {
        placeholders++;
        continue;
      }
      // Clean trailing punctuation that's not part of the URL
      let url = match[0].replace(/[.),:;]+$/, '');
      // Remove trailing markdown artifacts
      url = url.replace(/\)$/, '');

      if (!links.has(url)) {
        links.set(url, []);
      }
      links.get(url)!.push({ file: relPath, line: i + 1 });
    }
  }

  return { links, placeholders };
}

function shouldSkip(url: string): boolean {
  // Check skip patterns first (examples, templates, localhost)
  for (const pattern of SKIP_PATTERNS) {
    if (pattern.test(url)) return true;
  }
  return false;
}

function hostnameOf(url: string): string | null {
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

function isAllowlisted(url: string): boolean {
  const hostname = hostnameOf(url);
  return hostname !== null && ALLOWLISTED_DOMAINS.has(hostname);
}

/**
 * Build request headers. For api.github.com URLs attach GITHUB_TOKEN so
 * anonymous rate-limiting doesn't flap the check.
 */
function buildHeaders(url: string): Record<string, string> {
  const headers: Record<string, string> = {
    'User-Agent':
      'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    Accept: 'text/html,application/xhtml+xml,*/*',
  };
  // Either name: this site read only GITHUB_TOKEN and was the reason every local
  // invocation set the same value twice. See scripts/lib/github-token.ts.
  const token = githubToken();
  if (token && /^https:\/\/api\.github\.com\//.test(url)) {
    headers['Authorization'] = `Bearer ${token}`;
    headers['Accept'] = 'application/vnd.github+json';
  }
  return headers;
}

/**
 * github.com HTML pages (issues, PRs, trees, blobs) frequently 401 from CI
 * runner IP ranges behind Cloudflare anti-bot, even with a Bearer token —
 * the HTML layer doesn't accept Authorization. Rewrite supported paths to
 * the api.github.com equivalent so auth actually applies; the API returns
 * 200 for existing resources and 404 for deleted ones.
 */
// github.com top-level paths that look like /<owner>/<repo> but are site pages, not repositories.
const GH_NON_REPO_OWNERS = new Set([
  'about',
  'apps',
  'collections',
  'enterprise',
  'events',
  'features',
  'marketplace',
  'orgs',
  'pricing',
  'settings',
  'sponsors',
  'topics',
  'users',
]);

export function toApiUrl(url: string): string | null {
  // A bare repo page (optional trailing slash, query or fragment) maps to the repos endpoint.
  const bare = url.match(/^https:\/\/github\.com\/([^/?#]+)\/([^/?#]+)\/?(?:[?#].*)?$/);
  if (bare) {
    if (GH_NON_REPO_OWNERS.has(bare[1].toLowerCase())) return null;
    return `${WK_GH_API_BASE}/repos/${bare[1]}/${bare[2]}`;
  }
  const m = url.match(
    /^https:\/\/github\.com\/([^/]+)\/([^/]+)\/(issues|pull|tree|blob)\/(.+?)(?:[?#].*)?$/
  );
  if (!m) return null;
  const [, owner, repo, kind, rest] = m;
  if (kind === 'issues' || kind === 'pull') {
    const num = rest.split('/')[0];
    if (!/^\d+$/.test(num)) return null;
    // The issues endpoint returns both issues and PRs (PRs are issues with
    // a pull_request field), so a single lookup works for either form.
    return `${WK_GH_API_BASE}/repos/${owner}/${repo}/issues/${num}`;
  }
  // tree and blob: check that the ref + path exists via the contents endpoint.
  // rest is <ref>/<path...>; collapse into contents/<path>?ref=<ref>.
  const slash = rest.indexOf('/');
  if (slash === -1) {
    // /tree/<branch> with no path — verify the branch exists.
    return `${WK_GH_API_BASE}/repos/${owner}/${repo}/branches/${rest}`;
  }
  const ref = rest.slice(0, slash);
  const path = rest.slice(slash + 1);
  return `${WK_GH_API_BASE}/repos/${owner}/${repo}/contents/${path}?ref=${encodeURIComponent(ref)}`;
}

// HEAD answers these from servers that serve the same URL fine to GET: 405 (HEAD not implemented), 404 (Azure), and 401/403/429 from GitHub and Cloudflare anti-bot, where a plain GET with a browser UA and/or the token answers 200.
const GET_FALLBACK_STATUSES = new Set([401, 403, 404, 405, 429]);

type LinkVerdict =
  | { kind: 'ok' }
  | { kind: 'broken'; status: number | string }
  | { kind: 'unreachable'; err: NotCompared };

/** One method against one URL through the shared retry budget. */
async function ask(url: string, method: 'GET' | 'HEAD', maxAttempts?: number): Promise<void> {
  await askUpstream({ url, method, headers: buildHeaders(url), who: url, maxAttempts });
}

async function checkUrl(original: string): Promise<LinkVerdict> {
  // Rewrite github.com HTML URLs to api.github.com so GITHUB_TOKEN actually authorises the request. Only used when GITHUB_TOKEN is available.
  const url = (githubToken() && toApiUrl(original)) || original;
  let headFailure: NotCompared;
  try {
    await ask(url, 'HEAD');
    return { kind: 'ok' };
  } catch (err) {
    if (!(err instanceof NotCompared)) throw err;
    headFailure = err;
  }
  // Some servers do not implement HEAD, or refuse it to a client they would serve a GET. Ask again with GET, under the same budget.
  if (headFailure.status !== null && GET_FALLBACK_STATUSES.has(headFailure.status)) {
    try {
      await ask(url, 'GET');
      return { kind: 'ok' };
    } catch (err) {
      if (!(err instanceof NotCompared)) throw err;
      return err.unreachable
        ? { kind: 'unreachable', err }
        : { kind: 'broken', status: err.status ?? err.what };
    }
  }
  // LAST-CHANCE GET, and it is not belt-and-braces. The status fallback above only fires when HEAD *answers*; a HEAD that hangs or is refused never tries GET at all, so a host that simply does not serve HEAD would be reported as unreachable.
  //
  // Measured on https://azure.microsoft.com/pricing/calculator/, which failed this checker in CI with TIMEOUT: from a residential IP the same URL answers 404 to HEAD three times out of three and 200 to GET, with and without a browser UA. On the runner the HEAD hung instead of 404ing, so even the status fallback could not save it. The page is live either way.
  //
  // ONE attempt: HEAD has already spent the full budget on this URL. A failed rescue does not replace the original diagnosis.
  if (headFailure.unreachable) {
    try {
      await ask(url, 'GET', 1);
      return { kind: 'ok' };
    } catch (err) {
      if (!(err instanceof NotCompared)) throw err;
      return { kind: 'unreachable', err: headFailure };
    }
  }
  return { kind: 'broken', status: headFailure.status ?? headFailure.what };
}

// --------------------------------------------------------------------------- ALLOWLIST LIVENESS --------------------------------------------------------------------------- ALLOWLISTED_DOMAINS is thirteen hand-written claims of the form "verified manually in a real browser". Nothing re-checked them, so two failure modes were invisible: an entry whose site stopped blocking bots
// (dead weight that hides real 404s behind it forever), and a domain that stopped existing altogether (the link is dead, and the allowlist is what makes it look fine).
//
// TIERING -- deliberate, and the two halves are split on determinism:
//
// FAIL (offline, deterministic): an allowlist entry that no URL in the corpus references any more, and a KNOWN_BROKEN url that has left the docs. These are pure set arithmetic over the tree, they cannot flap, and a stale entry is exactly the dead weight this section exists to catch. Same policy as check-suppression-liveness.ts.
//
// WARN (network, non-deterministic): the re-probe result. It must NOT fail the build. Every entry in the list documents an IP- and fingerprint-dependent block -- www.planalto.gov.br's own comment records 200 six times out of six from a residential IP and ECONNRESET
//         from GitHub runners. So "answered 200 here, now" is not proof the
//         entry is dead weight; it is proof of where the probe ran from. Wiring
// that to exit 1 would turn a link checker into a red/green oracle for the runner's egress IP, i.e. exactly the flaky hard failure that gets a gate suppressed. It prints, loudly, and a human decides.

type ProbeOutcome =
  | { kind: 'ok'; status: number }
  | { kind: 'blocked'; status: number }
  | { kind: 'gone'; detail: string }
  | { kind: 'unreachable'; detail: string };

/** Single-shot probe: no retries, tighter timeout, error class preserved. */
async function probeOnce(url: string): Promise<ProbeOutcome> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), LIVENESS_TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      method: 'GET',
      signal: controller.signal,
      redirect: 'follow',
      headers: buildHeaders(url),
    });
    await res.text().catch(() => {});
    return res.ok ? { kind: 'ok', status: res.status } : { kind: 'blocked', status: res.status };
  } catch (err) {
    const cause = (err as { cause?: { code?: string } })?.cause;
    const code = cause?.code ?? '';
    // A name that no longer resolves is categorically different from a name that resolves and refuses us. The allowlist claims "reachable from a browser"; NXDOMAIN says nothing is reachable from anywhere.
    if (code === 'ENOTFOUND' || code === 'EAI_AGAIN') {
      return { kind: 'gone', detail: code };
    }
    const message = err instanceof Error ? err.message : String(err);
    return {
      kind: 'unreachable',
      detail: code || (message.includes('abort') ? 'TIMEOUT' : message.slice(0, 60)),
    };
  } finally {
    // Without this the abort timer stays armed after a fast response and keeps the event loop alive for up to LIVENESS_TIMEOUT_MS per probe. Caught by
    // eslint no-unused-vars on the handle, which is the only symptom it has.
    clearTimeout(timeout);
  }
}

interface LivenessReport {
  /** FAIL tier: allowlisted domain no URL in the corpus references any more. */
  unreferencedDomains: string[];
  /** FAIL tier: KNOWN_BROKEN url that has left the docs. */
  unreferencedKnownBroken: string[];
  /** WARN tier: domain answered ok for every URL behind it. */
  noLongerBlocking: { domain: string; samples: string[] }[];
  /** WARN tier: domain stopped resolving. */
  vanished: { domain: string; detail: string }[];
  /** WARN tier: a KNOWN_BROKEN url now answers 200. */
  healed: string[];
  /** Number of network probes actually performed (all workloads). */
  probed: number;
  /**
   * Probes performed against ALLOWLISTED_DOMAINS specifically.
   *
   * Tracked apart from `probed` on purpose. The first version of the vacuity
   * guard keyed on the total, and a planted slice(0, 0) on the domain sample
   * did NOT trip it, because the KNOWN_BROKEN probes kept the total non-zero.
   * A guard that another workload can satisfy on your behalf is not a guard.
   */
  domainProbes: number;
  /** Allowlisted domains that ARE still referenced, i.e. the probe workload. */
  referencedDomains: number;
}

async function auditAllowlist(
  allUrls: Map<string, LinkLocation[]>,
  allowlisted: LinkEntry[]
): Promise<LivenessReport> {
  const report: LivenessReport = {
    unreferencedDomains: [],
    unreferencedKnownBroken: [],
    noLongerBlocking: [],
    vanished: [],
    healed: [],
    probed: 0,
    domainProbes: 0,
    referencedDomains: 0,
  };

  // --- FAIL tier: pure set arithmetic, no network involved. ---------------
  const byDomain = new Map<string, string[]>();
  for (const entry of allowlisted) {
    const host = hostnameOf(entry.url);
    if (!host) continue;
    if (!byDomain.has(host)) byDomain.set(host, []);
    byDomain.get(host)!.push(entry.url);
  }
  for (const domain of ALLOWLISTED_DOMAINS) {
    if (!byDomain.has(domain)) report.unreferencedDomains.push(domain);
  }
  report.referencedDomains = byDomain.size;
  for (const url of KNOWN_BROKEN.keys()) {
    if (!allUrls.has(url)) report.unreferencedKnownBroken.push(url);
  }

  // --- WARN tier: re-probe. ----------------------------------------------
  const jobs: (() => Promise<void>)[] = [];

  for (const [domain, urls] of byDomain) {
    jobs.push(async () => {
      // Probe every distinct URL behind the domain, capped so a domain with dozens of references does not dominate the run. The entry is only reported as dead weight when the WHOLE sample answers ok: one green deep link on a site that 403s the rest proves nothing.
      const sample = urls.slice(0, 3);
      const outcomes = await Promise.all(sample.map(probeOnce));
      report.probed += sample.length;
      report.domainProbes += sample.length;
      // `[].every(...)` is true for BOTH branches below, so an empty sample would report a domain as vanished AND crash on outcomes[0]. Found by planting slice(0, 0) here; the vacuity guard in main() is what makes an empty sample a failure rather than a silent all-clear.
      if (sample.length === 0) return;
      if (outcomes.every((o) => o.kind === 'gone')) {
        report.vanished.push({ domain, detail: (outcomes[0] as { detail: string }).detail });
      } else if (outcomes.every((o) => o.kind === 'ok')) {
        report.noLongerBlocking.push({ domain, samples: sample });
      }
    });
  }

  for (const [url] of KNOWN_BROKEN) {
    if (!allUrls.has(url)) continue;
    jobs.push(async () => {
      const outcome = await probeOnce(url);
      report.probed++;
      if (outcome.kind === 'ok') report.healed.push(url);
    });
  }

  let idx = 0;
  async function worker() {
    while (idx < jobs.length) {
      const job = jobs[idx++];
      if (!job) break;
      await job();
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));

  return report;
}

async function processQueue(entries: LinkEntry[]): Promise<{
  broken: LinkEntry[];
  unreachable: Array<{ who: string; url: string; err: NotCompared }>;
  notAsked: number;
  notAskedUrls: string[];
  skipped: LinkEntry[];
  excluded: number;
  knownBroken: number;
  checked: number;
}> {
  const broken: LinkEntry[] = [];
  const unreachable: Array<{ who: string; url: string; err: NotCompared }> = [];
  const notAskedUrls: string[] = [];
  const skipped: LinkEntry[] = [];
  let excluded = 0;
  let knownBroken = 0;
  let checked = 0;
  let notAsked = 0;
  let answered = 0;
  let unansweredRun = 0;
  let idx = 0;

  async function worker() {
    while (idx < entries.length) {
      const entry = entries[idx++];
      if (!entry) break;

      if (shouldSkip(entry.url)) {
        excluded++;
        continue;
      }

      if (KNOWN_BROKEN.has(entry.url)) {
        knownBroken++;
        continue;
      }

      if (isAllowlisted(entry.url)) {
        skipped.push(entry);
        continue;
      }

      if (answered === 0 && unansweredRun >= OUTAGE_BREAKER) {
        notAsked++;
        notAskedUrls.push(entry.url);
        continue;
      }

      const result = await checkUrl(entry.url);
      checked++;

      if (result.kind === 'unreachable') {
        unansweredRun++;
        unreachable.push({
          who: `${entry.url} (${where(entry)})`,
          url: entry.url,
          err: result.err,
        });
        continue;
      }
      answered++;
      if (result.kind === 'broken') {
        broken.push(entry);
        console.error(`  BROKEN [${result.status}]: ${entry.url}`);
        for (const loc of entry.locations) {
          console.error(`    -> ${loc.file}:${loc.line}`);
        }
      }
    }
  }

  const workers = Array.from({ length: CONCURRENCY }, () => worker());
  await Promise.all(workers);

  return { broken, unreachable, notAsked, notAskedUrls, skipped, excluded, knownBroken, checked };
}

/** The first place a link is cited, and how many more there are. */
function where(entry: LinkEntry): string {
  const first = entry.locations[0];
  const more = entry.locations.length - 1;
  return `${first ? `${first.file}:${first.line}` : 'no location'}${more > 0 ? ` and ${more} more` : ''}`;
}

/**
 * Collect markdown files per root.
 *
 * ANTI-VACUITY GUARD. Every entry in SCAN_ROOTS is a hardcoded path constant,
 * which is root pattern 1 in `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py`:
 * move or rename a tree and its glob returns zero files, every loop below
 * iterates zero times, and the gate prints "All external links are valid"
 * while checking less than it claims. Measured, not assumed: before this guard
 * the whole script exited 0 against an empty tree.
 *
 * The guard is PER ROOT, not on the total. A total-only guard would let four
 * of the five trees disappear while the fifth kept the run green — the exact
 * silent-shrink failure that widening the scan makes possible.
 */
function collectFiles(): { files: string[]; perRoot: Map<string, number> } | null {
  const files: string[] = [];
  const perRoot = new Map<string, number>();
  const empty: string[] = [];

  for (const root of SCAN_ROOTS) {
    const found = globSync(`${root}/**/*.md`, {
      ignore: ['**/node_modules/**', '**/dist/**'],
    });
    perRoot.set(root, found.length);
    if (found.length === 0) empty.push(root);
    files.push(...found);
  }

  if (empty.length > 0) {
    console.error(
      `\n  Refusing to run: no markdown files under ${empty.join(', ')}.\n` +
        `  A link checker with nothing to scan reports success while asserting\n` +
        `  nothing. Fix SCAN_ROOTS, or fix the checkout that left the tree empty.`
    );
    return null;
  }

  return { files, perRoot };
}

/** The finding key for the host of `url`. A host outside the key alphabet (an IPv6 literal, say) or an unparsable URL gets a fixed key rather than none, so it is still a finding. */
export function hostKey(url: string): string {
  const host = hostnameOf(url);
  if (host === null || host === '') return 'link:unparsable-url';
  const key = `link:${host.toLowerCase()}`;
  return /^[A-Za-z0-9._:/@#-]{1,200}$/.test(key) ? key : 'link:unkeyable-host';
}

export interface FailureInputs {
  brokenUrls: string[];
  unreachableUrls: string[];
  notAskedUrls: string[];
  unreferencedDomains: string[];
  unreferencedKnownBroken: string[];
  zeroProbes: boolean;
  checkedNothing: boolean;
}

/**
 * Every finding key of a failing run, deduped and sorted. Per HOST, never per URL (a URL carries characters outside the key alphabet). Each failure tier has a key, because a tier without one would fail the gate while a keyed carry of it still passed the push guard.
 */
export function failureKeys(f: FailureInputs): string[] {
  const keys = new Set<string>();
  for (const url of [...f.brokenUrls, ...f.unreachableUrls, ...f.notAskedUrls]) {
    keys.add(hostKey(url));
  }
  for (const d of f.unreferencedDomains)
    keys.add(hostKey(`https://${d}/`).replace('link:', 'allowlist-stale:'));
  for (const u of f.unreferencedKnownBroken)
    keys.add(hostKey(u).replace('link:', 'known-broken-stale:'));
  if (f.zeroProbes) keys.add('link:liveness-zero-probes');
  if (f.checkedNothing) keys.add('link:nothing-checked');
  return [...keys].sort();
}

function selftestFailureKeys(): number {
  const none: FailureInputs = {
    brokenUrls: [],
    unreachableUrls: [],
    notAskedUrls: [],
    unreferencedDomains: [],
    unreferencedKnownBroken: [],
    zeroProbes: false,
    checkedNothing: false,
  };
  const cases: [string, FailureInputs, string[]][] = [
    ['a passing run emits none', none, []],
    [
      'one failing link emits exactly its host key',
      { ...none, unreachableUrls: ['https://gdpr-info.eu/art-6-gdpr/'] },
      ['link:gdpr-info.eu'],
    ],
    [
      'urls of one host collapse, kinds merge, order is sorted',
      {
        ...none,
        brokenUrls: ['https://b.example.org/x?q=1', 'https://A.example.org/y'],
        unreachableUrls: ['https://b.example.org/z'],
        notAskedUrls: ['https://a.example.org/w'],
      },
      ['link:a.example.org', 'link:b.example.org'],
    ],
    [
      'an IPv6 literal and a bad url still key',
      { ...none, brokenUrls: ['http://[::1]/x', 'not a url'] },
      ['link:unkeyable-host', 'link:unparsable-url'],
    ],
    [
      'keyless tiers key too',
      {
        ...none,
        unreferencedDomains: ['a.io'],
        unreferencedKnownBroken: ['https://k.io/p'],
        zeroProbes: true,
        checkedNothing: true,
      },
      [
        'allowlist-stale:a.io',
        'known-broken-stale:k.io',
        'link:liveness-zero-probes',
        'link:nothing-checked',
      ],
    ],
  ];
  let bad = 0;
  for (const [name, input, want] of cases) {
    const got = failureKeys(input);
    if (JSON.stringify(got) !== JSON.stringify(want)) {
      bad++;
      console.error(
        `  selftest FAIL: ${name}: ${JSON.stringify(got)} (want ${JSON.stringify(want)})`
      );
    }
  }
  if (bad > 0) process.exit(1);
  console.log(`  selftest ok: ${cases.length} failureKeys cases`);
  return cases.length;
}

function selftestToApiUrl(): void {
  const repoApi = `${WK_GH_API_BASE}/repos/${WK_GH_REPO}`;
  const cases: [string, string | null][] = [
    // Control first: a shape the function already handled must still map.
    [`${WK_GH_ORIGIN}/${WK_GH_REPO}/issues/12`, `${WK_GH_API_BASE}/repos/${WK_GH_REPO}/issues/12`],
    [`${WK_GH_ORIGIN}/${WK_GH_REPO}`, repoApi],
    [`${WK_GH_ORIGIN}/${WK_GH_REPO}/`, repoApi],
    [`${WK_GH_ORIGIN}/${WK_GH_REPO}#readme`, repoApi],
    [`${WK_GH_ORIGIN}/${WK_GH_REPO}?tab=readme`, repoApi],
    [`${WK_GH_ORIGIN}/features`, null],
    [`${WK_GH_ORIGIN}/orgs/rediacc`, null],
    [`https://example.com/${WK_GH_REPO}`, null],
  ];
  let bad = 0;
  for (const [input, want] of cases) {
    const got = toApiUrl(input);
    if (got !== want) {
      bad++;
      console.error(`  selftest FAIL: ${input} -> ${got} (want ${want})`);
    }
  }
  if (bad > 0) process.exit(1);
  console.log(`  selftest ok: ${cases.length} toApiUrl cases`);
}

async function main() {
  if (process.argv.includes('--selftest')) {
    selftestToApiUrl();
    selftestFailureKeys();
    return;
  }
  console.log('External Link Checker');
  console.log('='.repeat(60));
  if (FIXTURE_ROOT) {
    process.chdir(FIXTURE_ROOT);
    console.log(
      `  FIXTURE RUN over ${FIXTURE_ROOT}: no allowlist, no KNOWN_BROKEN, loopback checked`
    );
  }

  const collected = collectFiles();
  if (!collected) process.exit(1);
  const { files, perRoot } = collected;

  for (const [root, n] of perRoot) {
    console.log(`  ${root}: ${n} file(s)`);
  }
  console.log(`\nScanning ${files.length} markdown files...\n`);

  // Extract and deduplicate links
  const allLinks = new Map<string, LinkLocation[]>();
  let placeholders = 0;
  for (const file of files) {
    const { links: fileLinks, placeholders: p } = extractLinks(file);
    placeholders += p;
    for (const [url, locations] of fileLinks) {
      if (!allLinks.has(url)) {
        allLinks.set(url, []);
      }
      allLinks.get(url)!.push(...locations);
    }
  }

  // Filter to external links only
  const entries: LinkEntry[] = [];
  for (const [url, locations] of allLinks) {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      entries.push({ url, locations });
    }
  }

  console.log(
    `Found ${entries.length} unique external URLs (${placeholders} placeholder occurrence(s) dropped)\n`
  );
  console.log('Checking links...\n');

  const { broken, unreachable, notAsked, notAskedUrls, skipped, excluded, knownBroken, checked } =
    await processQueue(entries);

  console.log('Auditing allowlist liveness...\n');
  const liveness = await auditAllowlist(allLinks, skipped);

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`  Total unique URLs: ${entries.length}`);
  console.log(`  Checked:           ${checked}`);
  console.log(`  Excluded (patterns):${excluded}`);
  console.log(`  Skipped (allowlist):${skipped.length}`);
  console.log(`  Known-broken (tracked):${knownBroken}`);
  console.log(`  Broken:            ${broken.length}`);
  console.log(`  Not answered:      ${unreachable.length}`);
  console.log(`  Not asked (outage):${notAsked}`);
  console.log(`  Liveness probes:   ${liveness.probed}`);

  if (skipped.length > 0) {
    console.log(`\n  Allowlisted domains (verified manually):`);
    const domains = new Set(skipped.map((e) => new URL(e.url).hostname));
    for (const domain of [...domains].sort()) {
      console.log(`    - ${domain}`);
    }
  }

  // --- Liveness verdicts --------------------------------------------------
  if (liveness.noLongerBlocking.length > 0) {
    console.log(`\n  WARNING: allowlist entries that answered normally from this runner:`);
    for (const { domain, samples } of liveness.noLongerBlocking) {
      console.log(`    - ${domain}  (${samples.length} sampled URL(s) all returned 2xx)`);
    }
    console.log(
      `    These may be dead weight. They are NOT failed here: every entry in\n` +
        `    the allowlist documents an IP-dependent block, so a green probe from\n` +
        `    one location is not proof the block is gone. Re-check from a CI\n` +
        `    runner before deleting the entry.`
    );
  }

  if (liveness.vanished.length > 0) {
    console.log(`\n  WARNING: allowlisted domains that no longer resolve:`);
    for (const { domain, detail } of liveness.vanished) {
      console.log(`    - ${domain}  (${detail})`);
    }
    console.log(
      `    The allowlist claims these are reachable from a browser. A name that\n` +
        `    does not resolve is not reachable from anywhere, so the links behind\n` +
        `    them are probably dead and the allowlist is hiding it.`
    );
  }

  if (liveness.healed.length > 0) {
    console.log(`\n  WARNING: KNOWN_BROKEN links that now answer 2xx:`);
    for (const url of liveness.healed) console.log(`    - ${url}`);
    console.log(`    Fixed upstream. Delete the TREE_KNOWN_BROKEN entry.`);
  }

  if (knownBroken > 0) {
    console.log(`\n  Tracked broken links (documented, not fixable from this file):`);
    for (const entry of entries) {
      const reason = KNOWN_BROKEN.get(entry.url);
      if (!reason) continue;
      console.log(`    - ${entry.url}`);
      console.log(`      ${reason}`);
    }
  }

  // --- FAIL tier ----------------------------------------------------------
  const failures: string[] = [];

  if (liveness.unreferencedDomains.length > 0) {
    failures.push(
      `  Allowlisted domain(s) no longer referenced by any scanned markdown:\n` +
        liveness.unreferencedDomains.map((d) => `    - ${d}`).join('\n') +
        `\n  The exemption outlived the link it excused. Delete it from TREE_ALLOWLISTED_DOMAINS.`
    );
  }

  if (liveness.unreferencedKnownBroken.length > 0) {
    failures.push(
      `  KNOWN_BROKEN url(s) that no longer appear in any scanned markdown:\n` +
        liveness.unreferencedKnownBroken.map((u) => `    - ${u}`).join('\n') +
        `\n  The doc was fixed. Delete the entry from TREE_KNOWN_BROKEN.`
    );
  }

  // A liveness audit that probed nothing while it had work to do is vacuous: it prints no warnings, which reads as "every entry is still load-bearing".
  //
  // Deliberately keyed on referencedDomains, not on ALLOWLISTED_DOMAINS.size. The latter would be unreachable dead code: if no allowlisted domain is referenced, the unreferencedDomains failure above has already fired. Keyed on the actual probe workload it stays live, and it fires on the regression that matters -- someone making the probe conditional, capped to zero, or wrapped in
  // a try/catch that swallows it.
  if (liveness.referencedDomains > 0 && liveness.domainProbes === 0) {
    failures.push(
      `  Liveness audit ran ZERO probes while ${liveness.referencedDomains} allowlisted domain(s)\n` +
        `  were still referenced by the docs. Silence from an instrument that never\n` +
        `  fired is not a clean bill of health.`
    );
  }

  if (broken.length > 0) {
    failures.push(`  ${broken.length} broken external link(s) found.`);
  }

  // FAIL CLOSED (operator ruling 2026-10-14). A link whose host never answered was not checked, and a link that was not checked is a finding, on the nightly as on a pull request. Printed through the shared reporter so the log carries the sentence ci_diagnose.py reads as an upstream outage rather than as a broken link.
  reportUnreachable('external link(s)', unreachable, {
    notA: 'a broken link',
    hint: [
      '  and re-run the failed job when this is a nightly. A link that never answers from',
      '  any network is dead after all: fix or remove it, since an allowlist entry is only',
      '  for a host that blocks automated clients and still serves a browser.',
    ],
  });
  if (unreachable.length > 0) {
    failures.push(
      `  ${unreachable.length} external link(s) were NOT checked: their host did not answer.`
    );
  }
  if (notAsked > 0) {
    failures.push(
      `  ${notAsked} external link(s) were NOT asked: the first ${OUTAGE_BREAKER} links checked\n` +
        `  all went unanswered and no host answered at all, which is an outage on this\n` +
        `  side of the network rather than ${OUTAGE_BREAKER} dead links. Re-run once the network answers.`
    );
  }
  if (checked === 0) {
    failures.push(
      `  Not one link was checked: every URL was excluded, allowlisted or tracked, so a\n` +
        `  green here would rest on nothing.`
    );
  }

  if (failures.length > 0) {
    // One `::finding::` line per failing host (and per keyless failure), so a carried red of this gate names what it carries instead of hiding every future finding (.ci/config/carried-reds.json).
    const keys = failureKeys({
      brokenUrls: broken.map((e) => e.url),
      unreachableUrls: unreachable.map((u) => u.url),
      notAskedUrls,
      unreferencedDomains: liveness.unreferencedDomains,
      unreferencedKnownBroken: liveness.unreferencedKnownBroken,
      zeroProbes: liveness.referencedDomains > 0 && liveness.domainProbes === 0,
      checkedNothing: checked === 0,
    });
    console.error(`\n  FAILED:`);
    for (const f of failures) console.error(f);
    for (const key of keys) emitFinding(key);
    process.exit(1);
  }

  console.log(
    `\n  All external links are valid (${checked} checked, ${skipped.length} allowlisted, ${excluded} excluded).`
  );
}

main();
