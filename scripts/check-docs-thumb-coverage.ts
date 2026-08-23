#!/usr/bin/env tsx
/**
 * check:ci-docs-thumb-coverage -- the half of www-round5's gate 3 that the content
 * schema does NOT cover.
 *
 * GATE 3 WAS SPECIFIED AS THREE ASSERTIONS and one of them moved. The original plan
 * (agent/programs/www-round5/05-gates.md) had this gate assert that (a) `subcategory` is
 * present and legal FOR that doc's category, (b) the browse card renders it, and (c) a
 * per-doc thumbnail exists. Assertion (a) is now enforced by the content collection schema
 * itself: `content/config.ts` carries `z.enum(DOC_SUBCATEGORY_VALUES)` plus a superRefine
 * that checks category legality, so an illegal value is rejected at build time by name.
 * Re-implementing it here would be a second, weaker copy of a check that already cannot be
 * bypassed. What is left, and what this gate owns, is (c).
 *
 * WHY (c) NEEDS A GATE AT ALL. The thumbnails are hand-authored. The generator that drew
 * them is gone, so there is no regenerate script and no way to notice a gap except by
 * looking at the rendered card, which nobody does per-locale. A new doc without a
 * hand-authored thumbnail ships a blank card in all 13 locales silently. This gate makes
 * that a build failure instead.
 *
 * ONE THUMBNAIL SERVES ALL 13 LOCALES. Resolution is by BASE SLUG through the filename
 * convention, so a doc's translations share `<base-slug>.svg`. That is why this checks the
 * English collection and not 1,015 rendered pages: checking the other twelve would report
 * the same missing file twelve times and make the real count unreadable.
 *
 * ANTI-VACUITY. The English docs collection is 79 files. A run that discovers fewer is not
 * seeing the collection, and its green would mean nothing, so it FAILS rather than passing
 * quietly. The counts print on success for the same reason: a number that collapses should
 * be visible in the log, not inferred from an absent complaint.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');

const DOCS_DIR = path.join(REPO, 'packages/www/src/content/docs/en');
const THUMB_DIR = path.join(REPO, 'packages/www/public/img/docs-thumbs');

/**
 * The measured English corpus is 79. The floor sits below it deliberately: this is a
 * "the glob collapsed" tripwire, not an assertion that the corpus never shrinks. A doc
 * being deleted is legitimate; the collection vanishing is not.
 */
const MIN_DOCS = 50;

const baseSlug = (filename: string): string => filename.replace(/\.mdx?$/, '');

export const scan = (
  docsDir: string,
  thumbDir: string
): { docs: string[]; missing: string[]; thumbs: number } => {
  let entries: string[];
  try {
    entries = fs.readdirSync(docsDir);
  } catch {
    return { docs: [], missing: [], thumbs: 0 };
  }
  const docs = entries.filter((f) => f.endsWith('.md') || f.endsWith('.mdx')).map(baseSlug).sort();
  let thumbs: string[] = [];
  try {
    thumbs = fs.readdirSync(thumbDir).filter((f) => f.endsWith('.svg'));
  } catch {
    thumbs = [];
  }
  const have = new Set(thumbs.map((f) => f.replace(/\.svg$/, '')));
  return { docs, missing: docs.filter((s) => !have.has(s)), thumbs: thumbs.length };
};

const selftest = (): number => {
  let pass = 0;
  let fail = 0;
  const check = (name: string, ok: boolean, detail?: string): void => {
    if (ok) {
      pass += 1;
      console.log(`  PASS  ${name}`);
    } else {
      fail += 1;
      console.log(`  FAIL  ${name}${detail === undefined ? '' : ` -- ${detail}`}`);
    }
  };

  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'thumb-selftest-'));
  const d = path.join(tmp, 'docs');
  const t = path.join(tmp, 'thumbs');
  fs.mkdirSync(d);
  fs.mkdirSync(t);
  fs.writeFileSync(path.join(d, 'alpha.md'), '');
  fs.writeFileSync(path.join(d, 'beta.mdx'), '');
  fs.writeFileSync(path.join(t, 'alpha.svg'), '<svg/>');
  fs.writeFileSync(path.join(t, 'beta.svg'), '<svg/>');

  check('full coverage reports nothing missing', scan(d, t).missing.length === 0);

  // THE CONTROL THAT MATTERS: remove one thumbnail and require the gate to name that
  // specific doc. Asserting only the green above would pass for a function that returned
  // an empty array unconditionally.
  fs.rmSync(path.join(t, 'beta.svg'));
  const gap = scan(d, t);
  check('removing ONE thumbnail names exactly that doc', gap.missing.join(',') === 'beta', `got ${gap.missing.join(',')}`);
  check('and it does not spuriously flag the covered one', !gap.missing.includes('alpha'));

  // .mdx must resolve the same way .md does, or half the corpus is silently unchecked.
  check('an .mdx doc participates in coverage', scan(d, t).docs.includes('beta'));

  // A missing thumbnail DIRECTORY is total absence, not total coverage.
  const gone = scan(d, path.join(tmp, 'no-such-dir'));
  check('a missing thumbnail directory reports every doc, not zero', gone.missing.length === 2);

  // An unreadable docs dir must yield zero docs, which main() then treats as a hard
  // failure via the floor rather than as "nothing to check".
  check('an unreadable docs dir yields zero docs', scan(path.join(tmp, 'nope'), t).docs.length === 0);

  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\nselftest: ${pass} passed, ${fail} failed`);
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const { docs, missing, thumbs } = scan(DOCS_DIR, THUMB_DIR);

  if (docs.length < MIN_DOCS) {
    console.error(
      `✗ discovered only ${docs.length} English doc(s) under ` +
        `${path.relative(REPO, DOCS_DIR)}, below the floor of ${MIN_DOCS}.`
    );
    console.error('  The collection is not being seen, so a green here would mean nothing.');
    return 1;
  }

  if (missing.length > 0) {
    console.error(`✗ ${missing.length} doc(s) have no hand-authored thumbnail:\n`);
    for (const slug of missing) console.error(`  ${slug}  ->  img/docs-thumbs/${slug}.svg`);
    console.error('\n  The browse card renders blank for these in ALL 13 locales: one thumbnail');
    console.error('  serves every translation, resolved by base slug.');
    console.error('\n  There is NO regenerate script; the generator was deleted. Author the file by');
    console.error('  hand, viewBox="0 0 320 120", matching a sibling in that directory.');
    return 1;
  }

  console.log(
    `✓ every doc has a thumbnail. ${docs.length} English doc(s), ${thumbs} thumbnail file(s).`
  );
  return 0;
};

process.exit(main());
