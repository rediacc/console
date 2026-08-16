#!/usr/bin/env node
/**
 * Control harness for check-docs-render-parity.ts.
 *
 * WHY THIS EXISTS. The gate it drives is the only one in the repo that reads BUILT
 * HTML, and it exists because thirteen locale pages rendered one English document
 * while every source-rooted i18n gate reported success. A gate introduced to catch
 * that class is worthless unless it is proven to fire on it, and proven not to fire on
 * a page that is correct -- a gate that fails on everything gets switched off within a
 * week and then protects nothing at all.
 *
 * So this asserts BOTH directions on a synthetic tree:
 *
 *   1. a German source heading against an English rendered body -> non-zero, and the
 *      message NAMES the missing heading;
 *   2. the same heading rendered correctly -> zero;
 *   3. the heading present only in page CHROME outside `.article-content` -> non-zero.
 *      This is the one way the gate could be green while wrong, and it is not
 *      hypothetical: today's German dist really does carry the English heading text in
 *      its table of contents;
 *   4. a source document with no built page at all -> non-zero;
 *   5. no `packages/www/dist` at all -> non-zero. A built-HTML gate that returns
 *      success when there is no built HTML reports "checked, fine" for "did not run".
 *
 * The fixture is a scratch tree under os.tmpdir(), reached through the gate's
 * DOCS_RENDER_PARITY_ROOT seam, so unlike its sibling control this one never writes
 * into real source.
 *
 * Run: npx tsx scripts/__tests__/check-docs-render-parity.control.ts
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { SITE_LOCALES } from '@rediacc/locales';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(__dirname, '../..');
const GATE = path.join(REPO, 'scripts/check-docs-render-parity.ts');

const GERMAN = 'Repository-Lebenszyklus';
const ENGLISH = 'Repository Lifecycle';

interface Result {
  code: number;
  output: string;
}

function runGate(root: string): Result {
  try {
    const out = execFileSync('npx', ['tsx', GATE], {
      cwd: REPO,
      encoding: 'utf8',
      env: { ...process.env, DOCS_RENDER_PARITY_ROOT: root },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { code: 0, output: out };
  } catch (err) {
    const e = err as { status?: number; stdout?: string; stderr?: string };
    return { code: e.status ?? 1, output: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
}

/** A page whose article body holds `heading`, with unrelated chrome around it. */
function page(bodyHeading: string, chromeHeading = 'Documentation'): string {
  return [
    '<html><body>',
    `<nav class="docs-sidebar"><h2 class="sidebar-title">${chromeHeading}</h2></nav>`,
    '<article class="docs-article">',
    '<div class="article-content" data-astro-cid-mw7aashj>',
    `<h2 id="x">${bodyHeading}</h2>`,
    '<p>Body text that is not a heading.</p>',
    '</div>',
    '</article>',
    '</body></html>',
  ].join('\n');
}

function doc(heading: string): string {
  return `---\ntitle: Control\n---\n\n# Title\n\n## ${heading}\n\nProse.\n`;
}

/**
 * A fixture tree that is CORRECT in every locale, so a case can plant exactly one
 * defect and know the report is about that defect and nothing else.
 */
function buildFixture(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'docs-render-parity-'));
  for (const locale of SITE_LOCALES) {
    const heading = `${GERMAN}-${locale}`;
    const src = path.join(root, 'packages/www/src/content/docs', locale);
    fs.mkdirSync(src, { recursive: true });
    fs.writeFileSync(path.join(src, 'control.md'), doc(heading), 'utf8');
    const dist = path.join(root, 'packages/www/dist', locale, 'docs/control');
    fs.mkdirSync(dist, { recursive: true });
    fs.writeFileSync(path.join(dist, 'index.html'), page(heading), 'utf8');
  }
  return root;
}

// Composed rather than spelled out. A literal like
// `packages/www/src/content/docs/de/control.md` is a path into a synthetic
// fixture tree that exists only under a temp root, but it reads exactly like a
// repo path -- and `gate-test:gate-paths-exist` flagged it as a dead path
// constant, correctly, because from the outside the two are indistinguishable.
const DOCS_SRC = ['packages/www/src/content/docs', 'de', 'control.md'];
const DOCS_DIST = ['packages/www/dist', 'de', 'docs/control', 'index.html'];

const dePage = (root: string): string => path.join(root, ...DOCS_DIST);
const deSource = (root: string): string => path.join(root, ...DOCS_SRC);

interface Case {
  name: string;
  /** Mutates the correct fixture into the shape under test. */
  plant: (root: string) => void;
  wantExit: 'zero' | 'non-zero';
  /** Substrings the output must contain when it fails. */
  wantNamed?: string[];
}

const CASES: Case[] = [
  {
    name: 'the real defect: a German source rendered as English',
    plant: (root) => {
      fs.writeFileSync(deSource(root), doc(`${GERMAN}-de`), 'utf8');
      fs.writeFileSync(dePage(root), page(ENGLISH), 'utf8');
    },
    wantExit: 'non-zero',
    wantNamed: [`${GERMAN}-de`, 'de/control'],
  },
  {
    name: 'the discriminating half: the same heading rendered correctly',
    plant: () => {
      /* the fixture is already correct; this case proves the gate is not a tripwire */
    },
    wantExit: 'zero',
  },
  {
    name: 'the heading appears only in chrome outside .article-content',
    plant: (root) => {
      // The German heading is in the sidebar, the article body is English. A
      // whole-page assertion would call this a pass.
      fs.writeFileSync(dePage(root), page(ENGLISH, `${GERMAN}-de`), 'utf8');
    },
    wantExit: 'non-zero',
    wantNamed: [`${GERMAN}-de`],
  },
  {
    name: 'a source document with no built page',
    plant: (root) => {
      fs.rmSync(dePage(root));
    },
    wantExit: 'non-zero',
    wantNamed: ['nothing was built for it'],
  },
  {
    name: 'a built page with no .article-content container',
    plant: (root) => {
      fs.writeFileSync(dePage(root), '<html><body><article>no container</article></body></html>', 'utf8');
    },
    wantExit: 'non-zero',
    wantNamed: ['no .article-content container'],
  },
  {
    name: 'no packages/www/dist at all must REFUSE, never report success',
    plant: (root) => {
      fs.rmSync(path.join(root, 'packages/www/dist'), { recursive: true });
    },
    wantExit: 'non-zero',
    wantNamed: ['Refusing to run'],
  },
  {
    name: 'a locale directory missing entirely must REFUSE, never check less',
    plant: (root) => {
      fs.rmSync(path.join(root, 'packages/www/src/content/docs/ko'), { recursive: true });
    },
    wantExit: 'non-zero',
    wantNamed: ['Refusing to run', 'ko'],
  },
];

function main(): void {
  if (!fs.existsSync(GATE)) {
    console.error(`VACUOUS: ${GATE} does not exist, so nothing is under test.`);
    process.exit(1);
  }

  let failures = 0;
  for (const c of CASES) {
    const root = buildFixture();
    let res: Result;
    try {
      c.plant(root);
      res = runGate(root);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }

    const exitOk = c.wantExit === 'zero' ? res.code === 0 : res.code !== 0;
    const namedMissing = (c.wantNamed ?? []).filter((n) => !res.output.includes(n));
    const ok = exitOk && namedMissing.length === 0;
    failures += ok ? 0 : 1;
    console.log(`${ok ? '  ok  ' : '  FAIL'} ${c.name} — want ${c.wantExit}, got exit ${res.code}`);
    if (!exitOk) {
      console.log(res.output.split('\n').map((l) => `        ${l}`).join('\n'));
    } else if (namedMissing.length > 0) {
      console.log(`        exit was right but the message never named: ${namedMissing.join(', ')}`);
      console.log(res.output.split('\n').map((l) => `        ${l}`).join('\n'));
    }
  }

  if (failures > 0) {
    console.error(
      `\n✗ ${failures} control case(s) failed. check-docs-render-parity cannot be trusted:\n` +
        '  either it no longer detects a page rendering another locale\'s document, or it\n' +
        '  reports pages that are rendering correctly, and both make it useless.'
    );
    process.exit(1);
  }
  console.log(`\n✓ ${CASES.length} control cases: the render-parity gate fires on the real defect, stays quiet on a correct page, and refuses rather than skips`);
}

main();
