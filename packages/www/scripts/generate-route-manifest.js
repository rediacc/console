/**
 * Route Manifest Generator
 *
 * Scans the Astro build output (dist/) for all HTML files, extracts URL paths
 * and page titles, and generates a compact route-manifest.json used by the
 * Cloudflare Worker for smart 404 redirects.
 *
 * Output: dist/route-manifest.json (~15KB, ~90 entries)
 *
 * Run: node scripts/generate-route-manifest.js
 */

import fs from 'node:fs';
import path from 'node:path';

const DIST_DIR = path.resolve('dist');
const OUTPUT_PATH = path.join(DIST_DIR, 'route-manifest.json');

const BRAND_SUFFIXES = [' | Rediacc', ' — Rediacc', ' - Rediacc'];
const TITLE_RE = /<title>([^<]+)<\/title>/i;

// Paths to exclude from the manifest (redirects, transactional, or homepage)
const EXCLUDED_SLUGS = new Set(['404', 'checkout/success']);
const EXCLUDED_PATHS = new Set(['', '/']);

/**
 * Recursively find all HTML files in a directory.
 */
function findHtmlFiles(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      findHtmlFiles(full, files);
    } else if (entry.isFile() && entry.name.endsWith('.html')) {
      files.push(full);
    }
  }
  return files;
}

/**
 * Convert a dist file path to a URL path.
 * dist/en/docs/installation/index.html -> /en/docs/installation
 * dist/en/pricing.html -> /en/pricing
 * dist/404.html -> /404
 */
function fileToUrlPath(filePath) {
  let rel = path.relative(DIST_DIR, filePath).replaceAll('\\', '/');
  rel = rel.replace(/\/index\.html$/, '').replace(/\.html$/, '');
  return '/' + rel;
}

/**
 * Extract <title> from an HTML file and strip brand suffix.
 */
function extractTitle(filePath) {
  // Astro inlines everything on line 1; title can be 3-5KB in. Read up to 8KB.
  const fd = fs.openSync(filePath, 'r');
  const buf = Buffer.alloc(8192);
  const bytesRead = fs.readSync(fd, buf, 0, 8192, 0);
  fs.closeSync(fd);

  const head = buf.toString('utf8', 0, bytesRead);
  const match = TITLE_RE.exec(head);
  if (!match) return '';

  // Decode HTML entities (&amp; -> &, &#38; -> &, etc.)
  let title = match[1]
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .trim();

  for (const suffix of BRAND_SUFFIXES) {
    if (title.endsWith(suffix)) {
      title = title.slice(0, -suffix.length).trim();
      break;
    }
  }
  return title;
}

/**
 * Parse a URL path into structured fields.
 * /en/docs/installation -> { lang: 'en', section: 'docs', slug: 'installation' }
 * /en/pricing -> { lang: 'en', section: '', slug: 'pricing' }
 */
function parsePath(urlPath) {
  const segments = urlPath.split('/').filter(Boolean);
  const lang = segments[0] || '';
  const rest = segments.slice(1);

  // Determine section (docs, blog, solutions, or empty)
  const knownSections = ['docs', 'blog', 'solutions'];
  let section = '';
  let slugParts = rest;

  if (rest.length > 0 && knownSections.includes(rest[0])) {
    section = rest[0];
    slugParts = rest.slice(1);
  }

  const slug = slugParts.join('/');
  const pathWithoutLang = '/' + rest.join('/');

  return { lang, section, slug, pathWithoutLang };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

if (!fs.existsSync(DIST_DIR)) {
  process.stderr.write('Error: dist/ directory not found. Run astro build first.\n');
  process.exit(1);
}

const htmlFiles = findHtmlFiles(DIST_DIR);
const seen = new Set();
const entries = [];

for (const file of htmlFiles) {
  const urlPath = fileToUrlPath(file);
  const { lang, section, slug, pathWithoutLang } = parsePath(urlPath);

  // Only keep English routes (all languages share the same slug structure)
  if (lang !== 'en') continue;

  // Skip excluded paths
  if (EXCLUDED_PATHS.has(pathWithoutLang) || EXCLUDED_SLUGS.has(slug)) continue;

  // Skip section index pages (they're just redirects, e.g., /en/docs -> /en/docs/quick-start)
  if (section && !slug) continue;

  // Deduplicate
  if (seen.has(pathWithoutLang)) continue;
  seen.add(pathWithoutLang);

  const title = extractTitle(file);
  const keywords = slug.split(/[-/]/).filter((k) => k.length > 2);

  entries.push({
    path: pathWithoutLang,
    title,
    section,
    slug,
    keywords,
  });
}

// Sort for deterministic output
entries.sort((a, b) => a.path.localeCompare(b.path));

fs.writeFileSync(OUTPUT_PATH, JSON.stringify(entries, null, 2) + '\n');

process.stdout.write(
  `Route manifest: ${entries.length} entries (${(Buffer.byteLength(JSON.stringify(entries)) / 1024).toFixed(1)}KB) -> ${OUTPUT_PATH}\n`
);
