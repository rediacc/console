#!/usr/bin/env node
/**
 * Enforce two invariants on the rendered HTML output for the Design
 * Partner Program "joker" CTA (`.cta-bolt`, bolt-red, drawn from the
 * central bolt in the Rediacc logo):
 *
 *   1. AT MOST ONE per page (always). Multiple bolts dilute the cue.
 *   2. EXACTLY ONE per page on opt-in pages (only when the program is
 *      active). Opt-in is signaled by an HTML comment in the rendered
 *      output:  <!--@ci cta-bolt-required-->
 *      Templates emit this comment from inside their `dpActive` branch,
 *      so when the program is off the comment is absent everywhere and
 *      the `===1` rule is naturally moot.
 *
 * Program state is read from the same canonical source the runtime
 * helper uses: packages/www/src/i18n/translations/en.json's
 * `announcement.enabled`. When false, the `===1` check is skipped
 * entirely (only the `<=1` cap runs) so disabling the program for
 * testing does not flood CI with false failures.
 *
 * Wired into `npm run ci` via the root `check:ci-cta-bolt` script.
 * Locally: `cd packages/www && npm run build && npm run check:cta-bolt`.
 */
import { readdir, readFile, stat } from 'node:fs/promises';
import path from 'node:path';

const MARKER = '<!--@ci cta-bolt-required-->';

async function findHtml(dir) {
  const out = [];
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await findHtml(full)));
    } else if (entry.isFile() && entry.name.endsWith('.html')) {
      out.push(full);
    }
  }
  return out;
}

function countBolts(html) {
  const re = /class\s*=\s*("(?:[^"]*?)"|'(?:[^']*?)')/g;
  let count = 0;
  let m;
  while ((m = re.exec(html)) !== null) {
    const value = m[1].slice(1, -1);
    if (/\bcta-bolt\b/.test(value)) count += 1;
  }
  return count;
}

function hasMarker(html) {
  return html.includes(MARKER);
}

async function isProgramActive() {
  const enPath = path.resolve(
    import.meta.dirname,
    '..',
    'src',
    'i18n',
    'translations',
    'en.json'
  );
  const en = JSON.parse(await readFile(enPath, 'utf8'));
  return en?.announcement?.enabled === true;
}

async function main() {
  const dist = path.resolve(import.meta.dirname, '..', 'dist');
  try {
    await stat(dist);
  } catch {
    console.error(`[check-cta-bolt] dist not found at ${dist}. Run \`npm run build\` first.`);
    process.exit(2);
  }

  const programActive = await isProgramActive();
  const files = await findHtml(dist);
  if (files.length === 0) {
    console.error(`[check-cta-bolt] no HTML files under ${dist}. Build output empty?`);
    process.exit(2);
  }

  const tooMany = []; // count > 1
  const missingRequired = []; // marker present, count === 0
  let requiredEnforcedPages = 0;

  for (const file of files) {
    const html = await readFile(file, 'utf8');
    const count = countBolts(html);
    const required = programActive && hasMarker(html);
    if (required) requiredEnforcedPages += 1;

    if (count > 1) {
      tooMany.push({ file: path.relative(dist, file), count });
    } else if (required && count === 0) {
      missingRequired.push({ file: path.relative(dist, file) });
    }
  }

  let failed = false;

  if (tooMany.length > 0) {
    console.error(
      `[check-cta-bolt] FAIL — ${tooMany.length} page(s) have more than one .cta-bolt button.`
    );
    console.error(
      'Each page must have at most ONE bolt-red CTA (the "joker"). Move surplus bolts'
    );
    console.error(
      'to .sp-btn-primary / .cf-cta-featured / etc. without the `cta-bolt` class.'
    );
    console.error('');
    for (const v of tooMany) {
      console.error(`  ${v.file}  —  ${v.count} occurrences`);
    }
    failed = true;
  }

  if (missingRequired.length > 0) {
    if (failed) console.error('');
    console.error(
      `[check-cta-bolt] FAIL — ${missingRequired.length} page(s) declared cta-bolt-required but render zero bolts.`
    );
    console.error(
      `Add \`cta-bolt\` to a CTA on the page, or remove ${MARKER} if the page is no longer high-intent.`
    );
    console.error('');
    for (const v of missingRequired) {
      console.error(`  ${v.file}`);
    }
    failed = true;
  }

  if (failed) process.exit(1);

  const enforcement = programActive
    ? `on (${requiredEnforcedPages} required-bolt page(s) verified)`
    : 'off (program disabled)';
  console.log(
    `[check-cta-bolt] OK — ${files.length} pages checked, max 1 bolt per page; required-bolt enforcement: ${enforcement}.`
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
