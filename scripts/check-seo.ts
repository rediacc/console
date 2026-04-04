/**
 * SEO validation script for the www package.
 *
 * Checks Astro source files for common SEO regressions that cannot be caught
 * by ESLint JSON rules (those handle translation content; this handles templates).
 *
 * Run: npx tsx scripts/check-seo.ts
 */

import fs from 'node:fs';
import path from 'node:path';
import { globSync } from 'glob';

const WWW_SRC = 'packages/www/src';
const WWW_ROOT = 'packages/www';
const PAGES_DIR = path.join(WWW_SRC, 'pages');

let errors = 0;
let warnings = 0;

function error(file: string, message: string) {
  console.error(`  ERROR: ${file}: ${message}`);
  errors++;
}

function warn(file: string, message: string) {
  console.warn(`  WARN:  ${file}: ${message}`);
  warnings++;
}

// ──────────────────────────────────────────────────────────────────────────────
// 1. Astro.redirect() must specify 301 status
// ──────────────────────────────────────────────────────────────────────────────
function checkRedirects() {
  console.log('Checking Astro.redirect() calls for 301 status...');
  const files = globSync(`${WWW_SRC}/**/*.astro`);

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8');
    const lines = content.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.includes('Astro.redirect(')) {
        // Check if it specifies 301
        if (!line.includes('301')) {
          error(file, `line ${i + 1}: Astro.redirect() without explicit 301 status. Use Astro.redirect(url, 301)`);
        }
      }
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 2. No <meta http-equiv="refresh"> tags
// ──────────────────────────────────────────────────────────────────────────────
function checkMetaRefresh() {
  console.log('Checking for meta refresh tags...');
  const files = [
    ...globSync(`${WWW_SRC}/**/*.astro`),
    ...globSync(`${WWW_SRC}/**/*.tsx`),
    ...globSync(`${WWW_SRC}/**/*.jsx`),
  ];

  for (const file of files) {
    const content = fs.readFileSync(file, 'utf-8');
    if (/meta\s+http-equiv\s*=\s*["']refresh["']/i.test(content)) {
      error(file, 'Contains <meta http-equiv="refresh">. Use server-side 301 redirects instead.');
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 3. trailingSlash must be configured in astro.config.mjs
// ──────────────────────────────────────────────────────────────────────────────
function checkTrailingSlash() {
  console.log('Checking trailingSlash config...');
  const configPath = path.join(WWW_ROOT, 'astro.config.mjs');
  const content = fs.readFileSync(configPath, 'utf-8');

  if (!content.includes('trailingSlash')) {
    error(configPath, 'Missing trailingSlash config. Add trailingSlash: "never" or "always" to prevent Cloudflare 307 redirects.');
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 4. Hreflang codes in BaseLayout must match sitemap i18n codes
// ──────────────────────────────────────────────────────────────────────────────
function checkHreflangConsistency() {
  console.log('Checking hreflang consistency with sitemap...');

  const configPath = path.join(WWW_ROOT, 'astro.config.mjs');
  const configContent = fs.readFileSync(configPath, 'utf-8');

  // Extract locale codes from sitemap i18n config
  const localeMatch = configContent.match(/locales:\s*\{([^}]+)\}/s);
  if (!localeMatch) {
    warn(configPath, 'Could not parse sitemap i18n locales config.');
    return;
  }

  // Parse locale mappings (e.g., "de: 'de-DE'")
  const sitemapLocales = new Map<string, string>();
  const localeRegex = /(\w+):\s*['"]([^'"]+)['"]/g;
  let match;
  while ((match = localeRegex.exec(localeMatch[1])) !== null) {
    sitemapLocales.set(match[1], match[2]);
  }

  // Check BaseLayout hreflang implementation
  const layoutPath = path.join(WWW_SRC, 'layouts', 'BaseLayout.astro');
  const layoutContent = fs.readFileSync(layoutPath, 'utf-8');

  // Check that hreflang uses the mapped locale codes, not bare language codes
  // The hreflang should use getHreflang(lang) or equivalent, not just {lang}
  if (layoutContent.includes('hreflang={lang}') && sitemapLocales.size > 0) {
    // Check if any sitemap locale differs from its key (e.g., de -> de-DE)
    for (const [key, locale] of sitemapLocales) {
      if (key !== locale) {
        error(
          layoutPath,
          `Hreflang uses bare language code "{lang}" but sitemap maps "${key}" to "${locale}". ` +
          'HTML hreflang and sitemap hreflang must match. Use full BCP 47 codes.'
        );
        break; // One error is enough
      }
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// 5. Page files should include an H1 (directly or via known hero components)
// ──────────────────────────────────────────────────────────────────────────────
function checkH1Presence() {
  console.log('Checking H1 presence in pages...');

  // Components known to render an H1 (directly or via SPHero)
  const h1Components = ['SPHero', 'SPHomePage', 'SolutionPage', 'PersonaPage', 'ContentLayout', 'DocsLayout'];

  const pageFiles = globSync(`${PAGES_DIR}/\\[lang\\]/**/*.astro`);

  for (const file of pageFiles) {
    const content = fs.readFileSync(file, 'utf-8');

    // Skip redirect-only pages (only contain Astro.redirect)
    if (content.includes('Astro.redirect(') && !content.includes('<BaseLayout')) continue;

    // Check for direct <h1> or known hero component imports
    const hasDirectH1 = /<h1[\s>]/i.test(content);
    const hasHeroComponent = h1Components.some((comp) => content.includes(comp));

    if (!hasDirectH1 && !hasHeroComponent) {
      error(file, 'Page has no <h1> tag and does not use a known hero component that renders one.');
    }
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Run all checks
// ──────────────────────────────────────────────────────────────────────────────
console.log('Running SEO validation checks...\n');

checkRedirects();
checkMetaRefresh();
checkTrailingSlash();
checkHreflangConsistency();
checkH1Presence();

console.log(`\nSEO check complete: ${errors} error(s), ${warnings} warning(s)`);

if (errors > 0) {
  process.exit(1);
}
