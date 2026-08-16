#!/usr/bin/env tsx
/**
 * check:ci-docs-render-parity — a docs page must RENDER its own locale's document.
 *
 * THE CLASS THIS CATCHES. `packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro:9`
 * imports ONE English Marp deck with `?raw` and renders it for all 13 locale routes,
 * while the translated `src/content/docs/<lang>/rdc-cheat-sheet.md` reaches only the
 * `.md`/`.txt` exports. A German reader is served English prose at a German URL, and
 * the German export beside it is genuinely German. Every existing i18n gate stayed
 * green for months, because every one of them roots at `src/content/docs` and NONE of
 * them reads built HTML: freshness compares a `sourceHash`, cross-locale compares
 * contamination, structure-parity compares shapes. None of them can see a renderer
 * that ignores the file they all agree about.
 *
 * So this gate reads the artifact a human is served, and asserts it against the source
 * the other gates police. It is the only gate in the repo that closes that loop.
 *
 * WHAT IT ASSERTS, mechanically and without heuristics. For every site locale L and
 * every docs slug S where `packages/www/src/content/docs/L/S.md` exists:
 *
 *   1. Parse the `^## ` headings out of the source markdown (fenced code excluded).
 *   2. Read `packages/www/dist/L/docs/S/index.html` and extract the ARTICLE BODY --
 *      the `<div class="article-content">` DocsLayout.astro:173 emits directly around
 *      `<slot />`, matched by balanced `<div>` depth.
 *   3. Assert every source heading's text appears in that body.
 *
 * SCOPING TO THE ARTICLE BODY IS LOAD-BEARING, not tidiness. Today's German
 * `dist/de/docs/rdc-cheat-sheet/index.html` carries the ENGLISH heading text in its
 * table of contents, because the TOC is generated from the rendered English body. A
 * whole-page assertion would be satisfied by that TOC and report success on the exact
 * bug this gate exists for.
 *
 * NORMALISATION, and its limits. Headings are compared as plain text after: markdown
 * inline syntax removed (backticks, emphasis, link targets), HTML tags stripped, HTML
 * entities decoded, typographic substitutions (curly quotes, dashes, ellipsis) folded
 * back to ASCII, whitespace collapsed. Those foldings all describe the RENDERER's own
 * transformations of one string; none of them makes two different strings compare
 * equal. Headings carrying an unresolved `{{t:...}}` inline-translation placeholder are
 * skipped, because their rendered text is by design not their source text.
 *
 * IT REFUSES RATHER THAN SKIPS. Without `packages/www/dist` there is nothing to read,
 * and a gate that returns 0 in that state reports "checked, fine" for "did not run" --
 * the failure mode that let check:ci-seo's built-HTML scan sit vacuous locally for its
 * whole life. Build www first (the manifest declares `needs: ['build:www']`).
 *
 * Seams, for the control only: DOCS_RENDER_PARITY_ROOT overrides the repo root.
 *
 * Run: npx tsx scripts/check-docs-render-parity.ts
 * Control: npx tsx scripts/__tests__/check-docs-render-parity.control.ts
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SITE_LOCALES } from '@rediacc/locales';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = process.env.DOCS_RENDER_PARITY_ROOT ?? REPO;
const SRC_DIR = path.join(ROOT, 'packages/www/src/content/docs');
const DIST_DIR = path.join(ROOT, 'packages/www/dist');

const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const YELLOW = '\x1b[0;33m';
const NC = '\x1b[0m';

// ---------------------------------------------------------------------------
// Source side: the `## ` headings a locale document declares
// ---------------------------------------------------------------------------

/** Frontmatter and fenced code are not prose; a `## ` inside either is not a heading. */
function bodyOfMarkdown(text: string): string {
  const withoutFrontmatter = text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '');
  return withoutFrontmatter.replace(/^([ \t]*)(```|~~~)[^\n]*\n[\s\S]*?\n\1\2[^\n]*$/gm, '');
}

/**
 * Markdown inline syntax removed, leaving the text a renderer would emit.
 *
 * Underscores are deliberately NOT treated as emphasis: heading text in this repo
 * carries identifiers like `REDIACC_ALLOW_CONFIG_EDIT`, and stripping `_` would
 * mangle the very string the assertion compares.
 */
function plainFromMarkdown(heading: string): string {
  return normalizeText(
    heading
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/`+/g, '')
      .replace(/\*+/g, '')
  );
}

/** `## ` headings, in document order, with their 1-based source line. */
function sourceHeadings(text: string): Array<{ text: string; raw: string }> {
  const out: Array<{ text: string; raw: string }> = [];
  for (const line of bodyOfMarkdown(text).split('\n')) {
    const m = /^##[ \t]+(.+?)[ \t]*#*[ \t]*$/.exec(line);
    if (!m) continue;
    const raw = m[1] ?? '';
    // `{{t:...}}` is an inline-translation placeholder resolved at build time, so the
    // rendered text is by design not the source text. Comparing them would report a
    // failure for a feature working correctly.
    if (raw.includes('{{')) continue;
    const plain = plainFromMarkdown(raw);
    if (plain.length === 0) continue;
    out.push({ text: plain, raw });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Built side: the article body a reader is served
// ---------------------------------------------------------------------------

const ARTICLE_OPEN = /<div\b[^>]*\bclass="[^"]*\barticle-content\b[^"]*"[^>]*>/;

/**
 * The innermost wrapper around DocsLayout's `<slot />`, by balanced `<div>` depth.
 *
 * Returns null when the container is absent, which is a finding rather than a pass:
 * a page with no article body renders none of its document.
 */
function articleBody(html: string): string | null {
  const open = ARTICLE_OPEN.exec(html);
  if (!open) return null;
  let i = open.index + open[0].length;
  const start = i;
  let depth = 1;
  const tag = /<(\/?)div\b/g;
  tag.lastIndex = i;
  let m: RegExpExecArray | null;
  while ((m = tag.exec(html)) !== null) {
    depth += m[1] === '/' ? -1 : 1;
    if (depth === 0) return html.slice(start, m.index);
    i = tag.lastIndex;
  }
  // Unbalanced markup: return what is left rather than nothing, so the failure is
  // reported as a missing heading with real text rather than as an empty body.
  return html.slice(start);
}

const ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
  hellip: '...',
  mdash: '-',
  ndash: '-',
  rsquo: "'",
  lsquo: "'",
  ldquo: '"',
  rdquo: '"',
};

function decodeEntities(s: string): string {
  return s.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (whole, body: string) => {
    if (body.startsWith('#')) {
      const code = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : whole;
    }
    return ENTITIES[body.toLowerCase()] ?? whole;
  });
}

/**
 * Typographic folding, and why it is not fuzziness. The markdown pipeline rewrites
 * `'` to `’`, `"` to `“`/`”`, `--` to `–` and `...` to `…` while rendering. Those are
 * the RENDERER's transformations of a single string, so folding them back compares the
 * same string to itself. No two distinct headings are made equal by it.
 */
function normalizeText(s: string): string {
  return s
    .replace(/[‘’‚‛′]/g, "'")
    .replace(/[“”„‟″]/g, '"')
    .replace(/[–—−]/g, '-')
    .replace(/…/g, '...')
    .replace(/[\u00a0\u202f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Phrasing elements, which a browser renders WITHOUT a word break around them.
 *
 * This distinction is not cosmetic. `## Cold Snapshots (\`--cold\`)` renders as
 * `Cold Snapshots (<code>--cold</code>)`, and replacing every tag with a space turns
 * that into `Cold Snapshots ( --cold )` -- a mismatch against a page that is rendering
 * perfectly. Fourteen such false positives came out of the first run over the real
 * dist, one per locale, and a gate that cries wolf on correct pages is a gate somebody
 * switches off.
 *
 * An UNKNOWN element falls through to the space branch on purpose. That direction
 * fails loudly (a heading reported missing, which a human then reads) rather than
 * silently joining two unrelated strings into an accidental match.
 */
const INLINE_TAGS = new Set([
  'a', 'abbr', 'b', 'bdi', 'bdo', 'cite', 'code', 'data', 'del', 'dfn', 'em', 'i',
  'ins', 'kbd', 'mark', 'q', 'rp', 'rt', 'ruby', 's', 'samp', 'small', 'span',
  'strong', 'sub', 'sup', 'time', 'u', 'var', 'wbr',
]);

/** The visible text of an HTML fragment, with script/style content discarded. */
function visibleText(html: string): string {
  return normalizeText(
    decodeEntities(
      html
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
        .replace(/<!--[\s\S]*?-->/g, ' ')
        .replace(/<\/?([a-zA-Z][\w-]*)\b[^>]*>/g, (_whole, tag: string) =>
          INLINE_TAGS.has(tag.toLowerCase()) ? '' : ' '
        )
        .replace(/<[^>]+>/g, ' ')
    )
  );
}

// ---------------------------------------------------------------------------
// The analysis, pure over its inputs so the control can drive it synthetically
// ---------------------------------------------------------------------------

interface Pair {
  locale: string;
  slug: string;
  /** repo-relative, for the message */
  sourceFile: string;
  distFile: string;
  markdown: string;
  /** null when the built page is absent */
  html: string | null;
}

interface Finding {
  locale: string;
  slug: string;
  sourceFile: string;
  distFile: string;
  reason: string;
  missing: string[];
}

function analyze(pairs: readonly Pair[]): Finding[] {
  const out: Finding[] = [];
  for (const p of pairs) {
    const headings = sourceHeadings(p.markdown);
    if (headings.length === 0) continue;
    if (p.html === null) {
      out.push({
        locale: p.locale,
        slug: p.slug,
        sourceFile: p.sourceFile,
        distFile: p.distFile,
        reason: 'the source document exists but nothing was built for it',
        missing: [],
      });
      continue;
    }
    const body = articleBody(p.html);
    if (body === null) {
      out.push({
        locale: p.locale,
        slug: p.slug,
        sourceFile: p.sourceFile,
        distFile: p.distFile,
        reason: 'the built page has no .article-content container, so it renders no document body',
        missing: [],
      });
      continue;
    }
    const text = visibleText(body);
    const missing = headings.filter((h) => !text.includes(h.text)).map((h) => h.raw);
    if (missing.length > 0) {
      out.push({
        locale: p.locale,
        slug: p.slug,
        sourceFile: p.sourceFile,
        distFile: p.distFile,
        reason: `${missing.length} of ${headings.length} source heading(s) are absent from the rendered article body`,
        missing,
      });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// CONTROL. Prove the instrument can fire, and that it discriminates, before
// trusting a green over the real tree.
// ---------------------------------------------------------------------------

function control(): void {
  const mk = (markdown: string, html: string | null): Pair => ({
    locale: 'de',
    slug: 'control',
    sourceFile: 'control/de.md',
    distFile: 'control/de.html',
    markdown,
    html,
  });
  const wrap = (inner: string): string =>
    `<html><body><nav class="toc">Repository Lifecycle</nav><article><div class="article-content" data-astro-cid-x>${inner}</div></article></body></html>`;

  const fail = (why: string): never => {
    console.error(`${RED}CONTROL FAILED${NC}: ${why}`);
    console.error('  The real scan did not run: a gate whose control cannot fire proves nothing by passing.');
    process.exit(1);
  };

  // 1. The planted defect: a German source rendered as English.
  const red = analyze([mk('## Repository-Lebenszyklus\n', wrap('<h2>Repository Lifecycle</h2>'))]);
  if (red.length !== 1 || !red[0]?.missing.includes('Repository-Lebenszyklus')) {
    fail('a German heading absent from the rendered body was NOT reported');
  }
  // 2. Discrimination: the matching case must be silent, or the gate is a tripwire
  //    that fires on everything and would be disabled within a week.
  if (analyze([mk('## Repository-Lebenszyklus\n', wrap('<h2>Repository-Lebenszyklus</h2>'))]).length !== 0) {
    fail('a correctly rendered heading was reported as missing');
  }
  // 3. Scoping: the English TOC outside .article-content must not satisfy the
  //    assertion. This is the one way this gate could be green while wrong.
  const scoped = analyze([
    mk(
      '## Repository-Lebenszyklus\n',
      '<nav class="toc"><a>Repository-Lebenszyklus</a></nav><div class="article-content"><h2>Repository Lifecycle</h2></div>'
    ),
  ]);
  if (scoped.length !== 1) fail('chrome outside .article-content satisfied the assertion');

  console.log('  control  reports a locale heading missing from the rendered body');
  console.log('  control  stays silent when the body carries the heading');
  console.log('  control  ignores matching text outside .article-content');
}

// ---------------------------------------------------------------------------
// Disk inputs
// ---------------------------------------------------------------------------

function collectPairs(): Pair[] {
  const pairs: Pair[] = [];
  for (const locale of SITE_LOCALES) {
    const dir = path.join(SRC_DIR, locale);
    if (!existsSync(dir)) continue;
    for (const entry of readdirSync(dir).sort()) {
      if (!entry.endsWith('.md')) continue;
      const slug = entry.slice(0, -'.md'.length);
      const sourceFile = path.join(dir, entry);
      const distFile = path.join(DIST_DIR, locale, 'docs', slug, 'index.html');
      pairs.push({
        locale,
        slug,
        sourceFile: path.relative(ROOT, sourceFile),
        distFile: path.relative(ROOT, distFile),
        markdown: readFileSync(sourceFile, 'utf8'),
        html: existsSync(distFile) ? readFileSync(distFile, 'utf8') : null,
      });
    }
  }
  return pairs;
}

function main(): void {
  control();

  const refuse = (why: string, how: string): never => {
    console.error(`${RED}✗${NC} Refusing to run: ${why}`);
    console.error(`  ${how}`);
    process.exit(1);
  };

  if (!existsSync(SRC_DIR)) refuse(`no docs collection at ${path.relative(ROOT, SRC_DIR)}.`, 'Nothing to compare.');
  if (!existsSync(DIST_DIR)) {
    refuse(
      `no built site at ${path.relative(ROOT, DIST_DIR)}, so there is no rendered page to read.`,
      'Run `npm run build:www` first. This gate does NOT self-skip: reporting success for "did not run" is the exact vacuity it exists to catch.'
    );
  }

  const pairs = collectPairs();
  if (pairs.length === 0) refuse('zero locale documents found.', 'The scan is blind; fix the paths rather than trusting this green.');

  const localesSeen = new Set(pairs.map((p) => p.locale));
  const missingLocales = SITE_LOCALES.filter((l) => !localesSeen.has(l));
  if (missingLocales.length > 0) {
    refuse(
      `no documents found for ${missingLocales.join(', ')}, so those locales are unchecked.`,
      `The locale universe is @rediacc/locales (${SITE_LOCALES.length} codes); a missing directory is a content bug, not a reason to check less.`
    );
  }

  const withHeadings = pairs.filter((p) => sourceHeadings(p.markdown).length > 0);
  if (withHeadings.length === 0) {
    refuse('no source document yielded a single `## ` heading.', 'The heading parser broke; every assertion below would pass while checking nothing.');
  }

  const findings = analyze(pairs);

  console.log('');
  console.log('Docs render parity');
  console.log('='.repeat(60));
  console.log(
    `${pairs.length} locale document(s) across ${localesSeen.size} locale(s); ` +
      `${withHeadings.length} carry \`## \` headings and were compared against their built page.`
  );
  console.log('');

  if (findings.length === 0) {
    console.log(`${GREEN}✓${NC} every locale's rendered page carries that locale's own headings.`);
    return;
  }

  for (const f of findings) {
    console.error(`${RED}✗${NC} ${f.locale}/${f.slug}: ${f.reason}`);
    console.error(`    source: ${f.sourceFile}`);
    console.error(`    built:  ${f.distFile}`);
    for (const m of f.missing) console.error(`    ${YELLOW}missing heading${NC}: ## ${m}`);
  }
  console.error('');
  console.error(
    `${RED}✗${NC} ${findings.length} page(s) render something other than their own locale's document.\n` +
      "  A page that ignores its locale file serves one language to thirteen routes, and every\n" +
      '  source-rooted i18n gate stays green while it does.'
  );
  process.exit(1);
}

main();
