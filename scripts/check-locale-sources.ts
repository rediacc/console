#!/usr/bin/env tsx
/**
 * One source for the site's locale set, enforced.
 *
 * Before `packages/locales` existed there were 31 hand-maintained copies of the locale
 * list in the console tree, in five different orderings, plus more in the submodules. They
 * drifted: eslint carried 8, two media gates carried 10, `VIDEO_LANGS` carried 11, and
 * nothing could tell a deliberate subset from a stale copy. This gate stops that
 * reappearing — without it, the consolidation lasts exactly until the next person hardcodes
 * a list.
 *
 * WHAT IT FLAGS: an array literal of >= MIN_CODES site-locale codes, declared anywhere
 * outside the allowlist. Deliberate subsets are fine, but they must be built with
 * `subset()` from `@rediacc/locales`, which throws on an unknown code — a hardcoded literal
 * cannot make that promise.
 *
 * Usage:
 *   tsx scripts/check-locale-sources.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const SITE_CODES = new Set([
  'en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh', 'et', 'ko', 'pt', 'it',
]);

/** An array of at least this many locale codes is a locale LIST, not a coincidence. */
const MIN_CODES = 5;

/**
 * Files allowed to declare a locale list, each with the reason. Anything not here must
 * import from `@rediacc/locales`.
 */
const ALLOWED: Array<{ file: string; reason: string }> = [
  { file: 'packages/locales/index.js', reason: 'THE source of truth' },
  { file: 'packages/locales/index.d.ts', reason: 'hand-written literal tuple; the gate checks it matches index.js' },
  {
    file: 'packages/shared/src/i18n/types.ts',
    reason:
      'the ONE deliberate copy: private/account/Dockerfile compiles this package in isolation ' +
      'with no workspace context, so it cannot depend on an unpublished workspace package',
  },
  {
    file: 'packages/www/src/i18n/types.ts',
    reason: 'LANGUAGES is a presentation ORDER, not a set; a compile-time assertion proves it is a permutation',
  },
  {
    file: 'scripts/check-locale-sources.ts',
    reason: 'this gate needs the codes to recognise a locale list at all',
  },
  {
    file: 'scripts/check-i18n-cross-locale.ts',
    reason: 'per-language stopword tables, keyed by locale but not a locale set',
  },
];

type Finding = { file: string; line: number; codes: string[] };

export function findStrayLocaleLists(root: string, files: string[]): Finding[] {
  const allowed = new Set(ALLOWED.map((a) => a.file));
  const findings: Finding[] = [];
  // Array literals only. A `Set([...])` or a call argument is caught by the same shape.
  const arrayRe = /\[[^\][]*\]/g;

  for (const rel of files) {
    if (allowed.has(rel)) continue;
    // Generated artifacts are derived from a real source; policing the output instead of
    // the generator just teaches people to edit generated files.
    if (/\.generated\.|\/generated\//.test(rel)) continue;
    const abs = path.join(root, rel);
    let text: string;
    try {
      text = fs.readFileSync(abs, 'utf-8');
    } catch {
      continue;
    }
    if (!text.includes("'en'") && !text.includes('"en"')) continue; // cheap pre-filter

    for (const m of text.matchAll(arrayRe)) {
      const codes = [...m[0].matchAll(/['"]([a-z]{2})['"]/g)].map((x) => x[1]);
      const uniq = [...new Set(codes)];
      if (uniq.length < MIN_CODES) continue;
      if (!uniq.every((c) => SITE_CODES.has(c))) continue;
      // A literal handed to subset() is the SANCTIONED form — subset() throws on an
      // unknown code, which is the whole guarantee this gate is asking for. Flagging it
      // would condemn the exact pattern the error message recommends. Same for the
      // `as readonly [...]` tuple that types such a call.
      const before = text.slice(Math.max(0, (m.index ?? 0) - 120), m.index);
      if (/\bsubset\s*\(\s*['"][^'"]*['"]\s*,\s*$/.test(before)) continue;
      if (/\bas\s+readonly\s*$/.test(before)) continue;
      findings.push({
        file: rel,
        line: text.slice(0, m.index).split('\n').length,
        codes: uniq,
      });
    }
  }
  return findings;
}

/**
 * All THREE declarations of the locale list must agree, in the same order.
 *
 * `index.js` holds the literal, `index.d.ts` restates it as a tuple for the type system, and
 * `site-locales.json` is the copy that non-JS consumers read — `packages/locales/site_locales.py`
 * loads it for the Python pipelines, which live in gitignored trees and cannot import the JS.
 *
 * The JSON was previously unchecked, so JS and Python could silently disagree about which
 * languages the site ships. That is the same drift this whole gate exists to prevent, one
 * level up: a consolidation that leaves its own sources unpoliced has just relocated the bug.
 */
function checkDeclarationMatchesSource(root: string): string[] {
  const js = path.join(root, 'packages/locales/index.js');
  const dts = path.join(root, 'packages/locales/index.d.ts');
  const json = path.join(root, 'packages/locales/site-locales.json');
  if (!fs.existsSync(js) || !fs.existsSync(dts)) return [];
  const grab = (p: string) => {
    const t = fs.readFileSync(p, 'utf-8');
    const m = t.match(/SITE_LOCALES[^[]*\[([^\]]*)\]/);
    return m ? [...m[1].matchAll(/['"]([a-z]{2})['"]/g)].map((x) => x[1]) : [];
  };
  const a = grab(js);
  const b = grab(dts);
  if (a.length === 0 || b.length === 0) return [];

  const problems: string[] = [];
  if (a.join(',') !== b.join(',')) {
    problems.push(`packages/locales/index.d.ts tuple [${b}] does not match index.js [${a}]`);
  }
  if (!fs.existsSync(json)) {
    problems.push(
      'packages/locales/site-locales.json is MISSING. site_locales.py reads it, so every ' +
        'Python pipeline would fail at import.'
    );
    return problems;
  }
  let parsed: { siteLocales?: unknown; defaultLocale?: unknown };
  try {
    parsed = JSON.parse(fs.readFileSync(json, 'utf-8'));
  } catch (e) {
    problems.push(`packages/locales/site-locales.json is not valid JSON: ${String(e)}`);
    return problems;
  }
  const c = Array.isArray(parsed.siteLocales) ? parsed.siteLocales.map(String) : [];
  if (c.join(',') !== a.join(',')) {
    problems.push(
      `packages/locales/site-locales.json [${c}] does not match index.js [${a}]. ` +
        'The Python pipelines read the JSON and the site reads index.js, so they now ship ' +
        'different locale sets.'
    );
  }
  if (parsed.defaultLocale !== 'en') {
    problems.push(
      `packages/locales/site-locales.json defaultLocale is ${JSON.stringify(parsed.defaultLocale)}, ` +
        'expected "en" (NON_ENGLISH_LOCALES is derived by removing it).'
    );
  }
  return problems;
}

function trackedFiles(root: string): string[] {
  const out = execFileSync(
    'git',
    ['ls-files', '--cached', '--others', '--exclude-standard', '*.ts', '*.js', '*.tsx', '*.mjs'],
    { cwd: root, encoding: 'utf-8', maxBuffer: 32 * 1024 * 1024 }
  );
  return out.split('\n').filter((f) => f && !f.includes('node_modules') && !f.includes('/locales/'));
}

function selftest(): void {
  const failures: string[] = [];
  const check = (name: string, actual: unknown, expected: unknown) => {
    if (JSON.stringify(actual) === JSON.stringify(expected)) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}\n        expected ${JSON.stringify(expected)}\n        got      ${JSON.stringify(actual)}`);
      failures.push(name);
    }
  };
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'locale-src-'));
  const w = (rel: string, body: string) => {
    fs.mkdirSync(path.join(root, path.dirname(rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), body);
  };

  w('src/stray.ts', "const L = ['en','de','es','fr','ja','ar'];\n");
  check(
    'a stray 6-code list is reported',
    findStrayLocaleLists(root, ['src/stray.ts']).map((f) => f.file),
    ['src/stray.ts']
  );

  // Control: a short list is a coincidence, not a locale set.
  w('src/short.ts', "const PAIR = ['en','de'];\n");
  check('a 2-code list is NOT reported (control)', findStrayLocaleLists(root, ['src/short.ts']).length, 0);

  // Control: codes that are not site locales are somebody else's enum.
  w('src/other.ts', "const X = ['aa','bb','cc','dd','ee','ff'];\n");
  check('non-locale codes are NOT reported (control)', findStrayLocaleLists(root, ['src/other.ts']).length, 0);

  // Control: importing the real source is the point, and must be clean.
  w('src/good.ts', "import { SITE_LOCALES } from '@rediacc/locales';\nconst L = SITE_LOCALES;\n");
  check('importing the source is NOT reported (control)', findStrayLocaleLists(root, ['src/good.ts']).length, 0);

  // Control: an allowlisted file is exempt.
  w('packages/shared/src/i18n/types.ts', "const L = ['en','de','es','fr','ja','ar'];\n");
  check(
    'an allowlisted file is exempt (control)',
    findStrayLocaleLists(root, ['packages/shared/src/i18n/types.ts']).length,
    0
  );

  // Control: a literal passed to subset() is the SANCTIONED form and must be exempt —
  // without this the gate condemns the exact pattern its own error message recommends.
  w('src/sub.ts', "const NIS2 = subset('nis2', ['en','de','es','fr','et','it','pt']);\n");
  check('a subset() literal is NOT reported (control)', findStrayLocaleLists(root, ['src/sub.ts']).length, 0);

  // Control: generated artifacts are policed at their generator, not their output.
  w('src/thing.generated.ts', "const L = ['en','de','es','fr','ja','ar'];\n");
  check(
    'a .generated. file is NOT reported (control)',
    findStrayLocaleLists(root, ['src/thing.generated.ts']).length,
    0
  );

  // ---- the three-way source agreement (index.js / index.d.ts / site-locales.json) ----
  // Each case writes a fresh locale package into its own temp root, so a perturbation cannot
  // leak into the next case or into the real repo.
  const threeWay = (
    name: string,
    jsCodes: string[],
    dtsCodes: string[],
    jsonBody: string | null,
    expectMatch: RegExp | null
  ) => {
    const r = fs.mkdtempSync(path.join(os.tmpdir(), 'locale-3way-'));
    fs.mkdirSync(path.join(r, 'packages/locales'), { recursive: true });
    const lit = (c: string[]) => c.map((x) => `'${x}'`).join(', ');
    fs.writeFileSync(
      path.join(r, 'packages/locales/index.js'),
      `export const SITE_LOCALES = [${lit(jsCodes)}];\n`
    );
    fs.writeFileSync(
      path.join(r, 'packages/locales/index.d.ts'),
      `export declare const SITE_LOCALES: readonly [${lit(dtsCodes)}];\n`
    );
    if (jsonBody !== null) {
      fs.writeFileSync(path.join(r, 'packages/locales/site-locales.json'), jsonBody);
    }
    const got = checkDeclarationMatchesSource(r);
    if (expectMatch === null) check(name, got, []);
    else {
      const hit = got.some((g) => expectMatch.test(g));
      if (hit) console.log(`  PASS  ${name}`);
      else {
        console.error(`  FAIL  ${name}\n        expected /${expectMatch.source}/\n        got      ${JSON.stringify(got)}`);
        failures.push(name);
      }
    }
    fs.rmSync(r, { recursive: true, force: true });
  };

  const THREE = ['en', 'de', 'es'];
  const okJson = JSON.stringify({ siteLocales: THREE, defaultLocale: 'en' });

  // Control: all three agreeing must report NOTHING. If this ever fails, every other case
  // below is meaningless because the check would be firing unconditionally.
  threeWay('all three sources agreeing report nothing (control)', THREE, THREE, okJson, null);
  threeWay(
    'site-locales.json disagreeing with index.js is caught',
    THREE,
    THREE,
    JSON.stringify({ siteLocales: ['en', 'de'], defaultLocale: 'en' }),
    /site-locales\.json .* does not match index\.js/
  );
  threeWay(
    'a mere ORDER difference in the JSON is caught',
    THREE,
    THREE,
    JSON.stringify({ siteLocales: ['en', 'es', 'de'], defaultLocale: 'en' }),
    /site-locales\.json .* does not match index\.js/
  );
  threeWay(
    'index.d.ts disagreeing with index.js is caught',
    THREE,
    ['en', 'de'],
    okJson,
    /index\.d\.ts tuple .* does not match index\.js/
  );
  threeWay(
    'a missing site-locales.json is caught',
    THREE,
    THREE,
    null,
    /site-locales\.json is MISSING/
  );
  threeWay(
    'malformed JSON is caught, not thrown',
    THREE,
    THREE,
    '{ this is not json',
    /not valid JSON/
  );
  threeWay(
    'a non-en defaultLocale is caught',
    THREE,
    THREE,
    JSON.stringify({ siteLocales: THREE, defaultLocale: 'de' }),
    /defaultLocale is "de"/
  );

  fs.rmSync(root, { recursive: true, force: true });
  if (failures.length) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    process.exit(1);
  }
  console.log('\n✓ check-locale-sources self-test passed');
}

function main(): void {
  const argv = process.argv.slice(2);
  if (argv.includes('--selftest')) return selftest();
  const i = argv.indexOf('--root');
  const root = i >= 0 ? path.resolve(argv[i + 1]) : REPO_ROOT;

  const files = trackedFiles(root);
  // Refuse on an empty scan: a gate that reports "all clear" over nothing is worse than
  // no gate, because it reads as a pass. (anti-vacuity root pattern 1)
  if (files.length < 50) {
    console.error(`✗ Refusing to run: only ${files.length} source file(s) found under ${root}.`);
    process.exit(1);
  }

  const findings = findStrayLocaleLists(root, files);
  const mismatches = checkDeclarationMatchesSource(root);

  if (findings.length === 0 && mismatches.length === 0) {
    console.log(
      `✓ No stray locale lists across ${files.length} file(s); index.js, index.d.ts and ` +
        `site-locales.json all agree.`
    );
    return;
  }
  for (const m of mismatches) console.error(`✗ ${m}`);
  if (findings.length) {
    console.error(`✗ ${findings.length} hardcoded locale list(s) outside packages/locales:\n`);
    for (const f of findings) console.error(`  ${f.file}:${f.line}  [${f.codes.join(',')}]`);
    console.error(
      '\nImport SITE_LOCALES (or NON_ENGLISH_LOCALES) from @rediacc/locales. For a deliberate\n' +
        'subset use subset(name, codes), which throws on an unknown code — a hardcoded literal\n' +
        'cannot. If the file genuinely must declare its own, add it to ALLOWED with the reason.'
    );
  }
  process.exit(1);
}

main();
