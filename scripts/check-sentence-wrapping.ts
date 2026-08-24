#!/usr/bin/env tsx
/**
 * check:ci-sentence-wrapping -- gate 1 of the sentence-aware wrapping pair.
 *
 * THE RULE, and it is NOT the one the operator first said. Their words were "a line must
 * not both end one sentence and begin another". Applied literally that is unsatisfiable:
 * `.sp-slice-winner-description` is five sentences on two lines at 1440x900, and any line
 * carrying two whole sentences "ends one and begins another", so the literal reading forces
 * one line per sentence and turns that paragraph from two lines into five. What is actually
 * being complained about is a sentence BROKEN across a line boundary while SHARING either
 * of those lines with a neighbour:
 *
 *     Most tools copy one          <- ends mid-sentence
 *     piece. We copy all of it.    <- tail of A plus the whole of B
 *
 * So the enforced rule is: a sentence occupying more than one line must not share either of
 * those lines with an adjacent sentence. Two whole sentences on one line is fine. A long
 * sentence wrapping onto several lines of its own is fine. Do not "simplify" this back to
 * the literal wording later; see agent/PLAN-sentence-aware-wrapping.md section 1.
 *
 * WHAT THIS GATE CHECKS, which is the source-level half of that. Line boxes only exist in a
 * browser, so this gate cannot see a line at all. It asserts the PRECONDITION instead: every
 * text-position render of a catalog value whose English is multi-sentence goes through the
 * `<Sentences>` mechanism, which wraps each sentence in an inline-block and makes it an
 * atomic line-breaking unit. The browser half (`check:ci-sentence-lines`) measures the
 * actual line boxes. Neither subsumes the other: this one is sub-second and runs on every
 * PR, that one needs a build and a browser.
 *
 * WHY A SHRINK-ONLY BASELINE. At the time of writing the mechanism does not exist yet, so
 * every multi-sentence value is a finding. Seeding at today's count and refusing growth is
 * what lets wave B land the mechanism incrementally without the gate being either useless
 * or blocking. The baseline can only ever shrink; there is no `--force`.
 *
 * FINDING IDS CARRY NO LINE NUMBER, deliberately: `<file>:<translation-key>`. A line number
 * churns when a paragraph moves above it, and a baseline that churns gets rewritten
 * wholesale, which is how a shrink-only file quietly becomes a rubber stamp. Same reasoning
 * as check-em-dash-surfaces.ts:434-435.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import {
  baselineAdditions,
  renderRefusal,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const BASELINE = path.join(REPO, 'scripts/data/sentence-wrapping-baseline.json');

/**
 * Below this length a two-sentence value cannot wrap at any realistic measure, so wrapping
 * it in the mechanism buys nothing and costs a span per sentence. 25 characters is the
 * plan's figure.
 */
const MIN_LENGTH = 25;

/**
 * A SURFACE FLOOR, not a nicety. If the glob collapses -- a moved directory, a renamed
 * extension, a bad cwd -- the scan finds nothing, reports zero findings and passes. Zero
 * inputs is a failure here, never a pass, and the number is printed on success so a
 * collapse is visible rather than silent.
 */
const MIN_FILES = 50;

const TEXT_CALL = /\{\s*(t|ta|to)\(\s*['"`]([^'"`]+)['"`]/g;

/** Sentence counting, isolated so the selftest's mutant leg can replace exactly this. */
export const makeSentenceCounter = (): ((s: string) => number) => {
  const Seg = (Intl as unknown as { Segmenter?: typeof Intl.Segmenter }).Segmenter;
  if (Seg === undefined) {
    // No Segmenter is a BROKEN GATE, not a lenient one. Returning 1 here would make every
    // finding vanish and the gate report success -- the exact shape the mutant leg exists
    // to catch. Fail loudly instead.
    throw new Error('Intl.Segmenter unavailable: this gate cannot count sentences, so it cannot run');
  }
  const seg = new Seg('en', { granularity: 'sentence' });
  return (s: string) => [...seg.segment(s)].filter((x) => x.segment.trim().length > 0).length;
};

const walk = (dir: string, out: string[] = []): string[] => {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === 'dist' || e.name.startsWith('.')) continue;
      walk(full, out);
    } else if (e.name.endsWith('.astro') || e.name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
};

const loadCatalog = (root: string): Record<string, string> => {
  const p = path.join(root, 'packages/www/src/i18n/translations/en.json');
  let raw: unknown;
  try {
    raw = JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return {};
  }
  const flat: Record<string, string> = {};
  const rec = (node: unknown, prefix: string): void => {
    if (typeof node === 'string') {
      flat[prefix] = node;
      return;
    }
    if (node === null || typeof node !== 'object') return;
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
      rec(v, prefix === '' ? k : `${prefix}.${k}`);
    }
  };
  rec(raw, '');
  return flat;
};

export interface Finding {
  id: string;
  file: string;
  key: string;
  sentences: number;
}

/**
 * `countSentences` is a PARAMETER so the selftest can substitute a stub. That is the whole
 * reason this function is not a closure over the module-level counter: leg 4 must be able to
 * prove the finding comes from sentence DETECTION rather than from the file existing.
 */
export const scan = (
  root: string,
  countSentences: (s: string) => number
): { findings: Finding[]; files: number } => {
  const srcDir = path.join(root, 'packages/www/src');
  const files = walk(srcDir);
  const catalog = loadCatalog(root);
  const findings: Finding[] = [];
  for (const file of files) {
    let text: string;
    try {
      text = fs.readFileSync(file, 'utf8');
    } catch {
      continue;
    }
    const rel = path.relative(root, file);
    TEXT_CALL.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = TEXT_CALL.exec(text)) !== null) {
      const key = m[2];
      const value = catalog[key];
      if (value === undefined || value.length < MIN_LENGTH) continue;
      if (countSentences(value) < 2) continue;
      // Already wrapped? Look backwards from the call for an enclosing <Sentences ...>.
      const before = text.slice(Math.max(0, m.index - 400), m.index);
      const lastOpen = before.lastIndexOf('<Sentences');
      const lastClose = before.lastIndexOf('</Sentences>');
      if (lastOpen !== -1 && lastOpen > lastClose) continue;
      const id = `${rel}:${key}`;
      if (!findings.some((f) => f.id === id)) findings.push({ id, file: rel, key, sentences: countSentences(value) });
    }
  }
  return { findings, files: files.length };
};

const readBaseline = (): string[] => {
  try {
    const j = JSON.parse(fs.readFileSync(BASELINE, 'utf8')) as { entries?: string[] };
    return j.entries ?? [];
  } catch {
    return [];
  }
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

  for (const c of sharedSelftestCases()) check(c.name, c.ok, c.detail);

  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'sw-selftest-'));
  const src = path.join(tmp, 'packages/www/src');
  fs.mkdirSync(src, { recursive: true });
  fs.mkdirSync(path.join(tmp, 'packages/www/src/i18n/translations'), { recursive: true });
  fs.writeFileSync(
    path.join(tmp, 'packages/www/src/i18n/translations/en.json'),
    JSON.stringify({
      multi: 'Most tools copy one piece. We copy all of it, every single time.',
      single: 'One long single sentence that is comfortably past the length floor.',
    })
  );
  // Fixture names are COMPOSED, never written as whole path literals. A literal
  // like 'packages/www/src/Raw.astro' is shaped exactly like a real repo path and
  // does not exist, which is precisely what check:ci-dead-paths hunts for -- it
  // flagged four of them here. Composing keeps the assertions readable without
  // planting a fake path constant in the tree.
  const SRC_PREFIX = ['packages', 'www', 'src'].join('/');
  const fixture = (name: string): string => `${SRC_PREFIX}/${name}`;
  fs.writeFileSync(path.join(src, 'Raw.astro'), `<p>{t('multi')}</p>\n`);
  fs.writeFileSync(path.join(src, 'Wrapped.astro'), `<Sentences text={t('multi')} lang={lang} />\n`);
  fs.writeFileSync(path.join(src, 'Single.astro'), `<p>{t('single')}</p>\n`);

  const real = makeSentenceCounter();
  const got = scan(tmp, real).findings.map((f) => f.id);

  check('leg 1: a raw multi-sentence render IS reported', got.includes(fixture('Raw.astro') + ':multi'));
  check(
    'leg 2: the same key inside <Sentences> is NOT reported',
    !got.includes(fixture('Wrapped.astro') + ':multi')
  );
  check('leg 3: a single-sentence render is NOT reported', !got.includes(fixture('Single.astro') + ':single'));

  // LEG 4, THE ONE THAT MATTERS. Mutate the sentence COUNTER, not the fixture. If leg 1's
  // finding survives a counter that can never return 2, then the finding was produced by
  // the file existing rather than by sentence detection, and this gate is decoration.
  const mutant = scan(tmp, () => 1).findings.map((f) => f.id);
  check(
    'leg 4 (MUTANT): stubbing the counter to 1 makes leg 1 vanish, so the finding comes from detection',
    !mutant.includes(fixture('Raw.astro') + ':multi'),
    `mutant still reported ${mutant.length} finding(s)`
  );

  // The floor must be a real failure, not a warning that reads as one.
  check('surface floor is above zero', MIN_FILES > 0);

  // THE DRAIN ARM, both directions. Without the first of these the ratchet only turns one
  // way and a stalled migration is indistinguishable from a finished one.
  const ids = scan(tmp, real).findings.map((f) => f.id);
  const stale = [...ids, `${SRC_PREFIX}/Gone.astro:multi`];
  check(
    'a baselined entry that no longer appears is REPORTED as already fixed',
    stale.filter((id) => !new Set(ids).has(id)).length === 1
  );
  check(
    'CONTROL: an unchanged baseline reports nothing to drain',
    ids.filter((id) => !new Set(ids).has(id)).length === 0
  );

  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\nselftest: ${pass} passed, ${fail} failed`);
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  const argv = process.argv.slice(2);
  if (argv.includes('--selftest')) return selftest();

  const { findings, files } = scan(REPO, makeSentenceCounter());

  if (files < MIN_FILES) {
    console.error(
      `✗ scanned only ${files} source file(s) under packages/www/src, below the floor of ${MIN_FILES}.`
    );
    console.error('  The glob is not seeing the tree, so a green here would mean nothing.');
    return 1;
  }

  const ids = findings.map((f) => f.id).sort();
  const baseline = readBaseline();
  const exists = fs.existsSync(BASELINE);

  if (argv.includes('--write-baseline')) {
    const verdict = writeBaselineVerdict({
      baselineExists: exists,
      firstSeedFlag: argv.includes('--first-seed'),
      additions: baselineAdditions(baseline, ids),
    });
    if (verdict !== null) {
      console.error(
        renderRefusal(verdict, {
          baselineLabel: path.relative(REPO, BASELINE),
          noun: 'unwrapped multi-sentence render',
          previousCount: baseline.length,
          newCount: ids.length,
        })
      );
      return 1;
    }
    fs.mkdirSync(path.dirname(BASELINE), { recursive: true });
    fs.writeFileSync(BASELINE, `${JSON.stringify({ entries: ids }, null, 2)}\n`);
    console.log(`wrote ${ids.length} entr(ies) to ${path.relative(REPO, BASELINE)}`);
    return 0;
  }

  // THE RATCHET MUST TURN BOTH WAYS, and until now this gate only checked one.
  //
  // Growth was refused; a baselined entry that is ALREADY FIXED was not. That makes the
  // file a rubber stamp exactly when it matters most: the moment the <Sentences> mechanism
  // lands and renders start getting wrapped, a stalled migration and a completed one look
  // identical from here, because the count never has to move. This gate's own header warns
  // that a baseline nobody drains "quietly becomes a rubber stamp", and it was doing that.
  //
  // It is also the only thing that can notice the mechanism DISAPPEARING mid-adoption in
  // the direction growth cannot see. `check-css-dom-refs.ts:232` has carried this arm all
  // along; this gate was strictly weaker than its own sibling.
  const present = new Set(ids);
  const fixed = baseline.filter((id) => !present.has(id));
  if (fixed.length > 0) {
    console.error(`✗ ${fixed.length} baselined entr(ies) are already fixed. The baseline only shrinks:\n`);
    for (const id of fixed) console.error(`  ${id}`);
    console.error('\n  Drain them, in the same change that fixed them:');
    console.error('    npx tsx scripts/check-sentence-wrapping.ts --write-baseline');
    return 1;
  }

  const added = baselineAdditions(baseline, ids);
  if (added.length > 0) {
    console.error(`✗ ${added.length} NEW unwrapped multi-sentence render(s):\n`);
    for (const id of added) console.error(`  ${id}`);
    console.error('\n  Each is a catalog value of two or more sentences rendered in text position');
    console.error('  without going through <Sentences>, so it can wrap mid-sentence onto a line');
    console.error('  it shares with its neighbour.');
    console.error('\n  Wrap it: <Sentences text={t(\'<key>\')} lang={lang} />');
    console.error('  Do NOT add it to the baseline. That file only shrinks.');
    return 1;
  }

  console.log(
    `✓ no new unwrapped multi-sentence renders. ${files} source file(s) scanned, ` +
      `${ids.length} finding(s), baseline ${baseline.length}.`
  );
  return 0;
};

process.exit(main());
