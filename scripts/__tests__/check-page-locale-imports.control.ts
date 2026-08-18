#!/usr/bin/env node

/**
 * Control harness for check-page-locale-imports.ts.
 *
 * WHY BOTH HALVES ARE MANDATORY. The file this gate was written for held the bad
 * pattern and the legitimate one FOUR LINES APART:
 *
 *     packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro
 *       7:  // Vite ?raw import embeds file content as a string literal at build time,
 *       9:  import markdownSource from '../../../marp/rdc-cheat-sheet.marp.md?raw';
 *      13:  import themeCss from '../../../styles/marp-cheatsheet.css?raw';
 *
 * Line 9 is the defect: one English document rendered for thirteen locale routes.
 * Line 13 is fine forever: a stylesheet has no language. Line 7 is prose. A rule that
 * rejects all three is too blunt to keep, and a rule that accepts all three is the
 * status quo that shipped the bug, so the only useful assertion is that the gate
 * separates them — which is what the first case below asserts, on that exact text.
 *
 * (Those three lines are reproduced verbatim from the file as it stood at 0815-1. The
 * page itself is being deleted by the fix; the control must keep proving the rule after
 * the file is gone, so the shape lives here rather than being read off the tree. To
 * re-derive it:
 *   git log --diff-filter=D -1 --format=%H -- 'packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro'
 *   git show <that-sha>^:'packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro' | sed -n '7p;9p;13p')
 *
 * Run: npx tsx scripts/__tests__/check-page-locale-imports.control.ts
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(__dirname, '../..');
const GATE = path.join(REPO, 'scripts/check-page-locale-imports.ts');

/** Verbatim from rdc-cheat-sheet.astro as it stood before the fix; see the header. */
const CHEAT_SHEET_ASTRO = [
  '---',
  "import DocsLayout from '../../../layouts/DocsLayout.astro';",
  "import { LANGUAGES } from '../../../i18n/types';",
  '',
  '// Marp renders the deck to HTML at build time.',
  '',
  '// Vite ?raw import embeds file content as a string literal at build time,',
  '// so the deck ships inlined rather than fetched.',
  "import markdownSource from '../../../marp/rdc-cheat-sheet.marp.md?raw';",
  '',
  "// The theme is injected with set:html to escape Marp's scoping.",
  '',
  "import themeCss from '../../../styles/marp-cheatsheet.css?raw';",
  '---',
  '',
  '<DocsLayout><div set:html={themeCss} /></DocsLayout>',
].join('\n');

interface Result {
  code: number;
  output: string;
}

function runGate(root: string): Result {
  try {
    const out = execFileSync('npx', ['tsx', GATE], {
      cwd: REPO,
      encoding: 'utf8',
      env: { ...process.env, PAGE_LOCALE_IMPORTS_ROOT: root },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { code: 0, output: out };
  } catch (err) {
    const e = err as { status?: number; stdout?: string; stderr?: string };
    return { code: e.status ?? 1, output: `${e.stdout ?? ''}${e.stderr ?? ''}` };
  }
}

/** A fixture tree holding one file per entry, relative to packages/www/src. */
function fixture(files: Record<string, string>): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'page-locale-imports-'));
  // Both scanned roots always exist, so a case tests the RULE and never trips the
  // gate's missing-root refusal by accident.
  for (const rel of ['pages', 'layouts']) {
    fs.mkdirSync(path.join(root, 'packages/www/src', rel), { recursive: true });
  }
  for (const [rel, body] of Object.entries(files)) {
    const full = path.join(root, 'packages/www/src', rel);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body, 'utf8');
  }
  return root;
}

interface Case {
  name: string;
  files: Record<string, string>;
  wantExit: 'zero' | 'non-zero';
  /** Substrings the output must contain. */
  wantNamed?: string[];
  /** Substrings the output must NOT contain. */
  wantAbsent?: string[];
}

const CASES: Case[] = [
  {
    name: 'the real file: line 9 rejected, line 13 allowed, line 7 ignored',
    files: { 'pages/[lang]/docs/rdc-cheat-sheet.astro': CHEAT_SHEET_ASTRO },
    wantExit: 'non-zero',
    wantNamed: ['rdc-cheat-sheet.astro:9', 'rdc-cheat-sheet.marp.md?raw'],
    // The CSS `?raw` and the comment are the two halves a blunt rule would swallow.
    wantAbsent: ['rdc-cheat-sheet.astro:13', 'rdc-cheat-sheet.astro:7', 'marp-cheatsheet.css'],
  },
  {
    name: 'a page with only a CSS ?raw import is clean',
    files: { 'pages/x.astro': "---\nimport css from '../styles/a.css?raw';\n---\n" },
    wantExit: 'zero',
  },
  {
    name: 'an SVG ?raw import is clean too (no language in an icon)',
    files: { 'pages/x.astro': "---\nimport icon from '../assets/a.svg?raw';\n---\n" },
    wantExit: 'zero',
  },
  {
    name: 'a layout is scanned, not just a page',
    files: {
      'layouts/L.astro': "---\nimport md from '../content/docs/en/quick-start.md?raw';\n---\n",
    },
    wantExit: 'non-zero',
    wantNamed: ['layouts/L.astro:2'],
  },
  {
    name: 'importing src/content/docs/en/ without ?raw is still hardcoding English',
    files: {
      'pages/x.astro': "---\nimport d from '../content/docs/en/rdc-cheat-sheet.md';\n---\n",
    },
    wantExit: 'non-zero',
    wantNamed: ['content/docs/en/rdc-cheat-sheet.md', 'ENGLISH copy'],
  },
  {
    name: 'a dynamic import of the English copy is caught as well',
    files: {
      'pages/x.astro': "---\nconst d = await import('../content/docs/en/tools.md');\n---\n",
    },
    wantExit: 'non-zero',
    wantNamed: ['content/docs/en/tools.md'],
  },
  {
    name: 'a commented-out markdown ?raw import is prose, not an import',
    files: {
      'pages/x.astro':
        "---\n// import md from '../content/docs/en/a.md?raw';\n/* import b from './b.md?raw'; */\n---\n<!-- import c from './c.md?raw'; -->\n",
    },
    wantExit: 'zero',
  },
  {
    name: 'the same bad import OUTSIDE pages/ and layouts/ is out of scope',
    files: {
      'pages/x.astro': "---\nimport ok from '../utils/a.ts';\n---\n",
      'utils/marp.ts': "import md from '../content/docs/en/a.md?raw';\n",
    },
    wantExit: 'zero',
  },
  {
    name: 'ordinary imports, including a non-English locale path, are clean',
    files: {
      'pages/x.astro':
        "---\nimport { getCollection } from 'astro:content';\nimport de from '../content/docs/de/a.md';\nimport L from '../layouts/DocsLayout.astro';\n---\n",
    },
    wantExit: 'zero',
  },
];

function main(): void {
  if (!fs.existsSync(GATE)) {
    console.error(`VACUOUS: ${GATE} does not exist, so nothing is under test.`);
    process.exit(1);
  }

  let failures = 0;
  for (const c of CASES) {
    const root = fixture(c.files);
    let res: Result;
    try {
      res = runGate(root);
    } finally {
      fs.rmSync(root, { recursive: true, force: true });
    }
    const exitOk = c.wantExit === 'zero' ? res.code === 0 : res.code !== 0;
    const missing = (c.wantNamed ?? []).filter((n) => !res.output.includes(n));
    const present = (c.wantAbsent ?? []).filter((n) => res.output.includes(n));
    const ok = exitOk && missing.length === 0 && present.length === 0;
    failures += ok ? 0 : 1;
    console.log(`${ok ? '  ok  ' : '  FAIL'} ${c.name} — want ${c.wantExit}, got exit ${res.code}`);
    if (!ok) {
      if (missing.length > 0) console.log(`        never named: ${missing.join(', ')}`);
      if (present.length > 0) console.log(`        wrongly named: ${present.join(', ')}`);
      console.log(
        res.output
          .split('\n')
          .map((l) => `        ${l}`)
          .join('\n')
      );
    }
  }

  // Anti-vacuity: the gate must refuse when its scan roots are gone, rather than
  // reporting a clean tree it never looked at.
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), 'page-locale-imports-empty-'));
  const emptyRes = runGate(empty);
  fs.rmSync(empty, { recursive: true, force: true });
  const emptyOk = emptyRes.code !== 0 && emptyRes.output.includes('Refusing to run');
  failures += emptyOk ? 0 : 1;
  console.log(
    `${emptyOk ? '  ok  ' : '  FAIL'} a missing pages/ root REFUSES rather than reporting a clean scan`
  );

  if (failures > 0) {
    console.error(
      `\n✗ ${failures} control case(s) failed. check-page-locale-imports cannot be trusted:\n` +
        "  either it no longer catches a page pinned to one locale's content, or it now rejects\n" +
        '  the locale-independent `?raw` imports that sat four lines from the real defect.'
    );
    process.exit(1);
  }
  console.log(
    `\n✓ ${CASES.length + 1} control cases: the rule separates a markdown ?raw import from a CSS one, a comment and an out-of-scope file`
  );
}

main();
