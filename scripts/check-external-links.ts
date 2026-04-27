/**
 * External link validator for documentation.
 *
 * Extracts all external URLs from markdown files in packages/www/src/content/docs/
 * and verifies each one returns a successful HTTP status.
 *
 * Run: npx tsx scripts/check-external-links.ts
 *
 * Features:
 * - Extracts URLs from markdown links [text](url) and bare https:// references
 * - Deduplicates URLs across all files
 * - Concurrent validation with rate limiting
 * - Allowlist for known-flaky URLs (e.g., sites that block bots)
 * - Reports broken links with file location
 * - Exit code 1 on any broken link (CI-friendly)
 */

import fs from 'node:fs';
import path from 'node:path';
import { globSync } from 'glob';

const DOCS_DIR = 'packages/www/src/content/docs';
const CONCURRENCY = 5;
const TIMEOUT_MS = 15_000;
const MAX_RETRIES = 2;

// Sites that aggressively block all automated requests (403 even with browser UA + curl).
// Verified manually with a real browser. Keep this list minimal.
const ALLOWLISTED_DOMAINS = new Set([
  'www.hhs.gov',       // US HHS - blocks all automated requests
  'www.sec.gov',       // US SEC - blocks all automated requests
  'pd.rkn.gov.ru',     // Russia Roskomnadzor - unreachable from most locations
  'sdaia.gov.sa',      // Saudi SDAIA - connection refused from non-Saudi IPs
  'www.pipc.go.kr',    // South Korea PIPC - extremely slow, times out in CI
  'www.legislation.gov.au', // Australia legislation - intermittent timeouts from CI runners
  'www.iso.org',       // ISO standards - returns 403 to non-browser User-Agent (anti-scraping)
  // Own infrastructure -- only available after releases, not during CI
  'releases.rediacc.com',
]);

// URL patterns that are not real links (examples, templates, localhost).
// These appear in documentation code blocks and should never be fetched.
const SKIP_PATTERNS = [
  /^https?:\/\/example\.com/,
  /^https?:\/\/[^/]*\.example\.com/,
  /^https?:\/\/127\.\d+\.\d+\.\d+/,
  /^https?:\/\/localhost/,
  /\{[^}]+\}/,           // URL templates like {service}.{repo}
  /\$\{[^}]+\}/,         // Shell variables like ${SERVICE_IP}
  /^https?:\/\/[^/]*`/,  // URLs with trailing backtick (inline code artifacts)
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
];

interface LinkLocation {
  file: string;
  line: number;
}

interface LinkEntry {
  url: string;
  locations: LinkLocation[];
}

function extractLinks(filePath: string): Map<string, LinkLocation[]> {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const links = new Map<string, LinkLocation[]>();
  const relPath = path.relative(process.cwd(), filePath);

  // Match markdown links [text](https://...) and bare URLs https://...
  const urlRegex = /https?:\/\/[^\s)\]>"',]+/g;

  for (let i = 0; i < lines.length; i++) {
    const matches = lines[i].matchAll(urlRegex);
    for (const match of matches) {
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

  return links;
}

function shouldSkip(url: string): boolean {
  // Check skip patterns first (examples, templates, localhost)
  for (const pattern of SKIP_PATTERNS) {
    if (pattern.test(url)) return true;
  }
  return false;
}

function isAllowlisted(url: string): boolean {
  try {
    const hostname = new URL(url).hostname;
    return ALLOWLISTED_DOMAINS.has(hostname);
  } catch {
    return false;
  }
}

/**
 * Build request headers. For api.github.com URLs attach GITHUB_TOKEN so
 * anonymous rate-limiting doesn't flap the check.
 */
function buildHeaders(url: string): Record<string, string> {
  const headers: Record<string, string> = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*',
  };
  const token = process.env.GITHUB_TOKEN;
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
function toApiUrl(url: string): string | null {
  const m = url.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/(issues|pull|tree|blob)\/(.+?)(?:[?#].*)?$/);
  if (!m) return null;
  const [, owner, repo, kind, rest] = m;
  if (kind === 'issues' || kind === 'pull') {
    const num = rest.split('/')[0];
    if (!/^\d+$/.test(num)) return null;
    // The issues endpoint returns both issues and PRs (PRs are issues with
    // a pull_request field), so a single lookup works for either form.
    return `https://api.github.com/repos/${owner}/${repo}/issues/${num}`;
  }
  // tree and blob: check that the ref + path exists via the contents endpoint.
  // rest is <ref>/<path...>; collapse into contents/<path>?ref=<ref>.
  const slash = rest.indexOf('/');
  if (slash === -1) {
    // /tree/<branch> with no path — verify the branch exists.
    return `https://api.github.com/repos/${owner}/${repo}/branches/${rest}`;
  }
  const ref = rest.slice(0, slash);
  const path = rest.slice(slash + 1);
  return `https://api.github.com/repos/${owner}/${repo}/contents/${path}?ref=${encodeURIComponent(ref)}`;
}

async function checkUrl(url: string, retries = 0): Promise<{ ok: boolean; status: number | string }> {
  // Rewrite github.com HTML URLs to api.github.com so GITHUB_TOKEN actually
  // authorises the request. Only used when GITHUB_TOKEN is available.
  if (process.env.GITHUB_TOKEN) {
    const api = toApiUrl(url);
    if (api) url = api;
  }
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

    const response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
      redirect: 'follow',
      headers: buildHeaders(url),
    });

    clearTimeout(timeout);

    // Some servers don't support HEAD, retry with GET. 401/403/429 are also
    // common from GitHub/Cloudflare anti-bot on HEAD — the same URL answers
    // 200 to a plain GET with a browser UA and/or auth token.
    if (
      response.status === 405 ||
      response.status === 404 ||
      response.status === 401 ||
      response.status === 403 ||
      response.status === 429
    ) {
      const controller2 = new AbortController();
      const timeout2 = setTimeout(() => controller2.abort(), TIMEOUT_MS);

      const getResponse = await fetch(url, {
        method: 'GET',
        signal: controller2.signal,
        redirect: 'follow',
        headers: buildHeaders(url),
      });

      clearTimeout(timeout2);
      // Consume body to prevent memory leak
      await getResponse.text().catch(() => {});
      return { ok: getResponse.ok, status: getResponse.status };
    }

    return { ok: response.ok, status: response.status };
  } catch (err) {
    if (retries < MAX_RETRIES) {
      await new Promise((r) => setTimeout(r, 1000 * (retries + 1)));
      return checkUrl(url, retries + 1);
    }
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes('abort')) {
      return { ok: false, status: 'TIMEOUT' };
    }
    return { ok: false, status: message.slice(0, 60) };
  }
}

async function processQueue(entries: LinkEntry[]): Promise<{ broken: LinkEntry[]; skipped: LinkEntry[]; excluded: number; checked: number }> {
  const broken: LinkEntry[] = [];
  const skipped: LinkEntry[] = [];
  let excluded = 0;
  let checked = 0;
  let idx = 0;

  async function worker() {
    while (idx < entries.length) {
      const entry = entries[idx++];
      if (!entry) break;

      if (shouldSkip(entry.url)) {
        excluded++;
        continue;
      }

      if (isAllowlisted(entry.url)) {
        skipped.push(entry);
        continue;
      }

      const result = await checkUrl(entry.url);
      checked++;

      if (!result.ok) {
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

  return { broken, skipped, excluded, checked };
}

async function main() {
  console.log('External Link Checker');
  console.log('='.repeat(60));

  // Find all markdown files
  const files = globSync(`${DOCS_DIR}/**/*.md`);
  console.log(`Scanning ${files.length} markdown files...\n`);

  // Extract and deduplicate links
  const allLinks = new Map<string, LinkLocation[]>();
  for (const file of files) {
    const fileLinks = extractLinks(file);
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

  console.log(`Found ${entries.length} unique external URLs\n`);
  console.log('Checking links...\n');

  const { broken, skipped, excluded, checked } = await processQueue(entries);

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`  Total unique URLs: ${entries.length}`);
  console.log(`  Checked:           ${checked}`);
  console.log(`  Excluded (patterns):${excluded}`);
  console.log(`  Skipped (allowlist):${skipped.length}`);
  console.log(`  Broken:            ${broken.length}`);

  if (skipped.length > 0) {
    console.log(`\n  Allowlisted domains (verified manually):`);
    const domains = new Set(skipped.map((e) => new URL(e.url).hostname));
    for (const domain of [...domains].sort()) {
      console.log(`    - ${domain}`);
    }
  }

  if (broken.length > 0) {
    console.error(`\n  FAILED: ${broken.length} broken external link(s) found.`);
    process.exit(1);
  }

  console.log('\n  All external links are valid.');
}

main();
