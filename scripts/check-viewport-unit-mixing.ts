#!/usr/bin/env node
/**
 * A positioned box may not size itself against the VIEWPORT and place itself against its
 * CONTAINING BLOCK. On this site those are not the same width.
 *
 * WHY THEY DIFFER. `scrollbar-gutter: stable` reserves the scrollbar, so the initial
 * containing block is 15px narrower than the viewport: 1425px inside a 1440px window. A
 * `position: fixed` element's percentages resolve against the ICB while its `vw` units
 * resolve against the viewport, so a rule that mixes them is measuring one object with two
 * rulers.
 *
 * WHAT IT COST, twice, on this branch. `.overlay-backdrop` and `.sp-disclosure-pop` were
 * fixed under operator ruling R2 (f73d9c328); `.persona-menu-panel` was found later, with
 * the identical 7.5px offset, and it had been HALF converted for months without anyone
 * noticing:
 *
 *     position: fixed;
 *     left: 50%;                                        <- containing block
 *     width: min(calc(100vw - var(--space-8) * 2), 1020px);  <- viewport
 *
 * Measured on /en/solutions/environment-cloning at 1440: a 1020px panel centred at 712.5
 * against a viewport centre of 720.
 *
 * WHY A STATIC CHECK WHEN check:ci-page-density ALREADY MEASURES CENTRING. They catch it
 * at different moments and neither subsumes the other. The runtime gate needs a built site
 * and a browser and only sees the routes it drives; this one is sub-second, sees every
 * stylesheet including surfaces no route in that gate visits, and fires on the edit rather
 * than on the build. The mixing is also the CAUSE rather than the symptom, so this names
 * the two lines to change instead of an x-coordinate.
 *
 * ZERO DEBT, therefore no baseline: the tree is clean as of this commit, verified against
 * every stylesheet. The one rule that had the signature is fixed.
 *
 * Usage:
 *   npx tsx scripts/check-viewport-unit-mixing.ts [--selftest]
 *
 * Exit: 0 clean, 1 finding (or a floor breach), 2 usage error.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const DIRS = ['packages/www/src/styles', 'packages/www/public/styles'];

/** Below this the glob is not seeing the tree and a green would mean nothing. */
const MIN_FILES = 10;

const POSITIONED = /position:\s*(fixed|absolute)/;
/**
 * A viewport unit inside a width declaration.
 *
 * `\bvw\b` DOES NOT WORK and cost a false clean: in `100vw` the `0` and the `v` are both
 * word characters, so there is no boundary between them, and the first version of this
 * scan reported zero findings on a rule that plainly had the signature. The character
 * before `vw` is a digit, a dot or a closing paren, so require one of those.
 */
const VW_WIDTH = /\b(width|max-width|min-width)\s*:[^;]*[\d.)]vw/;
const PCT_POS = /\b(left|right|inset-inline-start|inset-inline-end)\s*:\s*50%/;
const VW_POS = /\b(left|right|inset-inline-start|inset-inline-end)\s*:\s*50vw/;

export interface Finding {
  file: string;
  selector: string;
}

/**
 * Judged from stylesheet text, exported so the controls drive the SAME function the real
 * scan does. A control that runs a reimplementation proves only that the copy agrees.
 */
export function judgeCss(file: string, css: string): Finding[] {
  const out: Finding[] = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const body = m[2];
    if (!POSITIONED.test(body)) continue;
    // A rule that already positions in `vw` is the FIXED shape, not a finding.
    if (VW_POS.test(body)) continue;
    if (!VW_WIDTH.test(body) || !PCT_POS.test(body)) continue;
    const selector = (m[1].trim().split('\n').pop() ?? '').trim();
    out.push({ file, selector: selector.slice(0, 80) });
  }
  return out;
}

const CONTROLS: { name: string; css: string; want: number }[] = [
  {
    name: 'the real case: fixed, left:50%, width in vw is reported',
    css: '.persona-menu-panel { position: fixed; left: 50%; transform: translateX(-50%); width: min(calc(100vw - 32px), 1020px); }',
    want: 1,
  },
  {
    name: 'CONTROL: the FIXED shape, left:50vw with a vw width, is silent',
    css: '.persona-menu-panel { position: fixed; left: 50vw; transform: translateX(-50%); width: min(calc(100vw - 32px), 1020px); }',
    want: 0,
  },
  {
    name: 'CONTROL: a percentage width with a percentage position is silent (one ruler)',
    css: '.tip { position: absolute; left: 50%; width: 80%; }',
    want: 0,
  },
  {
    name: 'CONTROL: a vw width on a STATIC element is silent (no containing-block question)',
    css: '.hero { width: 100vw; left: 50%; }',
    want: 0,
  },
  {
    name: 'CONTROL: a vw width with no horizontal placement is silent',
    css: '.bar { position: fixed; inset: 0; width: 100vw; }',
    want: 0,
  },
  {
    name: 'CONTROL: `100vw` is matched, i.e. the word-boundary bug stays fixed',
    css: '.x { position: fixed; left: 50%; max-width: 100vw; }',
    want: 1,
  },
];

function selftest(): number {
  let bad = 0;
  for (const c of CONTROLS) {
    const got = judgeCss('control.css', c.css).length;
    const ok = got === c.want;
    if (!ok) bad++;
    process.stdout.write(
      `  ${ok ? 'PASS' : 'FAIL'}  ${c.name}${ok ? '' : ` (want ${c.want}, got ${got})`}\n`
    );
  }
  if (bad > 0) {
    process.stderr.write(`check-viewport-unit-mixing: ${bad} control(s) failed\n`);
    return 1;
  }
  return 0;
}

function main(argv: string[]): number {
  for (const a of argv) {
    if (a === '--selftest') {
      const rc = selftest();
      if (rc !== 0) return rc;
    } else {
      process.stderr.write(`unknown argument: ${a}\n`);
      return 2;
    }
  }

  const files: string[] = [];
  for (const d of DIRS) {
    const full = path.join(REPO, d);
    if (!fs.existsSync(full)) continue;
    for (const f of fs.readdirSync(full)) if (f.endsWith('.css')) files.push(path.join(full, f));
  }

  if (files.length < MIN_FILES) {
    process.stderr.write(
      `check-viewport-unit-mixing: found ${files.length} stylesheet(s) under ${DIRS.join(', ')}, ` +
        `below the floor of ${MIN_FILES}.\n  The scan is not seeing the tree, so this verdict would be vacuous.\n`
    );
    return 1;
  }

  const findings = files.flatMap((f) =>
    judgeCss(path.relative(REPO, f), fs.readFileSync(f, 'utf8'))
  );

  if (findings.length > 0) {
    process.stderr.write(
      `\x1b[31m✗\x1b[0m ${findings.length} rule(s) size against the viewport and position against the containing block:\n\n`
    );
    for (const f of findings) process.stderr.write(`  ${f.file}\n    ${f.selector}\n`);
    process.stderr.write(
      '\n  `scrollbar-gutter: stable` leaves the containing block 15px narrower than the\n' +
        '  viewport, so a `50%` position and a `vw` width disagree by half of that. Measured\n' +
        '  on .persona-menu-panel: a 1020px panel centred at 712.5 against a viewport centre\n' +
        '  of 720.\n\n' +
        '  Use one ruler. For a viewport-centred overlay that is `left: 50vw` with the\n' +
        '  existing `translateX(-50%)`; for a box centred in its parent, drop the vw width.\n'
    );
    return 1;
  }

  process.stdout.write(
    `\x1b[32m✓\x1b[0m ${files.length} stylesheet(s): no positioned rule mixes a viewport-unit width ` +
      'with a containing-block position.\n'
  );
  return 0;
}

process.exit(main(process.argv.slice(2)));
