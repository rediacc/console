#!/usr/bin/env node
/**
 * Comparison Table Reference Validation Script
 *
 * Validates that comparison table cells in solution pages have proper
 * references linking to the Sources & References section.
 *
 * Rules (always enforced — offline):
 * - missing-comparison-ref: Every feature must have a refs array matching values length
 * - invalid-ref-index: Every ref must be 0 or a valid 1-based index into references.items
 * - missing-ref-url: Every referenced item must have a non-empty url field
 *
 * Rules (--online only — slower, for nightly/manual runs):
 * - ref-url-unreachable: Reference URLs must return 2xx/3xx status
 *
 * Usage:
 *   node scripts/validate-comparison-refs.js           # offline checks (CI default)
 *   node scripts/validate-comparison-refs.js --online   # also check URLs are reachable
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '..');
const TRANSLATIONS_DIR = path.join(ROOT_DIR, 'src', 'i18n', 'translations');

// Domains with aggressive bot protection that block automated requests.
// These are verified manually via agent-browser and skipped in --online checks.
const BOT_PROTECTED_DOMAINS = new Set(['www.rubrik.com']);

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

function addError(errors, rule, file, line, message, matchedText, suggestion) {
  errors.push({ rule, file, line, message, matchedText, suggestion });
}

// ---------------------------------------------------------------------------
// Offline validation rules
// ---------------------------------------------------------------------------

function validateOffline(translations, errors) {
  const solutionPages = translations?.pages?.solutionPages;
  if (!solutionPages) {
    addError(errors, 'missing-comparison-ref', 'en.json', 0, 'No solutionPages found in translations', '', null);
    return;
  }

  for (const [pageKey, pageData] of Object.entries(solutionPages)) {
    const comparison = pageData?.comparison;
    if (!comparison || !comparison.features) continue;

    const references = pageData?.references;
    const refItems = references?.items || [];
    const file = `solutionPages.${pageKey}`;

    for (let fi = 0; fi < comparison.features.length; fi++) {
      const feature = comparison.features[fi];
      const featurePath = `${file}.comparison.features[${fi}]`;

      // Rule 1: missing-comparison-ref
      if (!feature.refs) {
        addError(
          errors,
          'missing-comparison-ref',
          featurePath,
          0,
          `Feature "${feature.name}" has no refs array`,
          `values: [${feature.values.join(', ')}]`,
          'Add a refs array with one entry per value (0 = no ref needed)'
        );
        continue;
      }

      if (feature.refs.length !== feature.values.length) {
        addError(
          errors,
          'missing-comparison-ref',
          featurePath,
          0,
          `Feature "${feature.name}" refs length (${feature.refs.length}) !== values length (${feature.values.length})`,
          `refs: [${feature.refs.join(', ')}], values: [${feature.values.join(', ')}]`,
          'refs array must have the same number of entries as values'
        );
        continue;
      }

      // Rule 2: invalid-ref-index
      for (let ri = 0; ri < feature.refs.length; ri++) {
        const ref = feature.refs[ri];
        if (typeof ref !== 'number' || ref < 0) {
          addError(
            errors,
            'invalid-ref-index',
            featurePath,
            0,
            `Feature "${feature.name}" refs[${ri}] = ${ref} is not a valid number`,
            `refs: [${feature.refs.join(', ')}]`,
            'Each ref must be 0 (no ref) or a positive integer index into references.items'
          );
        } else if (ref > 0 && ref > refItems.length) {
          addError(
            errors,
            'invalid-ref-index',
            featurePath,
            0,
            `Feature "${feature.name}" refs[${ri}] = ${ref} exceeds references.items length (${refItems.length})`,
            `refs: [${feature.refs.join(', ')}]`,
            `Valid range: 0 or 1–${refItems.length}`
          );
        }
      }

      // Rule 3: missing-ref-url — check that referenced items have urls
      for (let ri = 0; ri < feature.refs.length; ri++) {
        const ref = feature.refs[ri];
        if (ref > 0 && ref <= refItems.length) {
          const item = refItems[ref - 1]; // 1-based to 0-based
          if (!item?.url || item.url.trim() === '') {
            addError(
              errors,
              'missing-ref-url',
              featurePath,
              0,
              `Feature "${feature.name}" refs[${ri}] = ${ref} → references.items[${ref - 1}] has no url`,
              item?.text || '(empty)',
              'Add a publicly accessible URL to this reference item'
            );
          }
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Online validation rules
// ---------------------------------------------------------------------------

async function validateOnline(translations, errors) {
  const solutionPages = translations?.pages?.solutionPages;
  if (!solutionPages) return;

  // Collect all unique URLs from reference items across all pages
  const urlMap = new Map(); // url → { pages[], text }
  for (const [pageKey, pageData] of Object.entries(solutionPages)) {
    const refItems = pageData?.references?.items || [];
    for (let i = 0; i < refItems.length; i++) {
      const item = refItems[i];
      if (!item?.url) continue;
      const url = item.url.trim();
      if (!url) continue;
      if (!urlMap.has(url)) {
        urlMap.set(url, { pages: [], text: item.text, index: i + 1 });
      }
      urlMap.get(url).pages.push(`${pageKey}[${i + 1}]`);
    }
  }

  // Only check URLs referenced by comparison tables
  const referencedUrls = new Set();
  for (const [, pageData] of Object.entries(solutionPages)) {
    const comparison = pageData?.comparison;
    if (!comparison?.features) continue;
    const refItems = pageData?.references?.items || [];
    for (const feature of comparison.features) {
      if (!feature.refs) continue;
      for (const ref of feature.refs) {
        if (ref > 0 && ref <= refItems.length) {
          const url = refItems[ref - 1]?.url?.trim();
          if (url) referencedUrls.add(url);
        }
      }
    }
  }

  if (referencedUrls.size === 0) {
    console.log(colors.dim('  No comparison reference URLs to check.'));
    return;
  }

  console.log(colors.dim(`  Checking ${referencedUrls.size} unique reference URLs...`));

  const BROWSER_UA =
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

  async function checkUrl(url) {
    // Skip domains known to use bot protection; verified manually via browser
    try {
      const hostname = new URL(url).hostname;
      if (BOT_PROTECTED_DOMAINS.has(hostname)) {
        return { url, status: 200, ok: true, skipped: true };
      }
    } catch { /* invalid URL will fail below */ }

    const makeRequest = async (method) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 15000);
      try {
        const resp = await fetch(url, {
          method,
          signal: controller.signal,
          redirect: 'follow',
          headers: {
            'User-Agent': BROWSER_UA,
            Accept: 'text/html,application/xhtml+xml,*/*',
          },
        });
        clearTimeout(timer);
        return resp;
      } catch (err) {
        clearTimeout(timer);
        throw err;
      }
    };

    try {
      let resp = await makeRequest('HEAD');
      // Retry with GET if HEAD is blocked (405, 403)
      if (resp.status === 405 || resp.status === 403) {
        resp = await makeRequest('GET');
      }
      return { url, status: resp.status, ok: resp.ok };
    } catch (err) {
      return { url, status: 0, ok: false, error: err.message };
    }
  }

  const results = [];
  const concurrency = 5;
  const urlArray = [...referencedUrls];

  for (let i = 0; i < urlArray.length; i += concurrency) {
    const batch = urlArray.slice(i, i + concurrency);
    results.push(...(await Promise.all(batch.map(checkUrl))));
  }

  const skipped = results.filter((r) => r.skipped);
  if (skipped.length > 0) {
    console.log(colors.dim(`  Skipped ${skipped.length} bot-protected URLs (verified manually)`));
  }

  for (const result of results) {
    if (!result.ok) {
      const info = urlMap.get(result.url);
      const pages = info?.pages?.join(', ') || 'unknown';
      const statusMsg = result.error
        ? `Network error: ${result.error}`
        : `HTTP ${result.status}`;
      addError(
        errors,
        'ref-url-unreachable',
        pages,
        0,
        statusMsg,
        result.url,
        'Ensure URL is publicly accessible or update reference'
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Output helpers (same pattern as validate-content-accuracy.js)
// ---------------------------------------------------------------------------

function groupByRule(errors) {
  const grouped = new Map();
  for (const error of errors) {
    if (!grouped.has(error.rule)) grouped.set(error.rule, []);
    grouped.get(error.rule).push(error);
  }
  return grouped;
}

function printSummary(errors, warnings) {
  console.log(colors.bold('Comparison Table Reference Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0 && warnings.length === 0) {
    console.log(colors.green('✓ All comparison reference checks passed.'));
    console.log('='.repeat(60));
    return 0;
  }

  if (errors.length > 0) {
    const grouped = groupByRule(errors);
    for (const [rule, items] of grouped.entries()) {
      console.log(colors.red(`\n[${rule}] (${items.length} errors)`));
      console.log(colors.dim('-'.repeat(40)));
      for (const item of items) {
        console.log(colors.red(`  ✗ ${item.file}`));
        console.log(colors.dim(`    ${item.message}`));
        console.log(colors.cyan(`    → ${item.matchedText}`));
        if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
      }
    }
  }

  if (warnings.length > 0) {
    const grouped = groupByRule(warnings);
    for (const [rule, items] of grouped.entries()) {
      console.log(colors.yellow(`\n[${rule}] (${items.length} warnings)`));
      console.log(colors.dim('-'.repeat(40)));
      for (const item of items) {
        console.log(colors.yellow(`  ⚠ ${item.file}`));
        console.log(colors.dim(`    ${item.message}`));
        console.log(colors.cyan(`    → ${item.matchedText}`));
        if (item.suggestion) console.log(colors.cyan(`    → ${item.suggestion}`));
      }
    }
  }

  console.log('\n' + '='.repeat(60));
  const parts = [];
  if (errors.length > 0) parts.push(colors.red(`${errors.length} errors`));
  if (warnings.length > 0) parts.push(colors.yellow(`${warnings.length} warnings`));
  console.log(`SUMMARY: ${parts.join(', ')}`);
  console.log('='.repeat(60));
  return errors.length > 0 ? 1 : 0;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = process.argv.slice(2);
  const online = args.includes('--online');
  const help = args.includes('--help') || args.includes('-h');

  if (help) {
    console.log(`
Usage: node scripts/validate-comparison-refs.js [options]

Options:
  --online    Also check that reference URLs are reachable (slower)
  --help, -h  Show this help message

Rules (always enforced — offline):
  missing-comparison-ref   Every comparison feature must have refs matching values length
  invalid-ref-index        Every ref must be 0 or valid 1-based index into references.items
  missing-ref-url          Referenced items must have non-empty url fields

Rules (--online only):
  ref-url-unreachable      Reference URLs must return 2xx/3xx HTTP status
`);
    process.exit(0);
  }

  const jsonPath = path.join(TRANSLATIONS_DIR, 'en.json');
  if (!fs.existsSync(jsonPath)) {
    console.log(colors.red('en.json not found'));
    process.exit(1);
  }

  const translations = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));

  console.log(colors.dim(`Scanning comparison tables in ${jsonPath}...`));

  const errors = [];
  const warnings = [];

  // Offline checks
  validateOffline(translations, errors);

  // Online checks
  if (online) {
    console.log(colors.dim('Online mode: checking reference URLs...'));
    await validateOnline(translations, errors);
  }

  process.exit(printSummary(errors, warnings));
}

main();
