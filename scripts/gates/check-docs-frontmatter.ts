#!/usr/bin/env tsx
/**
 * check:ci-docs-frontmatter -- every content entry's front matter, validated with the
 * content collection schema the site really builds with.
 *
 * WHY IT EXISTS. `packages/www/src/content/docs/ru/backup-destinations.md` wrote its tags
 * list with en dashes (U+2013) as its list markers. An en dash is not a YAML sequence
 * indicator, so the parser read `tags` as ONE plain string, `check:i18n` and every other local gate passed,
 * and only the Astro content loader refused it: the docs dev server would not start (fixed
 * in 10eae6293b). The hand-mirrored field lists in `packages/www/scripts/validate-content.js`
 * check presence, never type, which is how a string where a list belongs went through.
 *
 * THE SAME SCHEMA, NOT A COPY OF IT. This imports `packages/www/src/content.config.ts`
 * itself. Its only Astro-runtime import is the virtual module `astro:content`, whose
 * `defineCollection` is the identity on its argument; a synchronous resolve hook stands it
 * in for exactly that, so `collections.<name>.schema` is the real zod object, superRefine
 * included. The front matter is parsed with `@astrojs/internal-helpers/frontmatter`, the
 * parser Astro's markdown and MDX entry types call, so a YAML quirk reads here the way it
 * reads in the loader. A second, hand-written schema would drift from the first the day a
 * field is added; this one cannot.
 *
 * BOTH COLLECTIONS. The defect class is "front matter the loader refuses", which the blog
 * collection shares, so the gate validates every collection `content.config.ts` exports
 * and FAILS on a collection it has no directory for, rather than skipping it.
 *
 * ANTI-VACUITY. A collection below its floor, a locale directory with zero entries, a
 * schema that cannot be imported, or a missing parser is a failure with the reason, never
 * a pass. The success line prints the counts per collection and per locale.
 *
 * SEAM. `DOCS_FRONTMATTER_CONTENT_DIR` points the scan at a scratch content root (the
 * control at scripts/__tests__/check-docs-frontmatter.control.ts uses it); the schema is
 * always the real one.
 *
 * ---- gate ----
 * step: Docs front matter matches the content schema
 * needs: node
 * selftest: true
 * lane: quality-content
 * ---- end gate ----
 */

import fs from 'node:fs';
import { createRequire, registerHooks } from 'node:module';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const CONFIG = path.join(REPO, 'packages/www/src/content.config.ts');
const DEFAULT_CONTENT = path.join(REPO, 'packages/www/src/content');

/**
 * Collection name -> directory under the content root, with a floor. The loaders in
 * content.config.ts use `base: './src/content/<name>'` and `**\/*.{md,mdx}`. The floors
 * sit well under the measured corpus (1,054 docs, 92 blog posts on 2026-11-07): they are a
 * "the walk collapsed" tripwire, not a claim the corpus never shrinks.
 */
export const COLLECTIONS: Record<string, { dir: string; floor: number }> = {
  docs: { dir: 'docs', floor: 500 },
  blog: { dir: 'blog', floor: 40 },
};

interface SafeParseIssue {
  path: readonly PropertyKey[];
  message: string;
}
export interface Schema {
  safeParse(data: unknown): { success: boolean; error?: { issues: SafeParseIssue[] } };
}
type ParseFrontmatter = (code: string) => { frontmatter: Record<string, unknown> };

export interface Finding {
  file: string;
  message: string;
}

/** Every entry the collection's glob loader would load: `**\/*.{md,mdx}` under `dir`. */
export const listEntries = (dir: string): string[] => {
  if (!fs.existsSync(dir)) return [];
  return (fs.readdirSync(dir, { recursive: true, withFileTypes: true }) as fs.Dirent[])
    .filter((d) => d.isFile() && /\.mdx?$/.test(d.name))
    .map((d) => path.join(d.parentPath, d.name))
    .sort((a, b) => a.localeCompare(b));
};

const DASHES = /^\s*[\u2010-\u2015\u2212]\s/m;

/** A targeted hint for the shape that motivated the gate: a list written with a non-ASCII dash. */
const hintFor = (key: string, raw: string, value: unknown): string => {
  if (typeof value !== 'string') return '';
  const block = new RegExp(`^${key}:[^\\n]*\\n((?:[ \\t]+[^\\n]*\\n?)*)`, 'm').exec(raw)?.[1];
  if (block && DASHES.test(block)) {
    return ` (the list items under '${key}:' start with a typographic dash, which YAML does not read as a list marker; use an ASCII '-')`;
  }
  return '';
};

/**
 * Validate one entry's source text. Returns the findings as messages, empty when the
 * loader would accept it. Exported for the selftest.
 */
export const validateSource = (code: string, schema: Schema, parse: ParseFrontmatter): string[] => {
  let fm: Record<string, unknown>;
  try {
    fm = parse(code).frontmatter;
  } catch (e) {
    return [`front matter is not valid YAML: ${(e as Error).message.split('\n')[0]}`];
  }
  try {
    JSON.stringify(fm);
  } catch {
    return ['front matter is not JSON-serialisable, which the content loader refuses'];
  }
  const res = schema.safeParse(fm);
  if (res.success) return [];
  const raw = /^\uFEFF?\s*---\n([\s\S]*?\n)---/.exec(code)?.[1] ?? '';
  return (res.error?.issues ?? []).map((i) => {
    const key = i.path.map(String).join('.') || '(root)';
    const top = String(i.path[0] ?? '');
    return `${key}: ${i.message}${top ? hintFor(top, raw, fm[top]) : ''}`;
  });
};

/** Stand in for Astro's virtual `astro:content` so content.config.ts imports under plain tsx. */
let hooked = false;
const hookAstroContent = (): void => {
  if (hooked) return;
  if (typeof registerHooks !== 'function') {
    throw new Error(
      `node:module registerHooks is unavailable on Node ${process.version}; the toolchain pin in .devcontainer/toolchain.env is the supported Node`
    );
  }
  registerHooks({
    resolve(spec, ctx, next) {
      if (spec === 'astro:content') {
        return {
          url: 'data:text/javascript,export const defineCollection = (c) => c;',
          shortCircuit: true,
        };
      }
      return next(spec, ctx);
    },
  });
  hooked = true;
};

export const loadSchemas = async (): Promise<Record<string, Schema>> => {
  hookAstroContent();
  const mod = (await import(pathToFileURL(CONFIG).href)) as {
    collections?: Record<string, { schema?: Schema }>;
  };
  const out: Record<string, Schema> = {};
  for (const [name, c] of Object.entries(mod.collections ?? {})) {
    if (typeof c?.schema?.safeParse !== 'function') {
      throw new Error(`collection '${name}' in content.config.ts carries no zod schema`);
    }
    out[name] = c.schema;
  }
  return out;
};

/**
 * Resolved THROUGH the `astro` that packages/www depends on, not from the repo root: the
 * parser is astro's own dependency, so this is the copy its loader calls even if hoisting
 * changes, and a root-level import would silently pick up whatever copy floated up.
 */
export const loadParser = async (): Promise<ParseFrontmatter> => {
  const www = createRequire(path.join(REPO, 'packages/www/package.json'));
  const astro = createRequire(www.resolve('astro/package.json'));
  const entry = astro.resolve('@astrojs/internal-helpers/frontmatter');
  const m = (await import(pathToFileURL(entry).href)) as {
    parseFrontmatter?: ParseFrontmatter;
  };
  if (typeof m.parseFrontmatter !== 'function') {
    throw new Error('@astrojs/internal-helpers/frontmatter exports no parseFrontmatter');
  }
  return m.parseFrontmatter;
};

export interface ScanResult {
  findings: Finding[];
  problems: string[];
  shape: string[];
}

/** Walk every collection under `contentRoot` and validate each entry. */
export const scan = (
  contentRoot: string,
  schemas: Record<string, Schema>,
  parse: ParseFrontmatter
): ScanResult => {
  const findings: Finding[] = [];
  const problems: string[] = [];
  const shape: string[] = [];
  const known = Object.keys(COLLECTIONS)
    .sort((a, b) => a.localeCompare(b))
    .join(',');
  const exported = Object.keys(schemas)
    .sort((a, b) => a.localeCompare(b))
    .join(',');
  if (known !== exported) {
    problems.push(
      `content.config.ts exports collections [${exported}] but this gate maps [${known}]; add the new collection's directory and floor to COLLECTIONS in scripts/gates/check-docs-frontmatter.ts`
    );
  }
  for (const [name, schema] of Object.entries(schemas)) {
    const spec = COLLECTIONS[name];
    if (!spec) continue;
    const dir = path.join(contentRoot, spec.dir);
    const files = listEntries(dir);
    if (files.length < spec.floor) {
      problems.push(
        `collection '${name}': found ${files.length} entr(ies) under ${dir}, below the floor of ${spec.floor}; the gate is not seeing the tree, so its green would mean nothing`
      );
    }
    const perLocale = new Map<string, number>();
    for (const f of files) {
      const top = path.relative(dir, f).split(path.sep)[0] ?? '';
      perLocale.set(top, (perLocale.get(top) ?? 0) + 1);
      for (const message of validateSource(fs.readFileSync(f, 'utf8'), schema, parse)) {
        findings.push({ file: f, message });
      }
    }
    if (fs.existsSync(dir)) {
      for (const d of fs.readdirSync(dir, { withFileTypes: true })) {
        if (d.isDirectory() && !perLocale.has(d.name)) {
          problems.push(`collection '${name}': locale directory '${d.name}' holds zero entries`);
        }
      }
    }
    const locales = [...perLocale.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([l, n]) => `${l} ${n}`)
      .join(', ');
    shape.push(`${name} ${files.length} (${locales})`);
  }
  return { findings, problems, shape };
};

// ---------------------------------------------------------------- selftest

const selftest = async (): Promise<number> => {
  // Results are collected, then rendered once at the end, so a throw mid-way still reports nothing as passed.
  const results: { name: string; ok: boolean; detail: string }[] = [];
  const check = (name: string, ok: boolean, detail = ''): void => {
    results.push({ name, ok, detail });
  };

  const schemas = await loadSchemas();
  const parse = await loadParser();
  const docs: Schema | undefined = schemas.docs;
  check('content.config.ts exports a docs schema', docs !== undefined);
  if (!docs) return 1;

  const good = [
    '---',
    'title: "Backup destinations"',
    'description: "Where backups go."',
    'category: Guides',
    'tags:',
    '  - backup',
    'language: ru',
    'sourceHash: "0123456789abcdef"',
    '---',
    '',
    'Body.',
    '',
  ].join('\n');
  const goodRes = validateSource(good, docs, parse);
  check('a well-formed doc passes', goodRes.length === 0, goodRes.join('; '));

  // THE DEFECT: the same doc with the list markers written as en dashes.
  const enDash = good.replace('  - backup', '  \u2013 backup\n  \u2013 storage');
  const enRes = validateSource(enDash, docs, parse);
  check(
    'en-dash tags fire on tags, as a string-not-array issue',
    enRes.some((m) => m.startsWith('tags:') && /array/i.test(m)),
    enRes.join('; ')
  );
  check(
    'and the message names the typographic dash',
    enRes.some((m) => m.includes('typographic dash')),
    enRes.join('; ')
  );

  const noTitle = good.replace('title: "Backup destinations"\n', '');
  const ntRes = validateSource(noTitle, docs, parse);
  check(
    'a missing required title fires on title',
    ntRes.some((m) => m.startsWith('title:')),
    ntRes.join('; ')
  );

  const badCat = good.replace('category: Guides', 'category: Руководства');
  check(
    'a translated category fires',
    validateSource(badCat, docs, parse).some((m) => m.startsWith('category:'))
  );

  const badYaml = good.replace('tags:', 'tags: [unclosed');
  check(
    'a YAML syntax error fires instead of throwing',
    validateSource(badYaml, docs, parse).some((m) => m.includes('not valid YAML'))
  );

  check(
    'no front matter at all fires (title and description are required)',
    validateSource('Just a body.\n', docs, parse).length >= 2
  );

  const orderStr = good.replace('language: ru', 'language: ru\norder: "3"');
  check(
    'a quoted order fires (number expected)',
    validateSource(orderStr, docs, parse).some((m) => m.startsWith('order:'))
  );

  // Scan-level: zero entries is a problem, never a pass; an .mdx is an entry.
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'docs-fm-selftest-'));
  try {
    const empty = scan(tmp, schemas, parse);
    check(
      'an empty content root is a problem, not a pass',
      empty.problems.some((p) => p.includes("collection 'docs'") && p.includes('below the floor'))
    );
    fs.mkdirSync(path.join(tmp, 'docs', 'ru'), { recursive: true });
    fs.mkdirSync(path.join(tmp, 'docs', 'de'), { recursive: true });
    fs.writeFileSync(path.join(tmp, 'docs', 'ru', 'a.mdx'), enDash);
    const one = scan(tmp, schemas, parse);
    check(
      'an .mdx entry is scanned and its finding reported',
      one.findings.some((f) => f.file.endsWith('a.mdx'))
    );
    check(
      'an empty locale directory is a problem',
      one.problems.some((p) => p.includes("'de' holds zero entries"))
    );
    check(
      'a collection the gate does not map is a problem',
      scan(tmp, { ...schemas, extra: docs }, parse).problems.some((p) =>
        p.includes('[blog,docs,extra]')
      )
    );
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  for (const r of results) {
    console.log(
      `  ${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${!r.ok && r.detail ? ` -- ${r.detail}` : ''}`
    );
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\nselftest: ${results.length - failed} passed, ${failed} failed`);
  return failed === 0 ? 0 : 1;
};

// ---------------------------------------------------------------- main

const main = async (): Promise<number> => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const root = process.env.DOCS_FRONTMATTER_CONTENT_DIR
    ? path.resolve(process.env.DOCS_FRONTMATTER_CONTENT_DIR)
    : DEFAULT_CONTENT;

  let schemas: Record<string, Schema>;
  let parse: ParseFrontmatter;
  try {
    schemas = await loadSchemas();
    parse = await loadParser();
  } catch (e) {
    console.error(
      `✗ cannot load the content schema or the front matter parser: ${(e as Error).message}`
    );
    console.error(
      '  Nothing was validated. Run `npm ci && npm run install:natives` at the repo root, then re-run.'
    );
    return 1;
  }

  const { findings, problems, shape } = scan(root, schemas, parse);

  const report = problems.map((p) => `✗ ${p}`);
  if (findings.length > 0) {
    const files = new Set(findings.map((f) => f.file)).size;
    report.push(
      `✗ ${findings.length} front matter finding(s) in ${files} file(s); the Astro content loader refuses these and the site will not build or serve:`,
      '',
      ...findings.map((f) => `  ${path.relative(REPO, f.file)}: ${f.message}`),
      '',
      '  Fix the front matter to match the docs/blog schema in packages/www/src/content.config.ts.'
    );
  }
  // The shape prints on success too, so a collapsed count is visible in the log.
  if (report.length === 0) {
    console.log(`✓ front matter matches the content schema. ${shape.join('; ')}.`);
  } else {
    console.error(report.join('\n'));
  }
  return report.length === 0 ? 0 : 1;
};

process.exit(await main());
