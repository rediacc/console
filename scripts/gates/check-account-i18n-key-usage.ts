#!/usr/bin/env tsx
/**
 * Every translation key the account portal asks for must exist in its English catalogs.
 *
 * WHY THIS EXISTS. The www pricing page rendered `pages.pricing.plans.free.name` as visible
 * text (2026-11-17), and the question that followed was which other surface could do the
 * same. The account portal (`private/account/web`) could, and nothing checked it: www has
 * check-translation-key-usage.ts, the CLI has check-cli-i18n-key-usage.ts, and the portal's
 * ~2,800 `t()` calls had no source-to-catalog gate at all. i18next answers a missing key by
 * returning the key, so a typo or a deleted key ships as a raw dotted string.
 *
 * WHAT IT RESOLVES, against `web/src/i18n/locales/en/<namespace>.json`:
 *   - `t('ns:key')`: exactly that namespace.
 *   - `t('key')`: the namespaces the FILE binds with `useTranslation('ns' | ['a', 'b'])`,
 *     plus `common` when it calls `useTranslation()` bare (the configured defaultNS). A
 *     file that binds none (a helper handed a `TFunction`) is checked against every
 *     namespace, which still catches a key that exists nowhere.
 *   - `t: alias` destructuring (`const { t: tc } = useTranslation('common')`) binds the
 *     alias to its own namespaces.
 *   - i18next plurals: `key` resolves when `key_one` / `key_other` / ... exists.
 *   - `<Trans i18nKey="key">`.
 *   - A template key with a literal prefix (`t(`notices:kind.${k}`)`) as a WILDCARD: at
 *     least one catalog path must match `kind.*`. That proves the fixed parts; it cannot
 *     prove every runtime value of `k` has an entry.
 *
 * WHAT IT CANNOT SEE, said out loud: a key held in a variable (`t(item.labelKey)`), a key
 * chosen by a ternary, and a template with no literal prefix. Each is COUNTED and printed,
 * so the coverage line is honest.
 *
 * Usage:
 *   npx tsx scripts/gates/check-account-i18n-key-usage.ts [--selftest]
 *
 * ---- gate ----
 * kind: shared-step
 * step: i18n
 * needs: node, submodules
 * id: check:ci-i18n-account-key-usage
 * lane: quality-i18n
 * ---- end gate ----
 */
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';
import { GREEN, NC, RED } from '../lib/console.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { refuseFindings } from '../lib/findings-report.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';
import { stripComments } from './check-translation-key-usage.js';

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

const DEFAULT_NS = 'common';
const PLURAL_SUFFIXES = ['_zero', '_one', '_two', '_few', '_many', '_other'];

function collectPaths(node: Json, prefix: string, out: Set<string>): void {
  if (node && typeof node === 'object' && !Array.isArray(node)) {
    for (const [k, v] of Object.entries(node)) {
      const p = prefix ? `${prefix}.${k}` : k;
      // Leaves only. A branch object is not a translation: i18next returns the key for
      // `t('pages.pricing')`, so recording the branch made that call read as present.
      if (v && typeof v === 'object' && !Array.isArray(v)) collectPaths(v, p, out);
      else out.add(p);
    }
  }
}

export function catalogsFrom(raw: Record<string, Json>): Map<string, Set<string>> {
  const out: Map<string, Set<string>> = new Map();
  for (const [ns, tree] of Object.entries(raw)) {
    const paths = new Set<string>();
    collectPaths(tree, '', paths);
    out.set(ns, paths);
  }
  return out;
}

export interface Finding {
  file: string;
  line: number;
  key: string;
  searched: string[];
}

export interface ScanResult {
  findings: Finding[];
  checked: number;
  unresolvable: number;
}

/** The namespace list inside `useTranslation(...)`'s parentheses. */
function nsList(args: string): string[] {
  const names = [...args.matchAll(/['"]([\w-]+)['"]/g)].map((m) => m[1]);
  return names.length > 0 ? names : [DEFAULT_NS];
}

/** translate-function name -> namespaces it is bound to, for one file. */
function bindings(src: string): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  const add = (name: string, ns: string[]) => {
    if (!out.has(name)) out.set(name, new Set());
    for (const n of ns) out.get(name)!.add(n);
  };
  const re = /\{([^{}]*)\}\s*=\s*useTranslation\(([^)]*)\)/g;
  for (const m of src.matchAll(re)) {
    const ns = nsList(m[2]);
    const alias = /(?:^|[\s,])t\s*:\s*([A-Za-z_$][\w$]*)/.exec(m[1]);
    if (alias) add(alias[1], ns);
    else if (/(?:^|[\s,])t(?:\s*[,}]|\s*$)/.test(m[1])) add('t', ns);
  }
  return out;
}

function exists(
  catalogs: Map<string, Set<string>>,
  namespaces: Iterable<string>,
  key: string,
  wildcard?: RegExp
): boolean {
  for (const ns of namespaces) {
    const paths = catalogs.get(ns);
    if (!paths) continue;
    if (wildcard) {
      for (const p of paths) if (wildcard.test(p)) return true;
      continue;
    }
    if (paths.has(key)) return true;
    if (PLURAL_SUFFIXES.some((s) => paths.has(`${key}${s}`))) return true;
  }
  return false;
}

function wildcardFor(body: string): RegExp {
  const parts = body.split(/\$\{[^}]*\}/).map((p) => p.replace(/[.*+?^$()|[\]\\{}]/g, '\\$&'));
  return new RegExp(`^${parts.join('[^.]+')}$`);
}

/** Scan one source file. Pure, so the controls can drive it with fixtures. */
export function scanFile(
  file: string,
  raw: string,
  catalogs: Map<string, Set<string>>,
  result: ScanResult
): void {
  const src = stripComments(raw);
  const bound = bindings(src);
  const all = [...catalogs.keys()];
  const lineOf = (idx: number) => src.slice(0, idx).split('\n').length;
  const nsFor = (fn: string): string[] => {
    const b = bound.get(fn);
    if (b && b.size > 0) return [...b];
    // An unbound `t`: a TFunction parameter or a module-level i18n.t. Any namespace.
    return all;
  };

  const check = (fn: string, body: string, idx: number, isTemplate: boolean) => {
    let ns: string[];
    let key = body;
    const colon = /^([\w-]+):(.*)$/s.exec(body);
    if (colon && catalogs.has(colon[1])) {
      ns = [colon[1]];
      key = colon[2];
    } else {
      ns = nsFor(fn);
    }
    if (isTemplate && !/^[A-Za-z]/.test(key)) {
      result.unresolvable++;
      return;
    }
    result.checked++;
    const ok = isTemplate ? exists(catalogs, ns, key, wildcardFor(key)) : exists(catalogs, ns, key);
    if (!ok) {
      result.findings.push({
        file,
        line: lineOf(idx),
        key: isTemplate ? `\`${body}\`` : body,
        searched: ns.length === all.length && ns.length > 1 ? ['(every namespace)'] : ns,
      });
    }
  };

  const names = new Set<string>(['t', ...bound.keys()]);
  for (const fn of names) {
    const esc = fn.replace(/\$/g, '\\$');
    // A call, not a method or a longer identifier: `t(` but never `.t(` on an unrelated
    // object, `set(` or `format(`. `i18n.t(` is the one member call that is a translation.
    const callRe = new RegExp(`(?:(?<![\\w$.])|(?<=\\bi18n\\.))${esc}\\(\\s*(['"\`])`, 'g');
    for (const m of src.matchAll(callRe)) {
      const q = m[1];
      const start = (m.index ?? 0) + m[0].length;
      const end = src.indexOf(q, start);
      if (end < 0) continue;
      const body = src.slice(start, end);
      if (body.includes('\n')) continue;
      const after = src.slice(end + 1).trimStart()[0];
      // `t('a' + x)`, `t(cond ? 'a' : 'b')` and friends: not a whole-key literal.
      if (after !== ')' && after !== ',') {
        result.unresolvable++;
        continue;
      }
      if (q === '`' && body.includes('${')) check(fn, body, m.index ?? 0, true);
      else check(fn, body, m.index ?? 0, false);
    }
    const varRe = new RegExp(`(?<![\\w$.])${esc}\\(\\s*[A-Za-z_$(]`, 'g');
    for (const _ of src.matchAll(varRe)) result.unresolvable++;
  }
  for (const m of src.matchAll(/\bi18nKey=\{?\s*['"]([^'"]+)['"]/g)) {
    check('t', m[1], m.index ?? 0, false);
  }
}

function fixtureCatalogs(): Map<string, Set<string>> {
  return catalogsFrom({
    common: { save: 'Save', items_one: '{{count}} item', items_other: '{{count}} items' },
    notices: { kind: { outage: 'Outage', maintenance: 'Maintenance' }, title: 'Notices' },
    partner: { deals: { status: { open: 'Open' } } },
  });
}

function controls(): ControlCase[] {
  const cat = fixtureCatalogs();
  const run = (src: string): string[] => {
    const r: ScanResult = { findings: [], checked: 0, unresolvable: 0 };
    scanFile('probe.tsx', src, cat, r);
    return r.findings.map((f) => f.key);
  };
  const cases: [string, string, string[]][] = [
    [
      'CONTROL: a key missing from the bound namespace fires',
      "const { t } = useTranslation('notices');\nt('gone');",
      ['gone'],
    ],
    [
      'CONTROL: a key that exists only in ANOTHER namespace fires',
      "const { t } = useTranslation('notices');\nt('save');",
      ['save'],
    ],
    [
      'CONTROL: an explicit ns: prefix is resolved in that namespace',
      "t('notices:nope');",
      ['notices:nope'],
    ],
    [
      'CONTROL: a dynamic key whose fixed tail matches nothing fires',
      "const { t } = useTranslation('partner');\nt(`deals.status.${s}.label`);",
      ['`deals.status.${s}.label`'],
    ],
    [
      'CONTROL: an aliased t is bound to its own namespace',
      "const { t: tn } = useTranslation('notices');\ntn('save');",
      ['save'],
    ],
    ['CONTROL: a Trans i18nKey is checked', '<Trans i18nKey="missingKey" />', ['missingKey']],
    [
      'CONTROL: a key naming a namespace BRANCH, not a string, fires',
      "const { t } = useTranslation('partner');\nt('deals.status');",
      ['deals.status'],
    ],
    [
      'CONTROL: a wildcard that reaches only a branch fires',
      "const { t } = useTranslation('partner');\nt(`deals.${x}`);",
      ['`deals.${x}`'],
    ],
    [
      'SILENT: a key in the bound namespace',
      "const { t } = useTranslation('notices');\nt('title');",
      [],
    ],
    [
      'SILENT: bare useTranslation() binds common',
      "const { t } = useTranslation();\nt('save');",
      [],
    ],
    [
      'SILENT: a plural base resolves through _one/_other',
      "const { t } = useTranslation();\nt('items', { count });",
      [],
    ],
    ['SILENT: a wildcard that matches real paths', 't(`notices:kind.${notice.kind}`);', []],
    ['SILENT: a key held in a variable is counted, not guessed', 't(item.labelKey);', []],
    ['SILENT: a key in a comment is not a call', "// t('gone')\n", []],
    ['SILENT: a method named t on another object is not a call', "foo.t('gone');", []],
    [
      'SILENT: a two-namespace binding resolves in either',
      "const { t } = useTranslation(['notices', 'common']);\nt('save');",
      [],
    ],
  ];
  const scanned = cases.map(([name, src, want]) => {
    const got = run(src);
    return {
      name,
      ok: JSON.stringify(got) === JSON.stringify(want),
      detail: `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`,
    };
  });
  const floor = (name: string, files: number, checked: number, vacuous: boolean): ControlCase => ({
    name,
    ok: isVacuous(files, checked) === vacuous,
    detail: `${files} file(s), ${checked} key(s), want vacuous=${vacuous}`,
  });
  return [
    ...scanned,
    floor('CONTROL: one file under the file floor is vacuous', MIN_FILES - 1, MIN_KEYS, true),
    floor('CONTROL: one key under the key floor is vacuous', MIN_FILES, MIN_KEYS - 1, true),
    floor('CONTROL: nothing scanned is vacuous', 0, 0, true),
    floor('SILENT: exactly at both floors is not vacuous', MIN_FILES, MIN_KEYS, false),
  ];
}

function loadCatalogs(dir: string): Map<string, Set<string>> {
  const raw: Record<string, Json> = {};
  for (const f of readdirSync(dir)) {
    if (f.endsWith('.json'))
      raw[f.slice(0, -5)] = JSON.parse(readFileSync(path.join(dir, f), 'utf8')) as Json;
  }
  return catalogsFrom(raw);
}

// VACUITY FLOORS, measured 2026-11-17: 293 source files and 2819 key references. The floors sit far below that so a normal refactor never trips them, and far above trivial, so a glob or a catalog loader that goes blind cannot pass as a clean tree.
const MIN_FILES = 100;
const MIN_KEYS = 1000;

export function isVacuous(files: number, checked: number): boolean {
  return files < MIN_FILES || checked < MIN_KEYS;
}

function main(): void {
  console.log('account-i18n-key-usage controls');
  if (summarizeControls(controls()) !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }
  if (process.argv.includes('--selftest')) process.exit(0);

  const webSrc = submodulePath('private/account/web/src');
  const enDir = path.join(webSrc, 'i18n/locales/en');
  if (!requireSubmodule('account portal translation key usage', [enDir])) process.exit(0);

  const catalogs = loadCatalogs(enDir);
  const files = globSync('**/*.{ts,tsx}', {
    cwd: webSrc,
    absolute: true,
    ignore: ['**/__tests__/**', '**/*.test.ts', '**/*.test.tsx', '**/*.d.ts'],
  });
  const result: ScanResult = { findings: [], checked: 0, unresolvable: 0 };
  for (const f of files)
    scanFile(path.relative(webSrc, f), readFileSync(f, 'utf8'), catalogs, result);

  if (isVacuous(files.length, result.checked)) {
    console.error(
      `${RED}✗${NC} VACUOUS: ${result.checked} key(s) checked across ${files.length} file(s), floors ${MIN_KEYS} and ${MIN_FILES}; the gate verified nothing.`
    );
    process.exit(1);
  }
  const coverage = `${result.checked} key reference(s) checked, ${result.unresolvable} held in a variable or built without a literal prefix (not statically checkable), ${files.length} file(s).`;
  if (result.findings.length > 0) {
    refuseFindings({
      header: `\n${RED}✗${NC} ${result.findings.length} account portal translation key(s) missing from web/src/i18n/locales/en:\n`,
      items: result.findings.map(
        (f) => `web/src/${f.file}:${f.line}: ${f.key}  (looked in: ${f.searched.join(', ')})`
      ),
      limit: 60,
      remedy: [
        `\n${coverage}`,
        'Add each key to the English namespace file and the 12 locales, or fix the call.',
      ],
    });
  }
  console.log(`${GREEN}✓${NC} ${coverage}`);
}

if (isEntryPoint(import.meta.filename)) main();
