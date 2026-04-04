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
  // Redirect-only domains that may not respond to HEAD/GET from CI runners
  /^https?:\/\/get\.rediacc\.com/,
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

async function checkUrl(url: string, retries = 0): Promise<{ ok: boolean; status: number | string }> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

    const response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
      redirect: 'follow',
      headers: {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,*/*',
      },
    });

    clearTimeout(timeout);

    // Some servers don't support HEAD, retry with GET
    if (response.status === 405 || response.status === 404) {
      const controller2 = new AbortController();
      const timeout2 = setTimeout(() => controller2.abort(), TIMEOUT_MS);

      const getResponse = await fetch(url, {
        method: 'GET',
        signal: controller2.signal,
        redirect: 'follow',
        headers: {
          'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,*/*',
        },
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
