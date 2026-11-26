#!/usr/bin/env tsx
/**
 * check-mcp-docs-parity -- every copy of the MCP setup page names exactly the tools the registry serves.
 *
 * THE FAILURE THIS EXISTS FOR (PLAN-rmcp-docs.md Context 1, Design 1). `ai-agents-mcp.md` listed `machine_query`, `config_repositories`, `agent_capabilities`, `backup_push`, `backup_pull` and `term_exec` long after the CLI stopped serving any of them, in all 13 languages, and omitted the job, repo-versioning, replication, cluster and datastore tools. Nothing compared the page with the tool set, so the page decayed in silence.
 *
 * WHAT IS COMPARED, against `packages/shared/src/mcp/tools.generated.json` (read here directly, not through the gen-docs provider, so this is a second reading of the registry rather than a re-run of the renderer):
 *
 *   1. The English page carries exactly one `gen-docs: mcp-tools` region and one `gen-docs: mcp-tools-local` region, and the tool names in their tables equal the registry's remote tools (every surface except `local`) and local-only tools, in registry order. A row renamed, dropped, added or moved is a finding naming the tool.
 *   2. Each locale page carries the same two tables with TRANSLATED descriptions, between `<!-- >>> translated-table: mcp-tools -->` and `<!-- <<< translated-table -->` (and the same for `mcp-tools-local`). They cannot be gen-docs regions, because gen-docs would overwrite the translations with English. Names and order are compared, never prose. A locale still waiting for its translation is exempt BY NAME in `PENDING_TABLE_TRANSLATION` below, printed on every run, and the exemption reds the moment that locale gains its tables, so the list can only shrink.
 *   3. Outside those tables, a backticked tool-shaped name (snake_case whose first segment is a registry tool family or a retired one) that the registry does not serve is a STALE MENTION. Today's stale mentions are frozen in `STALE_MENTION_BASELINE`; a new one fails, and a baselined one that has gone fails too until its entry is deleted, so the baseline only drains.
 *   4. Per translated page (both tables), the Destructive cells of the tools the registry marks `destructiveHint: true` use exactly one value, the cells of the others use exactly one value, and the two values differ (a locale that translated "yes" two ways, or one word for both, is a finding).
 *   5. A raw `<word>` in a translated table row outside a code span is a finding: in a rendered page it is read as an HTML tag and vanishes.
 *
 * BLIND SPOT, stated so the green is not read as more than it is: a stale name written WITHOUT backticks, or in a family neither the registry nor `RETIRED_FAMILIES` knows, is not seen. Prose about a tool that still exists but behaves differently is not seen either.
 *
 * ZERO IS A FAILURE. No registry tools, no English page, or a locale directory missing the page refuses with exit 1: a parity check over nothing would be a green that meant nothing.
 *
 * Usage:
 *   npx tsx scripts/gates/check-mcp-docs-parity.ts            check the tree
 *   npx tsx scripts/gates/check-mcp-docs-parity.ts --selftest prove each check can fire and stays quiet on a clean page
 *
 * ---- gate ----
 * step: Check MCP docs parity
 * needs: node
 * selftest: true
 * lane: quality-content
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { subset } from '@rediacc/locales';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { findRegions } from '../lib/doc-regions.js';
import { exitWithMainIfEntryPoint } from '../lib/entry-point.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const REGISTRY = 'packages/shared/src/mcp/tools.generated.json';
const DOCS = 'packages/www/src/content/docs';
const PAGE = 'ai-agents-mcp.md';
const SOURCE_LANG = 'en';

/** The two tables, by the gen-docs provider id that renders the English copy. */
const TABLES = ['mcp-tools', 'mcp-tools-local'] as const;
type Table = (typeof TABLES)[number];

/** Code-point order, the same as doc-providers.ts byCodePoint; kept local so this gate does not import that module and every record its providers read. */
const byCodePoint = (a: string, b: string): number => Number(a > b) - Number(a < b);

/**
 * Locales whose page does not carry the translated tables yet.
 *
 * Empty: PLAN-rmcp-docs.md DO7 landed the tables in all 12 locales. An entry is added only while a new locale's page is being translated, and the gate reds the moment a listed locale gains its tables, so the exemption cannot outlive the gap.
 */
export const PENDING_TABLE_TRANSLATION: readonly string[] = [];

/**
 * Tool families the registry no longer serves at all, so a mention of one is still recognised as a tool name.
 *
 * `agent_capabilities` and `term_exec` were MCP tools; their families have no registry tool left, so without this list a stale mention of either would not look tool-shaped.
 */
export const RETIRED_FAMILIES: readonly string[] = ['agent', 'term'];

/** Every locale of the page as of 2026-11-25; used only to spell the baseline below. */
const ALL_13 = subset('mcp-docs-stale-baseline', [
  'ar',
  'de',
  'en',
  'es',
  'et',
  'fr',
  'it',
  'ja',
  'ko',
  'pt',
  'ru',
  'tr',
  'zh',
]);

/**
 * Stale tool mentions frozen on 2026-11-25: name -> the locales whose page still carries it.
 *
 * BLOCKER: the 12 locale pages were retranslated from the DO4 English page, so only the per-repo secret tools remain (the page names them to say they are CLI-only). A fixed mention reds this gate until its locale is removed from the entry (and the entry deleted once empty). Do not add a name or a locale here: a new stale mention is fixed in the page.
 */
export const STALE_MENTION_BASELINE: Readonly<Record<string, readonly string[]>> = {
  repo_secret_set: ALL_13,
  repo_secret_unset: ALL_13,
};

/* ------------------------------------------------------------- pure helpers */

export interface RegistryTools {
  remote: string[];
  local: string[];
  /** Names of the tools whose annotations carry `destructiveHint: true`. */
  destructive: ReadonlySet<string>;
}

/** The registry's tool names split remote/local, in file order. Throws on a malformed or empty registry. */
export function parseRegistry(text: string): RegistryTools {
  const doc = JSON.parse(text) as {
    tools?: {
      name?: unknown;
      surface?: unknown;
      annotations?: { destructiveHint?: unknown };
    }[];
  };
  const tools = doc.tools ?? [];
  if (!Array.isArray(tools) || tools.length === 0) {
    throw new Error(`${REGISTRY} lists no tools`);
  }
  const destructive = new Set<string>();
  const out: RegistryTools = { remote: [], local: [], destructive };
  for (const [i, t] of tools.entries()) {
    if (typeof t.name !== 'string' || typeof t.surface !== 'string') {
      throw new Error(`${REGISTRY} tools[${i}] has no string name or surface`);
    }
    (t.surface === 'local' ? out.local : out.remote).push(t.name);
    if (t.annotations?.destructiveHint === true) destructive.add(t.name);
  }
  return out;
}

/** The registry tables a page is compared against. */
export const expectedFor = (reg: RegistryTools, table: Table): string[] =>
  table === 'mcp-tools' ? reg.remote : reg.local;

/** First-cell backticked names of the table rows in `lines`, in order. The header and separator rows carry no backticks and drop out. */
export function tableNames(lines: readonly string[]): string[] {
  const names: string[] = [];
  for (const l of lines) {
    const m = /^\|\s*`([^`]+)`\s*\|/.exec(l);
    if (m?.[1]) names.push(m[1]);
  }
  return names;
}

/** The second cell of each tool row (the Destructive column), by tool name, in order. */
export function destructiveCells(lines: readonly string[]): { name: string; cell: string }[] {
  const out: { name: string; cell: string }[] = [];
  for (const l of lines) {
    const m = /^\|\s*`([^`]+)`\s*\|([^|]*)\|/.exec(l);
    if (m?.[1]) out.push({ name: m[1], cell: (m[2] ?? '').trim() });
  }
  return out;
}

/** D6 check 1: one Destructive word per `destructiveHint` group, and the two words differ. */
export function destructiveWordFindings(
  rows: readonly { name: string; cell: string }[],
  destructive: ReadonlySet<string>
): string[] {
  const out: string[] = [];
  const yes = new Set(rows.filter((r) => destructive.has(r.name)).map((r) => r.cell));
  const no = new Set(rows.filter((r) => !destructive.has(r.name)).map((r) => r.cell));
  if (yes.size > 1)
    out.push(
      `Destructive cells of destructive tools use ${yes.size} different words (${[...yes].map((w) => `"${w}"`).join(', ')}); use one`
    );
  if (no.size > 1)
    out.push(
      `Destructive cells of non-destructive tools use ${no.size} different words (${[...no].map((w) => `"${w}"`).join(', ')}); use one`
    );
  if (yes.size === 1 && no.size === 1 && [...yes][0] === [...no][0])
    out.push(
      `Destructive cells use the same word "${[...yes][0]}" for destructive and non-destructive tools; the two groups must differ`
    );
  const wrong = rows
    .filter((r) => destructive.has(r.name) && no.has(r.cell) && !yes.has(r.cell))
    .map((r) => r.name);
  if (wrong.length > 0)
    out.push(
      `destructive tool(s) carry the non-destructive word: ${wrong.map((n) => `\`${n}\``).join(', ')}`
    );
  return out;
}

/** D6 check 2: a raw `<word>` outside a code span on a table row, as the line numbers (0-based offsets into `lines`) and the tag. */
export function rawAngleFindings(lines: readonly string[]): { at: number; tag: string }[] {
  const out: { at: number; tag: string }[] = [];
  for (const [i, l] of lines.entries()) {
    if (!l.startsWith('|')) continue;
    const bare = l.replace(/`[^`]*`/g, '');
    for (const m of bare.matchAll(/<[A-Za-z][\w-]*>/g)) out.push({ at: i, tag: m[0] });
  }
  return out;
}

export interface Span {
  table: string;
  /** 0-based line index of the opening marker. */
  open: number;
  /** 0-based line index of the closing marker. */
  close: number;
}

const TRANSLATED_OPEN = /^<!--\s*>>>\s*translated-table:\s*([a-z0-9-]+)\s*-->\s*$/;
const TRANSLATED_CLOSE = /^<!--\s*<<<\s*translated-table\s*-->\s*$/;

/** The table spans a page carries: gen-docs regions on the source page, translated-table spans on a locale page. Unbalanced markers are returned as errors. */
export function tableSpans(text: string, source: boolean): { spans: Span[]; errors: string[] } {
  if (source) {
    const found = findRegions(text);
    if ('errors' in found)
      return {
        spans: [],
        errors: found.errors.map((e) => `line ${e.line}: ${e.message}`),
      };
    return {
      spans: found.regions.map((r) => ({
        table: r.provider,
        open: r.open,
        close: r.close,
      })),
      errors: [],
    };
  }
  const lines = text.split('\n');
  const spans: Span[] = [];
  const errors: string[] = [];
  let open: { table: string; line: number } | null = null;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i] ?? '';
    const m = TRANSLATED_OPEN.exec(l);
    if (m) {
      if (open)
        errors.push(`line ${i + 1}: translated-table "${m[1]}" opens inside "${open.table}"`);
      open = { table: m[1] ?? '', line: i };
    } else if (TRANSLATED_CLOSE.test(l)) {
      if (!open) errors.push(`line ${i + 1}: translated-table close with nothing open`);
      else spans.push({ table: open.table, open: open.line, close: i });
      open = null;
    }
  }
  if (open) errors.push(`line ${open.line + 1}: translated-table "${open.table}" is never closed`);
  return { spans, errors };
}

/** What differs between the expected and the actual name sequence, one line per difference, naming the tool. */
export function compareNames(expected: readonly string[], actual: readonly string[]): string[] {
  const out: string[] = [];
  const exp = new Set(expected);
  const act = new Set(actual);
  for (const n of expected) if (!act.has(n)) out.push(`missing \`${n}\` (the registry serves it)`);
  for (const n of actual)
    if (!exp.has(n)) out.push(`extra \`${n}\` (the registry does not serve it)`);
  const seen = new Set<string>();
  for (const n of actual) {
    if (seen.has(n)) out.push(`\`${n}\` is listed twice`);
    seen.add(n);
  }
  if (out.length === 0) {
    const at = expected.findIndex((n, i) => actual[i] !== n);
    if (at >= 0)
      out.push(
        `order differs at row ${at + 1}: expected \`${expected[at]}\`, found \`${actual[at]}\``
      );
  }
  return out;
}

const TOOL_TOKEN = /`([a-z][a-z0-9-]*(?:_[a-z0-9-]+)+)`/g;

/** Backticked tool-shaped names on the lines OUTSIDE `spans` that `served` does not contain, de-duplicated and sorted. */
export function staleMentions(
  text: string,
  spans: readonly Span[],
  served: ReadonlySet<string>,
  families: ReadonlySet<string>
): string[] {
  const lines = text.split('\n');
  const inside = (i: number): boolean => spans.some((s) => i >= s.open && i <= s.close);
  const found = new Set<string>();
  for (let i = 0; i < lines.length; i++) {
    if (inside(i)) continue;
    for (const m of (lines[i] ?? '').matchAll(TOOL_TOKEN)) {
      const name = m[1] ?? '';
      const family = name.slice(0, name.indexOf('_'));
      if (families.has(family) && !served.has(name)) found.add(name);
    }
  }
  return [...found].sort(byCodePoint);
}

/** The families a tool-shaped name is recognised by: each registry tool's first segment, plus the retired ones. */
export function familiesOf(reg: RegistryTools, retired: readonly string[]): Set<string> {
  const out = new Set(retired);
  for (const n of [...reg.remote, ...reg.local])
    if (n.includes('_')) out.add(n.slice(0, n.indexOf('_')));
  return out;
}

export interface PageInput {
  lang: string;
  text: string;
}

export interface Audit {
  findings: string[];
  /** Locales whose page carries no translated tables and is exempt by name. */
  pending: string[];
  /** Baselined stale mentions still present, as `lang:name`. */
  baselined: number;
  /** Locales whose translated tables were compared. */
  translated: string[];
}

/** The whole check over already-read inputs, so the selftest drives exactly what the tree run drives. */
export function audit(
  reg: RegistryTools,
  pages: readonly PageInput[],
  pending: readonly string[],
  retired: readonly string[],
  baseline: Readonly<Record<string, readonly string[]>>
): Audit {
  const findings: string[] = [];
  const served = new Set([...reg.remote, ...reg.local]);
  const families = familiesOf(reg, retired);
  const baselinePairs = new Set(
    Object.entries(baseline).flatMap(([name, langs]) => langs.map((l) => `${l}:${name}`))
  );
  const seenPairs = new Set<string>();
  const translated: string[] = [];
  const pendingOut: string[] = [];

  if (!pages.some((p) => p.lang === SOURCE_LANG)) {
    findings.push(
      `${DOCS}/${SOURCE_LANG}/${PAGE}: the English page is missing, so there is nothing to compare.`
    );
  }

  for (const p of pages) {
    const file = `${DOCS}/${p.lang}/${PAGE}`;
    const source = p.lang === SOURCE_LANG;
    const { spans, errors } = tableSpans(p.text, source);
    for (const e of errors) findings.push(`${file}: ${e}`);
    const lines = p.text.split('\n');

    const ours = spans.filter((s) => (TABLES as readonly string[]).includes(s.table));
    if (!source && ours.length === 0 && pending.includes(p.lang)) {
      pendingOut.push(p.lang);
    } else {
      if (!source && pending.includes(p.lang)) {
        findings.push(
          `${file}: carries translated tables but is still listed in PENDING_TABLE_TRANSLATION; delete "${p.lang}" from that list in scripts/gates/check-mcp-docs-parity.ts.`
        );
      }
      if (!source) translated.push(p.lang);
      for (const table of TABLES) {
        const mine = ours.filter((s) => s.table === table);
        const how = source
          ? `\`<!-- >>> gen-docs: ${table} -->\` region`
          : `\`<!-- >>> translated-table: ${table} -->\` span`;
        if (mine.length !== 1) {
          findings.push(`${file}: expected exactly one ${how}, found ${mine.length}.`);
          continue;
        }
        const span = mine[0] as Span;
        const diffs = compareNames(
          expectedFor(reg, table),
          tableNames(lines.slice(span.open + 1, span.close))
        );
        for (const d of diffs) {
          findings.push(
            `${file}:${span.open + 1}: ${table} table: ${d}. ` +
              (source
                ? 'Fix: npx tsx scripts/gen/gen-docs.ts --write.'
                : 'Fix: give the translated table the English rows, same names, same order.')
          );
        }
        if (!source) {
          const body = lines.slice(span.open + 1, span.close);
          for (const r of rawAngleFindings(body)) {
            findings.push(
              `${file}:${span.open + 2 + r.at}: ${table} table: raw ${r.tag} outside a code span is read as an HTML tag. Fix: put it in a code span.`
            );
          }
        }
      }
    }

    if (!source && ours.length > 0) {
      const rows = ours.flatMap((sp) => destructiveCells(lines.slice(sp.open + 1, sp.close)));
      for (const d of destructiveWordFindings(rows, reg.destructive)) {
        findings.push(
          `${file}: translated tables: ${d}. Fix: use the word the page uses for its other destructive tools.`
        );
      }
    }

    for (const name of staleMentions(p.text, spans, served, families)) {
      const pair = `${p.lang}:${name}`;
      seenPairs.add(pair);
      if (!baselinePairs.has(pair)) {
        findings.push(
          `${file}: mentions \`${name}\`, which ${REGISTRY} does not serve. Fix: delete the mention or name the tool that replaced it. Do not add it to the baseline.`
        );
      }
    }
  }

  const langsSeen = new Set(pages.map((p) => p.lang));
  for (const pair of [...baselinePairs].sort(byCodePoint)) {
    const lang = pair.slice(0, pair.indexOf(':'));
    if (langsSeen.has(lang) && !seenPairs.has(pair)) {
      findings.push(
        `${DOCS}/${lang}/${PAGE}: baselined stale mention \`${pair.slice(lang.length + 1)}\` is gone; remove "${lang}" from its STALE_MENTION_BASELINE entry so the baseline keeps shrinking.`
      );
    }
  }

  return {
    findings,
    pending: pendingOut,
    baselined: [...seenPairs].filter((x) => baselinePairs.has(x)).length,
    translated,
  };
}

/* ----------------------------------------------------------------- selftest */

function selftestCases(): ControlCase[] {
  const reg: RegistryTools = {
    remote: ['job_list', 'repo_up'],
    local: ['config_list'],
    destructive: new Set(['repo_up']),
  };
  const regionPage = (remote: string[], local: string[], extra = ''): string =>
    [
      '# MCP',
      extra,
      '<!-- >>> gen-docs: mcp-tools -->',
      '| Tool | Destructive | Description |',
      '|---|---|---|',
      ...remote.map((n) => `| \`${n}\` | no | x |`),
      '<!-- <<< gen-docs -->',
      '<!-- >>> gen-docs: mcp-tools-local -->',
      '| Tool | Destructive | Description |',
      '|---|---|---|',
      ...local.map((n) => `| \`${n}\` | no | x |`),
      '<!-- <<< gen-docs -->',
    ].join('\n');
  const translatedPage = (
    remote: string[],
    local: string[],
    word: (n: string) => string = (n) => (reg.destructive.has(n) ? 'ja' : 'nein'),
    desc = 'y'
  ): string =>
    [
      '<!-- >>> translated-table: mcp-tools -->',
      '| Werkzeug | Destruktiv | Beschreibung |',
      '|---|---|---|',
      ...remote.map((n) => `| \`${n}\` | ${word(n)} | ${desc} |`),
      '<!-- <<< translated-table -->',
      '<!-- >>> translated-table: mcp-tools-local -->',
      ...local.map((n) => `| \`${n}\` | ${word(n)} | ${desc} |`),
      '<!-- <<< translated-table -->',
    ].join('\n');
  const clean = regionPage(reg.remote, reg.local);
  const run = (
    pages: PageInput[],
    pending: string[] = [],
    baseline: Record<string, string[]> = {}
  ): Audit => audit(reg, pages, pending, ['term'], baseline);
  const n = (a: Audit): number => a.findings.length;
  const has = (a: Audit, s: string): boolean => a.findings.some((f) => f.includes(s));

  const cleanAudit = run([{ lang: 'en', text: clean }]);
  const renamed = run([{ lang: 'en', text: regionPage(['job_lisst', 'repo_up'], reg.local) }]);
  const dropped = run([{ lang: 'en', text: regionPage(['repo_up'], reg.local) }]);
  const swapped = run([{ lang: 'en', text: regionPage(['repo_up', 'job_list'], reg.local) }]);
  const noRegion = run([{ lang: 'en', text: '# MCP\n| `job_list` | x |' }]);
  const stale = run([
    {
      lang: 'en',
      text: regionPage(reg.remote, reg.local, 'Use `job_query` or `term_exec`.'),
    },
  ]);
  const notTool = run([
    {
      lang: 'en',
      text: regionPage(
        reg.remote,
        reg.local,
        'Edit `authorized_keys`; call `repo_up`; read `read_only`.'
      ),
    },
  ]);
  const baselined = run(
    [
      {
        lang: 'en',
        text: regionPage(reg.remote, reg.local, 'Old `repo_secret_set`.'),
      },
    ],
    [],
    { repo_secret_set: ['en'] }
  );
  const drained = run([{ lang: 'en', text: clean }], [], {
    repo_secret_set: ['en'],
  });
  const locOk = run([
    { lang: 'en', text: clean },
    { lang: 'de', text: translatedPage(reg.remote, reg.local) },
  ]);
  const withDe = (text: string): Audit =>
    run([
      { lang: 'en', text: clean },
      { lang: 'de', text },
    ]);
  const wordSplit = withDe(
    translatedPage(reg.remote, reg.local, (n) => (n === 'repo_up' ? 'ja' : 'nein')).replace(
      '| `config_list` | nein',
      '| `config_list` | nö'
    )
  );
  const wordSame = withDe(translatedPage(reg.remote, reg.local, () => 'nein'));
  const wordWrongRow = withDe(
    translatedPage(reg.remote, reg.local, (n) => (n === 'job_list' ? 'ja' : 'nein'))
  );
  const rawTag = withDe(
    translatedPage(reg.remote, reg.local, undefined, 'Datei ~/x/<config>.json')
  );
  const spanTag = withDe(
    translatedPage(reg.remote, reg.local, undefined, 'Datei `~/x/<config>.json`')
  );
  const locBad = run([
    { lang: 'en', text: clean },
    { lang: 'de', text: translatedPage(['job_list'], reg.local) },
  ]);
  const locPending = run(
    [
      { lang: 'en', text: clean },
      { lang: 'de', text: '# alt' },
    ],
    ['de']
  );
  const locStaleExempt = run(
    [
      { lang: 'en', text: clean },
      { lang: 'de', text: translatedPage(reg.remote, reg.local) },
    ],
    ['de']
  );
  const locUnlisted = run([
    { lang: 'en', text: clean },
    { lang: 'de', text: '# alt' },
  ]);
  const noEnglish = run([{ lang: 'de', text: translatedPage(reg.remote, reg.local) }]);
  let emptyRefused = false;
  try {
    parseRegistry('{"tools": []}');
  } catch {
    emptyRefused = true;
  }

  return [
    {
      name: 'clean control: matching English regions give no finding',
      ok: n(cleanAudit) === 0,
      detail: cleanAudit.findings.join('; '),
    },
    {
      name: 'planted: a renamed row fires, naming both names',
      ok: has(renamed, 'missing `job_list`') && has(renamed, 'extra `job_lisst`'),
    },
    {
      name: 'planted: a dropped row fires',
      ok: has(dropped, 'missing `job_list`'),
    },
    {
      name: 'planted: two swapped rows fire as an order difference',
      ok: has(swapped, 'order differs at row 1'),
    },
    {
      name: 'planted: an English page without the regions fires for both tables',
      ok:
        has(noRegion, 'gen-docs: mcp-tools -->') && has(noRegion, 'gen-docs: mcp-tools-local -->'),
    },
    {
      name: 'planted: stale mentions fire, a retired family included',
      ok: has(stale, '`job_query`') && has(stale, '`term_exec`') && n(stale) === 2,
    },
    {
      name: 'control: a served tool and non-tool snake_case give no finding',
      ok: n(notTool) === 0,
      detail: notTool.findings.join('; '),
    },
    {
      name: 'control: a baselined stale mention gives no finding',
      ok: n(baselined) === 0 && baselined.baselined === 1,
    },
    {
      name: 'planted: a baselined mention that is gone fires the drain message',
      ok: has(drained, 'is gone'),
    },
    {
      name: 'control: a locale with matching translated tables gives no finding',
      ok: n(locOk) === 0 && locOk.translated.includes('de'),
      detail: locOk.findings.join('; '),
    },
    {
      name: 'control: destructive and non-destructive words that each agree and differ give no finding',
      ok: n(locOk) === 0,
      detail: locOk.findings.join('; '),
    },
    {
      name: 'planted: two words for the non-destructive group fire',
      ok: has(wordSplit, 'non-destructive tools use 2 different words'),
    },
    {
      name: 'planted: one word for both groups fires',
      ok: has(wordSame, 'the two groups must differ'),
    },
    {
      name: 'planted: the wrong tool flagged destructive (one shared word) fires',
      ok:
        has(wordWrongRow, 'destructive tool(s) carry the non-destructive word: `job_list`') ||
        has(wordWrongRow, 'different words'),
      detail: wordWrongRow.findings.join('; '),
    },
    {
      name: 'planted: a raw <config> outside a code span fires',
      ok: has(rawTag, 'raw <config> outside a code span'),
    },
    {
      name: 'control: the same <config> inside a code span gives no finding',
      ok: n(spanTag) === 0,
      detail: spanTag.findings.join('; '),
    },
    {
      name: 'planted: a locale translated table missing a row fires',
      ok: has(locBad, 'missing `repo_up`'),
    },
    {
      name: 'control: a pending locale without tables is reported, not failed',
      ok: n(locPending) === 0 && locPending.pending.includes('de'),
    },
    {
      name: 'planted: a pending locale that gained its tables fires the stale exemption',
      ok: has(locStaleExempt, 'PENDING_TABLE_TRANSLATION'),
    },
    {
      name: 'planted: an unlisted locale without tables fires',
      ok: has(locUnlisted, 'translated-table: mcp-tools -->'),
    },
    {
      name: 'planted: a missing English page fires',
      ok: has(noEnglish, 'English page is missing'),
    },
    { name: 'planted: an empty registry is refused', ok: emptyRefused },
    ...treeRefusalCases(),
  ];
}

/** main() over a throwaway docs tree: a clean English-only tree passes, an empty docs tree and a locale directory without the page are each refused. */
function treeRefusalCases(): ControlCase[] {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'mcp-docs-parity-'));
  const verdicts: Record<string, number> = {};
  const build = (name: string, withEnglish: boolean, emptyLocale: boolean): string => {
    const root = path.join(base, name);
    fs.mkdirSync(path.join(root, path.dirname(REGISTRY)), { recursive: true });
    fs.copyFileSync(path.join(ROOT, REGISTRY), path.join(root, REGISTRY));
    fs.mkdirSync(path.join(root, DOCS), { recursive: true });
    if (withEnglish) {
      fs.mkdirSync(path.join(root, DOCS, SOURCE_LANG), { recursive: true });
      fs.copyFileSync(
        path.join(ROOT, DOCS, SOURCE_LANG, PAGE),
        path.join(root, DOCS, SOURCE_LANG, PAGE)
      );
    }
    if (emptyLocale) fs.mkdirSync(path.join(root, DOCS, 'xx'));
    return root;
  };
  const quietly = (root: string): number => {
    const { log, error } = console;
    console.log = () => undefined;
    console.error = () => undefined;
    try {
      return main([], root);
    } finally {
      console.log = log;
      console.error = error;
    }
  };
  try {
    verdicts.empty = quietly(build('empty', false, false));
    verdicts.missing = quietly(build('missing', true, true));
    verdicts.clean = quietly(build('clean', true, false));
  } finally {
    fs.rmSync(base, { recursive: true, force: true });
  }
  return [
    {
      name: 'tree: a docs tree with no page anywhere is refused as vacuous, not passed',
      ok: verdicts.empty === 1,
    },
    {
      name: 'tree: a locale directory without the page is refused (read through main)',
      ok: verdicts.missing === 1,
    },
    {
      name: 'tree: CONTROL, the same tree without the empty locale passes',
      ok: verdicts.clean === 0,
    },
  ];
}

/* --------------------------------------------------------------------- main */

function readPages(root: string): { pages: PageInput[]; missing: string[] } {
  const dir = path.join(root, DOCS);
  const langs = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort(byCodePoint);
  const pages: PageInput[] = [];
  const missing: string[] = [];
  for (const lang of langs) {
    const f = path.join(dir, lang, PAGE);
    if (fs.existsSync(f)) pages.push({ lang, text: fs.readFileSync(f, 'utf-8') });
    else missing.push(`${DOCS}/${lang}/${PAGE}`);
  }
  return { pages, missing };
}

export function main(argv: string[], root: string = ROOT): number {
  if (argv.includes('--selftest')) {
    console.log('check-mcp-docs-parity selftest');
    return summarizeControls(selftestCases());
  }

  const regFile = path.join(root, REGISTRY);
  if (!fs.existsSync(regFile)) {
    console.error(
      `${RED}✗${NC} ${REGISTRY} is missing; regenerate it with npx tsx packages/cli/scripts/generate-mcp-registry.ts.`
    );
    return 1;
  }
  let reg: RegistryTools;
  try {
    reg = parseRegistry(fs.readFileSync(regFile, 'utf-8'));
  } catch (e) {
    console.error(
      `${RED}✗${NC} ${(e as Error).message}; the gate has no tool set to compare against.`
    );
    return 1;
  }

  const { pages, missing } = readPages(root);
  if (pages.length === 0) {
    console.error(
      `${RED}✗${NC} VACUOUS: no ${PAGE} under ${DOCS}/<lang>/; the gate is not seeing the tree, so its green would mean nothing.`
    );
    return 1;
  }

  const a = audit(reg, pages, PENDING_TABLE_TRANSLATION, RETIRED_FAMILIES, STALE_MENTION_BASELINE);
  const findings = [
    ...missing.map((m) => `${m}: missing; every docs locale carries the MCP page.`),
    ...a.findings,
  ];

  if (a.pending.length > 0) {
    console.log(
      `${YELLOW}pending${NC} ${a.pending.length} locale(s) carry no translated tool tables yet (PENDING_TABLE_TRANSLATION, PLAN-rmcp-docs.md DO7): ${a.pending.join(', ')}`
    );
  }
  if (a.baselined > 0) {
    console.log(
      `${YELLOW}baselined${NC} ${a.baselined} stale tool mention(s) across the pages (STALE_MENTION_BASELINE, DO4 and DO7 drain it)`
    );
  }

  const shape =
    `${pages.length} page(s), ${reg.remote.length + reg.local.length} registry tool(s) ` +
    `(${reg.remote.length} remote, ${reg.local.length} local-only), ` +
    `${a.translated.length} locale table set(s) compared, ${a.pending.length} pending, ${a.baselined} baselined stale mention(s)`;
  if (findings.length > 0) {
    for (const f of findings) console.error(`  ${RED}FAIL${NC}  ${f}`);
    console.error(`${RED}✗${NC} check-mcp-docs-parity: ${findings.length} finding(s); ${shape}.`);
    return 1;
  }
  console.log(
    `${GREEN}✓${NC} check-mcp-docs-parity: the English tool tables match the registry; ${shape}.`
  );
  return 0;
}

exitWithMainIfEntryPoint(import.meta.filename, main);
