#!/usr/bin/env tsx
/**
 * Every i18n key the account portal holds in CONFIG must resolve, so no nav label, page title or
 * family heading can reach the screen as a raw key.
 *
 * WHY THIS EXISTS (PLAN-account-sidebar-redesign, operator ruling on P8: "improve CI to catch
 * such issues"). check-account-i18n-key-usage.ts resolves every `t('<literal>')`, but a label
 * built from config is `t(item.labelKey)`: the key is a string in an object literal far from the
 * call, and that gate COUNTS it as dynamic and moves on. The new sidebar builds every label that
 * way (lib/nav-config.ts `NAV`), as do FAMILY_PAGES and the old AppSidebar arrays, so the class
 * that shipped seven raw offer labels would ship again through config with every gate green.
 *
 * THE THREE LAYERS (Design 7), and which one this file is:
 *   (a) `ui('<literal>')` in the offer builder: check-account-i18n-key-usage.ts.
 *   (b) THIS FILE. Every object-literal property in I18N_PROPS under web/src whose value is a
 *       string literal is resolved against web/src/i18n/locales/en/<ns>.json:
 *         - `'ns:key'`: exactly that namespace;
 *         - `'key'`: the namespaces the file binds with `useTranslation(...)` (bare means
 *           `common`), or EVERY namespace when the file binds none (a config module such as
 *           lib/resource-pages.ts), which still catches a key that exists nowhere;
 *         - a plural base resolves through `_one` / `_other` / ...
 *       A key that resolves in `nav` or `offerUi` (the two namespaces this plan created) must
 *       also exist in every locale directory, so a locale that lost one fails by name.
 *   (c) the rendered DOM: private/account/web/src/test/__tests__/raw-key-render.test.tsx,
 *       through the shared scanner src/test/raw-key-scan.ts, run by check:ci-test-account-web.
 *   scripts/__tests__/check-account-raw-keys.control.ts plants a raw key in each layer and
 *   requires each to fail; the package.json script runs it before this gate.
 *
 * WHAT IT CANNOT SEE, said out loud: a property whose value is not a string literal (a
 * variable, a ternary, a template) is COUNTED and printed, not guessed.
 *
 * THE ALLOWLIST is .ci/config/account-raw-key-allowlist.json, `{ "entries": [ { "string",
 * "surface", "reason" } ] }`. `surface` is a web/src-relative file for this layer or
 * `render:<name>` for layer (c). Every entry needs a reason starting `BLOCKER:` that passes the
 * shared quality validator (docs/agent-reference/suppressions.md). Liveness is IN-GATE: a
 * layer (b) entry that suppresses no finding fails as stale here, a `render:` entry must name a
 * surface in RENDER_SURFACES here and fails as stale in the render test. Every suppressed
 * finding is printed on every run.
 *
 * Usage:
 *   npx tsx scripts/gates/check-account-raw-keys.ts [--selftest]
 *   ACCOUNT_RAW_KEY_ALLOWLIST=<file>   read another allowlist (the control harness's seam)
 *   SUBMODULE_PRESENCE_ROOT=<dir>      read private/account from a mirror (the shared seam)
 *
 * ---- gate ----
 * step: Account raw i18n keys
 * needs: node, submodules
 * lane: quality-i18n
 * run: tsx scripts/__tests__/check-account-raw-keys.control.ts && tsx scripts/gates/check-account-raw-keys.ts
 * why: a label held in config (`t(item.labelKey)`) is invisible to the key-usage gate, so a
 *      missing nav or offer key would render raw with every gate green (P8, Design 7)
 * ---- end gate ----
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import { globSync } from 'glob';
import { type BlockerValidationFailure, validateBlockerQuality } from '../lib/blocker-validator.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { refuseFindings } from '../lib/findings-report.js';
import { REPO_ROOT } from '../lib/repo-root.js';
import { requireSubmodule, submodulePath } from '../lib/submodule-presence.js';
import { catalogsFrom } from './check-account-i18n-key-usage.js';
import { stripComments } from './check-translation-key-usage.js';

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };
type Catalogs = Map<string, Set<string>>;

/**
 * The properties that hold an i18n key. The four Design 7 names, plus the three FAMILY_PAGES
 * siblings (`navLabelKey`, `subtitleKey`, `emptyKey`) whose JSDoc says "i18n key". Deliberately
 * NOT every `*Key`: `primaryKey` and `pathKey` name a column and a contract path.
 */
export const I18N_PROPS = [
  'labelKey',
  'titleKey',
  'descKey',
  'placeholderKey',
  'navLabelKey',
  'subtitleKey',
  'emptyKey',
] as const;

/** Namespaces whose keys must exist in EVERY locale, not only en (Design 7 layer b). */
export const ALL_LOCALE_NAMESPACES = ['nav', 'offerUi'];

const DEFAULT_NS = 'common';
const PLURAL_SUFFIXES = ['_zero', '_one', '_two', '_few', '_many', '_other'];

export interface KeyProp {
  line: number;
  prop: string;
  key: string;
}

export interface PropScan {
  literals: KeyProp[];
  /** Properties in I18N_PROPS whose value is not a plain string literal. */
  dynamic: number;
}

/** Every I18N_PROPS property with a string-literal value; a type annotation is not a value. */
export function keyProps(raw: string): PropScan {
  const src = stripComments(raw);
  const lineOf = (idx: number) => src.slice(0, idx).split('\n').length;
  const literals: KeyProp[] = [];
  let dynamic = 0;
  const re = new RegExp(`(?<![\\w$.])(${I18N_PROPS.join('|')})\\s*:\\s*`, 'g');
  for (const m of src.matchAll(re)) {
    const at = (m.index ?? 0) + m[0].length;
    const rest = src.slice(at);
    const lit = /^(['"])([^'"\n]*)\1/.exec(rest);
    if (lit) {
      literals.push({ line: lineOf(m.index ?? 0), prop: m[1], key: lit[2] });
      continue;
    }
    // `labelKey: string;` and `labelKey?: string` in a type are declarations, not values.
    if (/^(?:string|LucideIcon|undefined|null)\b/.test(rest)) continue;
    dynamic++;
  }
  return { literals, dynamic };
}

/** The namespaces a file binds via `useTranslation(...)`, or null when it binds none. */
export function boundNamespaces(raw: string): string[] | null {
  const src = stripComments(raw);
  const out = new Set<string>();
  let any = false;
  for (const m of src.matchAll(/\buseTranslation\(([^)]*)\)/g)) {
    any = true;
    const names = [...m[1].matchAll(/['"]([\w-]+)['"]/g)].map((x) => x[1]);
    for (const n of names.length > 0 ? names : [DEFAULT_NS]) out.add(n);
  }
  return any ? [...out] : null;
}

function has(paths: Set<string> | undefined, key: string): boolean {
  if (!paths) return false;
  return paths.has(key) || PLURAL_SUFFIXES.some((s) => paths.has(`${key}${s}`));
}

export interface Resolution {
  /** The namespace the key resolved in, or null. */
  ns: string | null;
  key: string;
  searched: string[];
}

/** Resolve one config key against the en catalogs. */
export function resolveKey(literal: string, bound: string[] | null, en: Catalogs): Resolution {
  const colon = /^([\w-]+):(.+)$/.exec(literal);
  if (colon && en.has(colon[1])) {
    return {
      ns: has(en.get(colon[1]), colon[2]) ? colon[1] : null,
      key: colon[2],
      searched: [colon[1]],
    };
  }
  const searched = bound ?? [...en.keys()];
  for (const ns of searched) if (has(en.get(ns), literal)) return { ns, key: literal, searched };
  return { ns: null, key: literal, searched: bound ?? ['(every namespace)'] };
}

export interface Finding {
  file: string;
  line: number;
  key: string;
  message: string;
}

export interface Scan {
  findings: Finding[];
  checked: number;
  dynamic: number;
  localeChecks: number;
  filesWithKeys: number;
}

/** Layer (b) over a set of `{ rel, text }` sources. Pure, so the selftest drives it with fixtures. */
export function scanSources(
  sources: { rel: string; text: string }[],
  locales: Map<string, Catalogs>
): Scan {
  const en = locales.get('en');
  if (!en) throw new Error('the en locale is not loaded; nothing can be resolved');
  const scan: Scan = { findings: [], checked: 0, dynamic: 0, localeChecks: 0, filesWithKeys: 0 };
  for (const { rel, text } of sources) {
    const { literals, dynamic } = keyProps(text);
    scan.dynamic += dynamic;
    if (literals.length === 0) continue;
    scan.filesWithKeys++;
    const bound = boundNamespaces(text);
    for (const kp of literals) {
      scan.checked++;
      const r = resolveKey(kp.key, bound, en);
      if (!r.ns) {
        scan.findings.push({
          file: rel,
          line: kp.line,
          key: kp.key,
          message: `${kp.prop} '${kp.key}' resolves in no en namespace (looked in: ${r.searched.join(', ')})`,
        });
        continue;
      }
      if (!ALL_LOCALE_NAMESPACES.includes(r.ns)) continue;
      for (const [lang, cats] of locales) {
        if (lang === 'en') continue;
        scan.localeChecks++;
        if (!has(cats.get(r.ns), r.key)) {
          scan.findings.push({
            file: rel,
            line: kp.line,
            key: kp.key,
            message: `${kp.prop} '${kp.key}' is missing from locales/${lang}/${r.ns}.json`,
          });
        }
      }
    }
  }
  return scan;
}

// ---------------------------------------------------------------- allowlist

export interface AllowEntry {
  string: string;
  surface: string;
  reason: string;
}

export interface AllowVerdict {
  problems: string[];
  /** Findings left after the allowlist. */
  remaining: Finding[];
  /** Findings the allowlist suppressed, printed every run. */
  suppressed: { finding: Finding; entry: AllowEntry }[];
}

type ReasonCheck = (id: string, reason: string, file: string) => BlockerValidationFailure | null;

/** Lint the allowlist and apply its layer (b) entries. Pure apart from the injected reason check. */
export function applyAllowlist(
  raw: unknown,
  findings: Finding[],
  renderSurfaces: readonly string[],
  file: string,
  checkReason: ReasonCheck = validateBlockerQuality
): AllowVerdict {
  const problems: string[] = [];
  const entries: AllowEntry[] = [];
  const list = raw && typeof raw === 'object' ? (raw as { entries?: unknown }).entries : undefined;
  if (!Array.isArray(list)) {
    return {
      problems: [`${file}: expected { "entries": [ ... ] }`],
      remaining: findings,
      suppressed: [],
    };
  }
  const seen = new Set<string>();
  for (const [i, e] of list.entries()) {
    const ent = (e && typeof e === 'object' ? e : {}) as Partial<AllowEntry>;
    const id = `entries[${i}] ${JSON.stringify(ent.string ?? null)} @ ${ent.surface ?? '?'}`;
    if (
      typeof ent.string !== 'string' ||
      ent.string === '' ||
      typeof ent.surface !== 'string' ||
      ent.surface === ''
    ) {
      problems.push(`${file} ${id}: needs a non-empty "string" and "surface"`);
      continue;
    }
    const reason = typeof ent.reason === 'string' ? ent.reason.trim() : '';
    if (!reason.startsWith('BLOCKER:')) {
      problems.push(
        `${file} ${id}: "reason" must start with "BLOCKER:" and say why the key cannot be fixed today`
      );
      continue;
    }
    const bad = checkReason(id, reason.slice('BLOCKER:'.length).trim(), file);
    if (bad) {
      problems.push(bad.message);
      continue;
    }
    const dup = `${ent.surface}\u0000${ent.string}`;
    if (seen.has(dup)) {
      problems.push(`${file} ${id}: duplicate entry`);
      continue;
    }
    seen.add(dup);
    if (ent.surface.startsWith('render:') && !renderSurfaces.includes(ent.surface.slice(7))) {
      problems.push(
        `${file} ${id}: no render surface named '${ent.surface.slice(7)}' (known: ${renderSurfaces.join(', ')})`
      );
      continue;
    }
    entries.push({ string: ent.string, surface: ent.surface, reason });
  }
  const used = new Set<AllowEntry>();
  const remaining: Finding[] = [];
  const suppressed: AllowVerdict['suppressed'] = [];
  for (const f of findings) {
    const entry = entries.find((e) => e.surface === f.file && e.string === f.key);
    if (entry) {
      used.add(entry);
      suppressed.push({ finding: f, entry });
    } else remaining.push(f);
  }
  for (const e of entries) {
    if (!e.surface.startsWith('render:') && !used.has(e)) {
      problems.push(
        `${file}: STALE entry ${JSON.stringify(e.string)} @ ${e.surface} suppresses no finding; delete it`
      );
    }
  }
  return { problems, remaining, suppressed };
}

// ---------------------------------------------------------------- selftest

function fixtureLocales(): Map<string, Catalogs> {
  return new Map([
    [
      'en',
      catalogsFrom({
        common: { dashboardMenuItem: 'Dashboard', items_one: '1', items_other: 'n' },
        nav: { item: { settings: 'Settings', billing: 'Billing' }, user: { themeLight: 'Light' } },
        console: { datastoresTitle: 'Datastores' },
      }),
    ],
    [
      'de',
      catalogsFrom({
        common: { dashboardMenuItem: 'Übersicht' },
        nav: { item: { settings: 'Einstellungen' }, user: { themeLight: 'Hell' } },
        console: { datastoresTitle: 'Datenspeicher' },
      }),
    ],
  ]);
}

const okReason: ReasonCheck = () => null;

function controls(): ControlCase[] {
  const loc = fixtureLocales();
  const run = (text: string): string[] =>
    scanSources([{ rel: 'probe.ts', text }], loc).findings.map((f) => f.message);
  const cases: [string, string, (got: string[]) => boolean][] = [
    [
      'CONTROL: an unknown nav labelKey fires',
      "const NAV = [{ id: 'x', labelKey: 'nav:item.zzzMissing' }];",
      (g) => g.length === 1 && g[0].includes("'nav:item.zzzMissing' resolves in no en namespace"),
    ],
    [
      'CONTROL: a nav key present in en but missing from de fires naming the locale',
      "const NAV = [{ labelKey: 'nav:item.billing' }];",
      (g) => g.length === 1 && g[0].includes('missing from locales/de/nav.json'),
    ],
    [
      'CONTROL: a bare key outside the bound namespace fires',
      "const { t } = useTranslation('nav');\nconst X = [{ titleKey: 'datastoresTitle' }];",
      (g) => g.length === 1 && g[0].includes('looked in: nav'),
    ],
    [
      'CONTROL: a key in no namespace of an unbound config file fires',
      "export const P = [{ navLabelKey: 'zzzNowhere' }];",
      (g) => g.length === 1 && g[0].includes('(every namespace)'),
    ],
    [
      'CONTROL: double quotes are read too',
      'const X = [{ placeholderKey: "nav:zzz" }];',
      (g) => g.length === 1,
    ],
    [
      'SILENT: an ns-prefixed key present in every locale',
      "const NAV = [{ labelKey: 'nav:item.settings' }];",
      (g) => g.length === 0,
    ],
    [
      'SILENT: a bare key in the bound namespace (bare useTranslation binds common)',
      "const { t } = useTranslation();\nconst X = [{ titleKey: 'dashboardMenuItem' }];",
      (g) => g.length === 0,
    ],
    [
      'SILENT: an unbound config file resolves in any namespace',
      "export const P = [{ titleKey: 'datastoresTitle' }];",
      (g) => g.length === 0,
    ],
    [
      'SILENT: a plural base resolves through _one/_other',
      "const X = [{ labelKey: 'common:items' }];",
      (g) => g.length === 0,
    ],
    [
      'SILENT: a type annotation is not a value',
      'type T = { labelKey: string; titleKey?: string };',
      (g) => g.length === 0,
    ],
    [
      'SILENT: a property outside I18N_PROPS is ignored',
      "const C = { primaryKey: 'name', pathKey: 'a b' };",
      (g) => g.length === 0,
    ],
    [
      'SILENT: a key in a comment is not a value',
      "// labelKey: 'nav:zzz'\n",
      (g) => g.length === 0,
    ],
  ];
  const out: ControlCase[] = cases.map(([name, src, ok]) => {
    const got = run(src);
    return { name, ok: ok(got), detail: `got ${JSON.stringify(got)}` };
  });

  const dyn = keyProps('const a = { labelKey: item.labelKey, titleKey: `x.${y}` };');
  out.push({
    name: 'CONTROL: non-literal values are counted as dynamic, never resolved',
    ok: dyn.literals.length === 0 && dyn.dynamic === 2,
    detail: JSON.stringify(dyn),
  });
  const lined = keyProps("\n\nconst a = [\n  { labelKey: 'k' },\n];");
  out.push({
    name: 'CONTROL: the finding carries the source line',
    ok: lined.literals[0]?.line === 4,
    detail: JSON.stringify(lined),
  });

  const finding: Finding = { file: 'lib/x.ts', line: 3, key: 'nav:zzz', message: 'm' };
  const allow = (entries: unknown[], findings: Finding[] = [finding]) =>
    applyAllowlist({ entries }, findings, ['palette'], 'allow.json', okReason);
  const good = { string: 'nav:zzz', surface: 'lib/x.ts', reason: 'BLOCKER: a valid reason' };
  const v1 = allow([{ ...good, reason: 'the label ships next week' }]);
  out.push({
    name: 'CONTROL: an allowlist entry without a BLOCKER: reason fails',
    ok:
      v1.problems.some((p) => p.includes('must start with "BLOCKER:"')) &&
      v1.remaining.length === 1,
    detail: JSON.stringify(v1.problems),
  });
  const v2 = allow([good], []);
  out.push({
    name: 'CONTROL: an allowlist entry that matches nothing fails as stale',
    ok: v2.problems.some((p) => p.includes('STALE')),
    detail: JSON.stringify(v2.problems),
  });
  const v3 = allow([{ ...good, surface: 'render:nowhere' }], []);
  out.push({
    name: 'CONTROL: a render: entry naming an unknown surface fails',
    ok: v3.problems.some((p) => p.includes("no render surface named 'nowhere'")),
    detail: JSON.stringify(v3.problems),
  });
  const v4 = allow([good, good]);
  out.push({
    name: 'CONTROL: a duplicate entry fails',
    ok: v4.problems.some((p) => p.includes('duplicate')),
    detail: JSON.stringify(v4.problems),
  });
  const v5 = applyAllowlist({ entries: [good] }, [finding], [], 'allow.json', () => ({
    kind: 'too-short',
    normalized: 'x',
    message: 'reason too short',
  }));
  out.push({
    name: 'CONTROL: the shared BLOCKER quality validator is consulted',
    ok: v5.problems.includes('reason too short'),
    detail: JSON.stringify(v5.problems),
  });
  const v6 = allow([good]);
  out.push({
    name: 'SILENT: a valid entry suppresses its finding and stays visible as suppressed',
    ok: v6.problems.length === 0 && v6.remaining.length === 0 && v6.suppressed.length === 1,
    detail: JSON.stringify(v6),
  });
  const v7 = allow([{ ...good, surface: 'render:palette' }], []);
  out.push({
    name: 'SILENT: a render: entry on a known surface is left to the render test',
    ok: v7.problems.length === 0,
    detail: JSON.stringify(v7.problems),
  });
  out.push(
    { name: 'CONTROL: nothing scanned is vacuous', ok: isVacuous(0, 0, 0), detail: '' },
    {
      name: 'CONTROL: one key under the floor is vacuous',
      ok: isVacuous(MIN_FILES, MIN_KEYS - 1, MIN_LOCALE_CHECKS),
      detail: '',
    },
    {
      name: 'CONTROL: no locale check is vacuous',
      ok: isVacuous(MIN_FILES, MIN_KEYS, 0),
      detail: '',
    },
    {
      name: 'SILENT: exactly at the floors is not vacuous',
      ok: !isVacuous(MIN_FILES, MIN_KEYS, MIN_LOCALE_CHECKS),
      detail: '',
    }
  );
  return out;
}

// VACUITY FLOORS, measured 2026-11-19 on the landed tree (see the success line for today's
// numbers): the floors sit well below it, so a refactor never trips them, and far above zero,
// so a glob or a property regex that goes blind cannot pass as a clean tree.
const MIN_FILES = 3;
const MIN_KEYS = 40;
const MIN_LOCALE_CHECKS = 100;

export function isVacuous(files: number, keys: number, localeChecks: number): boolean {
  return files < MIN_FILES || keys < MIN_KEYS || localeChecks < MIN_LOCALE_CHECKS;
}

function loadLocales(dir: string): Map<string, Catalogs> {
  const out = new Map<string, Catalogs>();
  for (const lang of readdirSync(dir, { withFileTypes: true })) {
    if (!lang.isDirectory()) continue;
    const raw: Record<string, Json> = {};
    for (const f of readdirSync(path.join(dir, lang.name))) {
      if (f.endsWith('.json'))
        raw[f.slice(0, -5)] = JSON.parse(
          readFileSync(path.join(dir, lang.name, f), 'utf8')
        ) as Json;
    }
    out.set(lang.name, catalogsFrom(raw));
  }
  return out;
}

async function main(): Promise<void> {
  console.log('account-raw-keys controls');
  if (summarizeControls(controls()) !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }
  if (process.argv.includes('--selftest')) process.exit(0);

  const webSrc = submodulePath('private/account/web/src');
  const localesDir = path.join(webSrc, 'i18n/locales');
  const scannerFile = path.join(webSrc, 'test/raw-key-scan.ts');
  if (!requireSubmodule('account portal raw i18n keys', [path.join(localesDir, 'en'), scannerFile]))
    process.exit(0);

  const locales = loadLocales(localesDir);
  const files = globSync('**/*.{ts,tsx}', {
    cwd: webSrc,
    absolute: true,
    ignore: ['**/__tests__/**', '**/*.test.ts', '**/*.test.tsx', '**/*.d.ts', 'test/**'],
  });
  const scan = scanSources(
    files.map((f) => ({ rel: path.relative(webSrc, f), text: readFileSync(f, 'utf8') })),
    locales
  );
  if (isVacuous(scan.filesWithKeys, scan.checked, scan.localeChecks)) {
    console.error(
      `${RED}✗${NC} VACUOUS: ${scan.checked} config key(s) in ${scan.filesWithKeys} file(s), ${scan.localeChecks} locale check(s); floors ${MIN_KEYS}, ${MIN_FILES} and ${MIN_LOCALE_CHECKS}. The gate is not seeing the tree, so its green would mean nothing.`
    );
    process.exit(1);
  }

  const { RENDER_SURFACES } = (await import(pathToFileURL(scannerFile).href)) as {
    RENDER_SURFACES: readonly string[];
  };
  const allowFile = process.env.ACCOUNT_RAW_KEY_ALLOWLIST
    ? path.resolve(process.env.ACCOUNT_RAW_KEY_ALLOWLIST)
    : path.join(REPO_ROOT, '.ci/config/account-raw-key-allowlist.json');
  if (!existsSync(allowFile)) {
    console.error(
      `${RED}✗${NC} ${allowFile} is missing; it must exist, even with no entries ({ "entries": [] }).`
    );
    process.exit(1);
  }
  const allowRel = path.relative(REPO_ROOT, allowFile);
  const verdict = applyAllowlist(
    JSON.parse(readFileSync(allowFile, 'utf8')),
    scan.findings,
    RENDER_SURFACES,
    allowRel
  );
  for (const { finding, entry } of verdict.suppressed) {
    console.log(
      `${YELLOW}!${NC} allowlisted: web/src/${finding.file}:${finding.line}: ${finding.message} -- ${entry.reason}`
    );
  }
  const shape = `${scan.checked} config key(s) in ${scan.filesWithKeys} file(s) resolved, ${scan.localeChecks} nav/offerUi locale check(s) across ${locales.size} locale(s), ${scan.dynamic} non-literal value(s) not statically checkable, ${verdict.suppressed.length} allowlisted.`;
  const items = [
    ...verdict.problems,
    ...verdict.remaining.map((f) => `web/src/${f.file}:${f.line}: ${f.message}`),
  ];
  if (items.length > 0) {
    refuseFindings({
      header: `\n${RED}✗${NC} ${items.length} raw-key problem(s) in the account portal's config keys or ${allowRel}:\n`,
      items,
      limit: 60,
      remedy: [
        `\n${shape}`,
        'A config key that resolves nowhere renders as the raw key. Add it to locales/en/<ns>.json and the 12 other locales (naturalized, docs/i18n/CONVENTIONS.md), or correct the literal. Do not add it to the allowlist.',
      ],
    });
  }
  console.log(`${GREEN}✓${NC} ${shape}`);
}

if (isEntryPoint(import.meta.filename)) await main();
