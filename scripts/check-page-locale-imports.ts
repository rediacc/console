#!/usr/bin/env tsx
/**
 * check:ci-page-locale-imports — a page may not reach into ONE locale's content.
 *
 * THE RULE. Nothing under `packages/www/src/pages/**` or `packages/www/src/layouts/**`
 * may import a MARKDOWN file via Vite's `?raw`, nor import anything under
 * `src/content/docs/en/`.
 *
 * WHY IT IS DECIDABLE AND NOT A STYLE OPINION. Every one of those routes is emitted
 * once per locale by `getStaticPaths`. A page that names a single content file by PATH
 * therefore serves that one language to all thirteen routes, by construction, before
 * anyone writes a line of logic. `packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro:9`
 * did exactly this for months:
 *
 *     import markdownSource from '../../../marp/rdc-cheat-sheet.marp.md?raw';
 *
 * and the German page served English prose while the German `.md` export beside it was
 * genuinely German. `?raw` needs a STATIC specifier, so there is no locale-keyed version
 * of that import; reaching for it is already the mistake.
 *
 * WHAT IT MUST NOT BREAK. `?raw` on a stylesheet or an SVG is a legitimate,
 * locale-independent pattern, and the same file used it two lines later
 * (`rdc-cheat-sheet.astro:13`, `styles/marp-cheatsheet.css?raw`). A rule that rejected
 * both would block the good pattern to stop the bad one, and would be worked around
 * rather than obeyed. The extension is what separates them, and the control asserts
 * both halves.
 *
 * ITS LIMIT, stated plainly. This is a PROXY. A page can still hardcode English inline,
 * or build a specifier at runtime, and this gate will not see it. That is
 * `check:ci-docs-render-parity`'s job, which reads the built HTML and needs a full
 * astro build to do it. This one is instant, needs no build, and names the mistake at
 * the exact point someone would make it again.
 *
 * Seams, for the control only: PAGE_LOCALE_IMPORTS_ROOT overrides the repo root.
 *
 * Run: npx tsx scripts/check-page-locale-imports.ts
 * Control: npx tsx scripts/__tests__/check-page-locale-imports.control.ts
 */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = process.env.PAGE_LOCALE_IMPORTS_ROOT ?? REPO;

/** Route-emitting surfaces. Every file here is rendered once per locale. */
const SCANNED_ROOTS = ['packages/www/src/pages', 'packages/www/src/layouts'];
const SCANNED_EXTS = new Set(['.astro', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']);
const MARKDOWN_EXTS = new Set(['.md', '.mdx', '.markdown']);

const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const NC = '\x1b[0m';

// ---------------------------------------------------------------------------
// Reading imports without being fooled by text that merely LOOKS like one
// ---------------------------------------------------------------------------

/**
 * Comments blanked, string bodies preserved.
 *
 * Not optional, and not hypothetical: `rdc-cheat-sheet.astro:7` is the comment
 *
 *     // Vite ?raw import embeds file content as a string literal at build time,
 *
 * sitting two lines above the real violation. A gate that reported the comment would
 * be reporting prose, and the first person to hit that false positive would (rightly)
 * stop believing the second, real finding underneath it.
 *
 * Comment bodies are replaced with spaces rather than removed so that every reported
 * line number still matches the file on disk.
 */
function blankComments(src: string): string {
  const out = src.split('');
  const blank = (from: number, to: number): void => {
    for (let k = from; k < to && k < out.length; k++) if (out[k] !== '\n') out[k] = ' ';
  };
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (c === '"' || c === "'" || c === '`') {
      i++;
      while (i < src.length && src[i] !== c) i += src[i] === '\\' ? 2 : 1;
      i++;
      continue;
    }
    if (c === '/' && next === '/') {
      const end = src.indexOf('\n', i);
      blank(i, end === -1 ? src.length : end);
      i = end === -1 ? src.length : end;
      continue;
    }
    if (c === '/' && next === '*') {
      const end = src.indexOf('*/', i + 2);
      const stop = end === -1 ? src.length : end + 2;
      blank(i, stop);
      i = stop;
      continue;
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i + 4);
      const stop = end === -1 ? src.length : end + 3;
      blank(i, stop);
      i = stop;
      continue;
    }
    i++;
  }
  return out.join('');
}

/** Module specifiers this file imports, each with its 1-based line. */
function importSpecifiers(src: string): Array<{ spec: string; line: number }> {
  const cleaned = blankComments(src);
  const patterns = [
    /\bimport\s+[^;'"()]*?\bfrom\s*['"]([^'"]+)['"]/g, // import X from '...'
    /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g, // await import('...')
    /\bimport\s*['"]([^'"]+)['"]/g, // side-effect import
    /\bexport\s+[^;'"()]*?\bfrom\s*['"]([^'"]+)['"]/g, // re-export
  ];
  const seen = new Set<string>();
  const out: Array<{ spec: string; line: number }> = [];
  for (const re of patterns) {
    let m: RegExpExecArray | null;
    while ((m = re.exec(cleaned)) !== null) {
      const spec = m[1] ?? '';
      const line = cleaned.slice(0, m.index).split('\n').length;
      const key = `${line}\0${spec}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ spec, line });
    }
  }
  return out.sort((a, b) => a.line - b.line);
}

// ---------------------------------------------------------------------------
// The rule, pure over its inputs so the control can drive it synthetically
// ---------------------------------------------------------------------------

interface Violation {
  file: string;
  line: number;
  spec: string;
  rule: 'markdown-raw' | 'english-content';
  why: string;
}

function classify(spec: string): Pick<Violation, 'rule' | 'why'> | null {
  const [pathPart = '', query = ''] = spec.split('?', 2);
  const ext = path.posix.extname(pathPart).toLowerCase();
  const isRaw = query.split('&').includes('raw');

  if (isRaw && MARKDOWN_EXTS.has(ext)) {
    return {
      rule: 'markdown-raw',
      why:
        'a `?raw` markdown import is a STATIC specifier, so this one document is rendered for ' +
        'every locale route this file emits. Read the localized document out of the `docs` ' +
        'content collection instead.',
    };
  }
  if (/(^|\/)content\/docs\/en(\/|$)/.test(pathPart)) {
    return {
      rule: 'english-content',
      why:
        'this names the ENGLISH copy of a translated document by path, so the twelve other ' +
        "locale routes render English. Select the entry for the route's own `lang`.",
    };
  }
  return null;
}

function scanFile(rel: string, src: string): Violation[] {
  const out: Violation[] = [];
  for (const { spec, line } of importSpecifiers(src)) {
    const verdict = classify(spec);
    if (verdict) out.push({ file: rel, line, spec, ...verdict });
  }
  return out;
}

// ---------------------------------------------------------------------------
// CONTROL. The instrument must fire, and must discriminate, before its green
// over the real tree means anything.
// ---------------------------------------------------------------------------

function control(): void {
  const fail = (why: string): never => {
    console.error(`${RED}CONTROL FAILED${NC}: ${why}`);
    console.error(
      '  The real scan did not run: a rule that cannot fire proves nothing by passing.'
    );
    process.exit(1);
  };
  const hits = (src: string): Violation[] => scanFile('control.astro', src);

  // The exact shape that shipped, and the legitimate one two lines below it.
  const real = hits(
    [
      '---',
      '// Vite ?raw import embeds file content as a string literal at build time,',
      '// so this deck is inlined rather than fetched.',
      "import markdownSource from '../../../marp/rdc-cheat-sheet.marp.md?raw';",
      "import themeCss from '../../../styles/marp-cheatsheet.css?raw';",
      '---',
    ].join('\n')
  );
  if (real.length !== 1) {
    fail(`expected exactly the markdown ?raw import to be reported, got ${JSON.stringify(real)}`);
  }
  if (real[0]?.line !== 4)
    fail(`the reported line was ${real[0]?.line}, not the markdown import's line 4`);
  if (real[0]?.rule !== 'markdown-raw') fail(`wrong rule: ${real[0]?.rule}`);

  // A comment is prose. Blanking it must not also break the line numbering above.
  if (hits('// import x from "./a.md?raw";\n').length !== 0)
    fail('a COMMENTED-OUT import was reported');

  // The English-content half.
  if (hits("import d from '../../content/docs/en/rdc-cheat-sheet.md';\n").length !== 1) {
    fail('an import of src/content/docs/en/ was NOT reported');
  }
  // ...and its discriminating twin: the collection itself is not the English copy.
  if (hits("import { getCollection } from 'astro:content';\n").length !== 0) {
    fail('an ordinary import was reported');
  }
  if (hits("import d from '../../content/docs/de/rdc-cheat-sheet.md';\n").length !== 0) {
    fail(
      'a non-English locale path was reported; the rule is about hardcoding EN, not about content imports'
    );
  }

  console.log('  control  reports a `?raw` markdown import, at its real line');
  console.log('  control  allows the `?raw` CSS import two lines below it');
  console.log('  control  ignores a commented-out import');
  console.log('  control  reports an import of src/content/docs/en/, and only that locale');
}

// ---------------------------------------------------------------------------
// Disk inputs
// ---------------------------------------------------------------------------

function walk(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir).sort()) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (SCANNED_EXTS.has(path.extname(entry).toLowerCase())) acc.push(full);
  }
  return acc;
}

function main(): void {
  control();

  const refuse = (why: string, how: string): never => {
    console.error(`${RED}✗${NC} Refusing to run: ${why}`);
    console.error(`  ${how}`);
    process.exit(1);
  };

  const files: string[] = [];
  for (const rel of SCANNED_ROOTS) {
    const dir = path.join(ROOT, rel);
    if (!existsSync(dir))
      refuse(`${rel} does not exist.`, 'A renamed route root leaves this gate scanning nothing.');
    walk(dir, files);
  }
  if (files.length === 0) {
    refuse(
      `${SCANNED_ROOTS.join(' and ')} hold no scannable files.`,
      'The walk is blind; every assertion below would pass while checking nothing.'
    );
  }

  const violations: Violation[] = [];
  for (const file of files) {
    violations.push(...scanFile(path.relative(ROOT, file), readFileSync(file, 'utf8')));
  }

  console.log('');
  console.log('Page locale imports');
  console.log('='.repeat(60));
  console.log(`${files.length} file(s) under ${SCANNED_ROOTS.join(', ')}.`);
  console.log('');

  if (violations.length === 0) {
    console.log(`${GREEN}✓${NC} no page or layout reaches into a single locale's content by path.`);
    return;
  }

  for (const v of violations) {
    console.error(`${RED}✗${NC} ${v.file}:${v.line}  ${v.spec}`);
    console.error(`    ${v.why}`);
  }
  console.error('');
  console.error(
    `${RED}✗${NC} ${violations.length} fixed-locale content import(s) in route-emitting files.\n` +
      '  Every one of these files is built once per locale, so naming one content file by path\n' +
      '  serves that language to all thirteen routes while every source-rooted i18n gate stays green.'
  );
  process.exit(1);
}

main();
