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

/** The .d.ts tuple must list exactly what index.js exports, or the types lie. */
function checkDeclarationMatchesSource(root: string): string | null {
  const js = path.join(root, 'packages/locales/index.js');
  const dts = path.join(root, 'packages/locales/index.d.ts');
  if (!fs.existsSync(js) || !fs.existsSync(dts)) return null;
  const grab = (p: string) => {
    const t = fs.readFileSync(p, 'utf-8');
    const m = t.match(/SITE_LOCALES[^[]*\[([^\]]*)\]/);
    return m ? [...m[1].matchAll(/['"]([a-z]{2})['"]/g)].map((x) => x[1]) : [];
  };
  const a = grab(js);
  const b = grab(dts);
  if (a.length === 0 || b.length === 0) return null;
  return a.join(',') === b.join(',')
    ? null
    : `packages/locales/index.d.ts tuple [${b}] does not match index.js [${a}]`;
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
  const mismatch = checkDeclarationMatchesSource(root);

  if (findings.length === 0 && !mismatch) {
    console.log(`✓ No stray locale lists across ${files.length} file(s); index.d.ts matches index.js.`);
    return;
  }
  if (mismatch) console.error(`✗ ${mismatch}`);
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
