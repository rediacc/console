#!/usr/bin/env node
/**
 * The hand-authored illustrations have a contract, and until now only discipline held it.
 *
 * `agent/PLAN-*` recorded the gap in as many words: "Constraint, documented not gated:
 * textless is operator decision L4 (solution-illustration.ts:4, SPProblem.astro:40,
 * persona-pages.ts:26-27). No CI check enforces it. Discipline, not machinery -- so it
 * goes in the review checklist." A review checklist is a person remembering; this is the
 * machinery.
 *
 * THREE INVARIANTS, each with a consequence rather than a preference behind it:
 *
 *   TEXTLESS. One file serves all 13 locales precisely because it contains no words. A
 *   single <text> element silently makes an asset English-only, and nothing downstream
 *   notices: the drawing still renders, in the wrong language, on twelve locales.
 *
 *   TOKEN-PAINTED. Every colour must arrive through `var(--illustration-*, #fallback)`.
 *   A bare hex renders identically in light mode and is invisible in dark, which is how
 *   521 illustrations once shipped with a hardcoded `#f5f5f5` background that nobody
 *   could theme (see check-svg-theme-reach.ts, the gate for the OTHER half of that
 *   story: an SVG that asks for tokens must be inlined to receive them).
 *
 *   SCALABLE. A `viewBox` is what lets the same file be a 240px diagram and a 64px
 *   thumbnail. Without one the asset has a fixed intrinsic size and the CSS that scales
 *   it silently stops working.
 *
 * THE REGRESSION THIS IS AIMED AT IS CONCRETE, not hypothetical. `private/growth`'s
 * `illustration_pipeline` produces output that violates all three: its staged
 * `instant-recovery.svg` was measured carrying 3 <text> elements, 0
 * `var(--illustration-*)` tokens and hardcoded hex fills, against 0 / 4 / none in the 21
 * live files. That pipeline is one `cp` away from this directory.
 *
 * ZERO DEBT, so no baseline: 26 assets, all clean as of this commit.
 *
 * Usage:
 *   npx tsx scripts/check-illustration-contract.ts [--selftest]
 *
 * Exit: 0 clean, 1 finding (or a floor breach), 2 usage error.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const DIRS = [
  'packages/www/src/assets/images/illustrations',
  'packages/www/src/assets/images/disclosure',
];

/** Below this the glob is not seeing the tree and a green would mean nothing. */
const MIN_FILES = 20;

/** A hex colour that is NOT the fallback slot of an --illustration-* custom property. */
const TOKEN_FALLBACK = /var\(--illustration-[a-z-]+,\s*#[0-9a-fA-F]{3,8}\)/g;

export interface Finding {
  file: string;
  problems: string[];
}

/**
 * Judged from the file's text, exported so the controls drive the SAME function the real
 * scan does. A control that runs a reimplementation proves only that the copy agrees.
 */
export function judgeSvg(file: string, svg: string): Finding {
  const problems: string[] = [];

  const texts = svg.match(/<text\b/g)?.length ?? 0;
  if (texts > 0) {
    problems.push(
      `${texts} <text> element(s): the drawings are textless (operator decision L4) so one ` +
        'file can serve all 13 locales. Words here ship English on every locale.'
    );
  }

  // Strip the legitimate `var(--illustration-x, #hex)` fallbacks first; whatever hex
  // survives is a colour no theme can reach.
  const bare = svg.replace(TOKEN_FALLBACK, '').match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
  if (bare.length > 0) {
    problems.push(
      `${bare.length} hardcoded colour(s) (${[...new Set(bare)].slice(0, 4).join(', ')}): ` +
        'paint through var(--illustration-ink / -ink-soft / -surface / -accent) so the ' +
        'asset follows the theme.'
    );
  }

  if (!/\bviewBox\s*=/.test(svg)) {
    problems.push(
      'no viewBox: the asset cannot scale, so the CSS that renders it at 64px and at ' +
        '240px silently stops working.'
    );
  }

  return { file, problems };
}

const CONTROLS: { name: string; svg: string; expect: string | null }[] = [
  {
    name: 'the pipeline shape: <text> in an illustration is reported',
    svg: '<svg viewBox="0 0 800 450"><text x="10" y="10">Instant Recovery</text></svg>',
    expect: '<text>',
  },
  {
    name: 'a hardcoded hex outside a token fallback is reported',
    svg: '<svg viewBox="0 0 800 450"><rect fill="#1a1a1a"/></svg>',
    expect: 'hardcoded colour',
  },
  {
    name: 'CONTROL: a hex INSIDE a token fallback is not a hardcoded colour',
    svg: '<svg viewBox="0 0 800 450"><rect style="fill:var(--illustration-surface,#ffffff)"/></svg>',
    expect: null,
  },
  {
    name: 'a missing viewBox is reported',
    svg: '<svg width="800" height="450"><rect style="stroke:var(--illustration-ink,#1a1a1a)"/></svg>',
    expect: 'no viewBox',
  },
  {
    name: 'CONTROL: a conforming asset produces no findings',
    svg: '<svg viewBox="0 0 120 80" width="120" height="80"><rect style="fill:var(--illustration-surface,#ffffff);stroke:var(--illustration-ink,#1a1a1a)"/></svg>',
    expect: null,
  },
  {
    name: 'CONTROL: all three problems on one asset are all reported, not just the first',
    svg: '<svg width="800"><text>x</text><rect fill="#abc"/></svg>',
    expect: 'no viewBox',
  },
];

function selftest(): number {
  let bad = 0;
  for (const c of CONTROLS) {
    const { problems } = judgeSvg('control.svg', c.svg);
    const ok =
      c.expect === null ? problems.length === 0 : problems.some((p) => p.includes(c.expect));
    if (!ok) bad++;
    process.stdout.write(`  ${ok ? 'PASS' : 'FAIL'}  ${c.name}\n`);
  }
  // The last control also asserts the COUNT, since "reports the first problem and stops"
  // would satisfy every case above.
  const all = judgeSvg('control.svg', '<svg width="800"><text>x</text><rect fill="#abc"/></svg>');
  if (all.problems.length !== 3) {
    process.stdout.write(
      `  FAIL  CONTROL: three problems yield three findings (got ${all.problems.length})\n`
    );
    bad++;
  } else {
    process.stdout.write('  PASS  CONTROL: three problems yield three findings\n');
  }
  if (bad > 0) {
    process.stderr.write(`check-illustration-contract: ${bad} control(s) failed\n`);
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
    for (const f of fs.readdirSync(full)) if (f.endsWith('.svg')) files.push(path.join(full, f));
  }

  if (files.length < MIN_FILES) {
    process.stderr.write(
      `check-illustration-contract: found ${files.length} asset(s) under ${DIRS.join(', ')}, ` +
        `below the floor of ${MIN_FILES}.\n  The scan is not seeing the tree, so this verdict ` +
        'would be vacuous.\n'
    );
    return 1;
  }

  const findings = files
    .map((f) => judgeSvg(path.relative(REPO, f), fs.readFileSync(f, 'utf8')))
    .filter((v) => v.problems.length > 0);

  if (findings.length > 0) {
    process.stderr.write(
      `\x1b[31m✗\x1b[0m ${findings.length} illustration(s) break the contract:\n\n`
    );
    for (const v of findings) {
      process.stderr.write(`  ${v.file}\n`);
      for (const p of v.problems) process.stderr.write(`    - ${p}\n`);
    }
    return 1;
  }

  process.stdout.write(
    `\x1b[32m✓\x1b[0m ${files.length} hand-authored illustration(s): textless, token-painted, scalable.\n`
  );
  return 0;
}

process.exit(main(process.argv.slice(2)));
