#!/usr/bin/env tsx
/**
 * check:ci-docs-copy-units -- the code-block copy affordance, judged against the real
 * docs corpus.
 *
 * THE DEFECT THIS CLOSES, paid for on 2026-08-24. `addPerLineCopy` in DocsLayout.astro
 * called a line "runnable" when it was neither blank nor a comment, which is true of
 * almost every line of almost every code block. That put a copy button on 9 of the 13
 * lines of the Rediaccfile on /en/docs/rules-of-rediacc -- three of them a bare `}` --
 * and on all 3 lines of each YAML fragment beneath it. No gate could see it: it is a
 * property of rendered behaviour over content, and lint and tsc are both blind to it.
 *
 * IT RUNS PRODUCTION CODE, NOT A COPY OF IT. The classifier is lifted out of the inline
 * script in DocsLayout.astro at gate time and evaluated. A reimplementation here would
 * be a second, weaker copy that can agree with itself while the shipped script rots --
 * which is exactly how a selftest in this repo once passed while touching no production
 * code at all.
 *
 * ANTI-VACUITY. A run that discovers fewer than 400 fenced blocks is not seeing the
 * corpus and FAILS rather than passing quietly; the counts print on success so a
 * collapse is visible in the log instead of inferred from an absent complaint.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const LAYOUT = path.join(REPO, 'packages/www/src/layouts/DocsLayout.astro');
const DOCS = path.join(REPO, 'packages/www/src/content/docs/en');
const MIN_BLOCKS = 400;

type Unit = { start: number; end: number; name: string };
type Classifier = {
  SHELL_LANGS: Record<string, number>;
  looksLikeScript: (t: string[]) => boolean;
  functionUnits: (t: string[]) => Unit[];
  commandUnits: (t: string[]) => Unit[];
};

/** Lift the four symbols out of the shipped inline script. */
export const loadClassifier = (source: string): Classifier => {
  const start = source.indexOf('      var SHELL_LANGS = {');
  const end = source.indexOf('      function addUnitCopy(');
  if (start < 0 || end < 0 || end <= start) {
    throw new Error(
      'cannot find the classifier in DocsLayout.astro. If it was renamed, this gate ' +
        'must follow it rather than be deleted.'
    );
  }
  const body = source.slice(start, end);
  return new Function(
    `${body}\nreturn { SHELL_LANGS, looksLikeScript, functionUnits, commandUnits };`
  )() as Classifier;
};

/** The same decision addUnitCopy makes, expressed over text. */
export const unitsFor = (c: Classifier, lang: string, texts: string[]): Unit[] => {
  if (c.SHELL_LANGS[lang] !== 1) return [];
  if (c.looksLikeScript(texts)) {
    const units = c.functionUnits(texts);
    const body = texts.filter((t) => t.trim() !== '').length;
    if (units.length === 1 && units[0].end - units[0].start + 1 >= body) return [];
    return units;
  }
  const units = c.commandUnits(texts);
  return units.length < 2 ? [] : units;
};

const blocks = (text: string): { lang: string; texts: string[] }[] => {
  const lines = text.split('\n');
  const out: { lang: string; texts: string[] }[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const m = /^```([A-Za-z0-9_+-]+)\s*$/.exec(lines[i]);
    if (!m) continue;
    const body: string[] = [];
    let j = i + 1;
    for (; j < lines.length && !lines[j].startsWith('```'); j += 1) body.push(lines[j]);
    out.push({ lang: m[1], texts: body });
    i = j;
  }
  return out;
};

const DANGLING = new Set(['}', 'fi', 'done', 'esac', 'EOF']);

/**
 * THE GATE'S OWN LIST, and it must stay independent of the classifier's.
 *
 * The first version of this check asked `units.length && SHELL_LANGS[lang] !== 1`, which
 * CANNOT FIRE: unitsFor already returns [] for a non-shell fence, so the two halves are
 * the same question and the conjunction is dead. Planting `yaml: 1` into the shipped
 * SHELL_LANGS was caught only because the planted-defect run came back green. Judging the
 * classifier against a list it does not own is what makes the assertion real.
 */
const SHELLY = new Set(['bash', 'sh', 'shell', 'shellscript', 'zsh', 'console', 'shellsession', 'powershell', 'ps1']);

const selftest = (c: Classifier): number => {
  let fail = 0;
  const check = (name: string, ok: boolean, detail = ''): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  };
  const u = (lang: string, src: string) => unitsFor(c, lang, src.split('\n'));

  // THE CONTROL THAT MATTERS: the exact shape that shipped broken.
  const rediaccfile = '#!/bin/bash\n\n_compose() {\n  renet compose -- "$@"\n}\n\nup() {\n  _compose up -d\n}';
  const fns = u('bash', rediaccfile);
  check('a Rediaccfile yields one unit per function', fns.map((f) => f.name).join(',') === '_compose,up', JSON.stringify(fns));
  check('and none of them starts on a closing brace', fns.every((f) => !DANGLING.has(rediaccfile.split('\n')[f.start].trim())));

  check('a yaml fragment yields nothing', u('yaml', 'labels:\n  - "a=1"\n  - "b=2"').length === 0);
  check('a json fragment yields nothing', u('json', '{\n  "a": 1,\n  "b": 2\n}').length === 0);
  check('a two-command recipe still yields two units', u('bash', 'rdc repo list\nrdc doctor').length === 2);
  check('a one-command block yields nothing', u('bash', 'rdc repo list').length === 0);
  check('comments do not count as commands', u('bash', '# note\nrdc doctor').length === 0);
  check('a trailing backslash joins its continuation', u('bash', 'curl -X POST \\\n  -H "a: b" \\\n  http://x\nrdc doctor').length === 2);
  check('a heredoc is one unit, not one per body line', u('bash', "cat > f <<'EOF'\nline one\nline two\nEOF\nrdc doctor").length === 2);
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  const c = loadClassifier(fs.readFileSync(LAYOUT, 'utf8'));
  if (process.argv.slice(2).includes('--selftest')) return selftest(c);

  let total = 0;
  const offences: string[] = [];
  let withUnits = 0;
  for (const file of fs.readdirSync(DOCS).filter((f) => /\.mdx?$/.test(f))) {
    const text = fs.readFileSync(path.join(DOCS, file), 'utf8');
    for (const b of blocks(text)) {
      total += 1;
      const units = unitsFor(c, b.lang, b.texts);
      if (units.length) withUnits += 1;
      if (units.length && !SHELLY.has(b.lang)) {
        offences.push(`${file}: a ${b.lang} block offers ${units.length} copy unit(s)`);
      }
      for (const unit of units) {
        const head = (b.texts[unit.start] || '').trim();
        if (DANGLING.has(head)) {
          offences.push(`${file}: a copy unit starts on \`${head}\`, which is not a command`);
        }
      }
    }
  }

  if (total < MIN_BLOCKS) {
    console.error(`✗ discovered only ${total} fenced block(s) under ${path.relative(REPO, DOCS)}, below the floor of ${MIN_BLOCKS}.`);
    console.error('  The corpus is not being seen, so a green here would mean nothing.');
    return 1;
  }
  if (offences.length) {
    console.error(`✗ ${offences.length} code block(s) offer a copy control on something nobody can paste:\n`);
    for (const o of offences.slice(0, 30)) console.error(`  ${o}`);
    console.error('\n  addUnitCopy in packages/www/src/layouts/DocsLayout.astro decides this in three');
    console.error('  parts: is the fence a shell language, is the block a file or a recipe, and');
    console.error('  where does one command end. Fix it there, not by narrowing this gate.');
    return 1;
  }
  console.log(`✓ ${total} fenced block(s) checked; ${withUnits} offer per-unit copy, none on a non-shell fence or a dangling terminator.`);
  return 0;
};

process.exit(main());
