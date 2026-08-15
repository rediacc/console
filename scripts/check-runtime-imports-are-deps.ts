/**
 * check:ci-runtime-imports-are-deps — a package imported by RUNTIME code must
 * be a dependency, not a devDependency.
 *
 * The class this catches, found 2026-08-14: `@aws-sdk/client-s3` sat in
 * private/account's devDependencies while two runtime services imported it
 * (blob-storage.service.ts and backup-chunk-store.ts, both via dynamic import
 * inside request handling). Its own sibling `@aws-sdk/s3-request-presigner`,
 * used in the SAME function, was correctly a dependency. So a production
 * install lost the client and kept the presigner, and the first presign would
 * fail at runtime with a module-not-found.
 *
 * Why nothing caught it: typecheck, lint and the whole test suite all run with
 * devDependencies installed, so every local signal is green. `check:deps`
 * exists but answers a different question (are versions current). The defect is
 * only visible to an install nobody performs locally:
 *   npm ls @aws-sdk/client-s3 --omit=dev   ->  (empty)
 *
 * The rule enforced: for each package with a src/ tree, every bare package
 * specifier imported from a non-test source file must appear in that package's
 * `dependencies` (or be a workspace/builtin/type-only import). devDependencies
 * are for things the BUILD needs, not things the running process needs.
 *
 * Run: npx tsx scripts/check-runtime-imports-are-deps.ts
 *
 * Control-first: every run first proves the detector on a synthetic runtime
 * import that resolves only to a devDependency, and refuses to pass an empty
 * scan.
 */

import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/**
 * Packages scanned: ONLY those whose code is loaded from node_modules at
 * runtime, because that is the only place the distinction bites.
 *
 * private/account qualifies and is the reason this gate exists: its
 * package.json has `build: tsc` and `start: node dist/entry/node.js`, so there
 * is NO bundler and every import resolves from node_modules at run time.
 *
 * packages/cli is deliberately EXCLUDED. It ships as an esbuild bundle
 * (cli-bundle.cjs, then a Node SEA), so nothing is installed beside it and its
 * runtime imports are correctly devDependencies. An earlier draft of this gate
 * scanned it and produced 211 findings, every one a false positive: a gate that
 * would force a bundled package to relabel its whole dependency tree is a gate
 * that gets deleted, not obeyed.
 *
 * packages/shared is excluded for the opposite reason: it is a LIBRARY, so its
 * dependencies are resolved by whoever installs it, and that package's own
 * manifest is the thing under test there, not this one.
 */
const TARGETS = ['private/account'];

/** A scan that finds fewer imports than this means the globs broke. */
const MIN_IMPORTS = 200;

/**
 * Import specifiers that are legitimately absent from `dependencies`.
 * Each needs a reason; this is not a place to silence a real finding.
 */
const ALLOWED: Record<string, string> = {
  // Node builtins are provided by the runtime.
  node: 'node: builtin protocol',
};

interface Finding {
  pkg: string;
  spec: string;
  file: string;
}

/** Bare specifier from an import/require/dynamic-import, package name only. */
const IMPORT_RE =
  /(?:^|\s)(?:import|export)\s+(?:type\s+)?[^;'"]*from\s*['"]([^'"]+)['"]|(?:^|\s)import\s*\(\s*['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]/gm;

/** `@scope/name` or `name`, dropping any subpath. */
function packageOf(spec: string): string | null {
  if (spec.startsWith('.') || spec.startsWith('/')) return null;
  if (spec.startsWith('node:')) return null;
  const parts = spec.split('/');
  return spec.startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0];
}

/** Type-only imports never reach the runtime. */
function isTypeOnly(line: string): boolean {
  return /^\s*(?:import|export)\s+type\s/.test(line);
}

function scan(pkgDir: string): Finding[] {
  return scanIn(ROOT, pkgDir);
}

function scanIn(root: string, pkgDir: string): Finding[] {
  const pkgPath = join(root, pkgDir, 'package.json');
  if (!existsSync(pkgPath)) return [];
  const pkg = JSON.parse(readFileSync(pkgPath, 'utf8')) as {
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
  };
  const deps = new Set(Object.keys(pkg.dependencies ?? {}));
  const devDeps = new Set(Object.keys(pkg.devDependencies ?? {}));

  const out: Finding[] = [];
  const files = globSync(`${pkgDir}/src/**/*.{ts,tsx}`, { cwd: root, absolute: false });
  for (const file of files) {
    if (/__tests__|\.test\.|\.spec\./.test(file)) continue;
    const text = readFileSync(join(root, file), 'utf8');
    for (const m of text.matchAll(IMPORT_RE)) {
      const spec = m[1] ?? m[2] ?? m[3];
      if (!spec) continue;
      const line = text.slice(text.lastIndexOf('\n', m.index ?? 0) + 1, (m.index ?? 0) + m[0].length);
      if (isTypeOnly(line)) continue;
      const name = packageOf(spec);
      if (!name || name in ALLOWED) continue;
      // Only a devDependency: that is the defect. Unlisted entirely is a
      // different problem (a hoisted or transitive import) and is out of scope
      // here, because this gate is about MISFILING, not about completeness.
      if (devDeps.has(name) && !deps.has(name)) {
        out.push({ pkg: pkgDir, spec: name, file });
      }
    }
  }
  return out;
}

// ── Control: the REAL detector, on a real fixture, in both directions ──────
// An earlier draft asserted that a hardcoded one-element array had length one,
// which is a control that cannot fail. It is exactly the decoration this repo
// keeps finding, so it is written out here: the control builds an actual
// package on disk and runs scan() over it.
{
  const tmp = mkdtempSync(join(tmpdir(), 'runtime-deps-control-'));
  try {
    const pkgDir = join(tmp, 'ctl');
    mkdirSync(join(pkgDir, 'src'), { recursive: true });
    writeFileSync(
      join(pkgDir, 'package.json'),
      JSON.stringify({
        dependencies: { 'ctl-runtime-ok': '1' },
        devDependencies: { 'ctl-dev-only': '1', 'ctl-types-only': '1' },
      })
    );
    writeFileSync(
      join(pkgDir, 'src', 'a.ts'),
      [
        "import { x } from 'ctl-dev-only';", // MUST be reported
        "import { y } from 'ctl-runtime-ok';", // correctly a dependency
        "import type { T } from 'ctl-types-only';", // type-only, never at runtime
        "import { z } from './local.js';", // relative
        "import { readFileSync } from 'node:fs';", // builtin
      ].join('\n')
    );
    // scan() resolves against ROOT, so point it at the fixture for this call.
    const found = scanIn(tmp, 'ctl');
    const names = found.map((f) => f.spec);
    if (!names.includes('ctl-dev-only')) {
      console.error(
        '✗ instrument control did not fire: a runtime import of a devDependency\n' +
          '  was not reported, so a green run below would mean nothing.'
      );
      process.exit(1);
    }
    if (names.includes('ctl-runtime-ok') || names.includes('ctl-types-only')) {
      console.error(
        `✗ instrument control over-reports (${names.join(', ')}): a correct dependency\n` +
          '  or a type-only import was flagged, so every package would fail forever.'
      );
      process.exit(1);
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

const findings: Finding[] = [];
let importCount = 0;
for (const target of TARGETS) {
  const files = globSync(`${target}/src/**/*.{ts,tsx}`, { cwd: ROOT, absolute: false });
  for (const f of files) {
    if (/__tests__|\.test\.|\.spec\./.test(f)) continue;
    importCount += [...readFileSync(join(ROOT, f), 'utf8').matchAll(IMPORT_RE)].length;
  }
  findings.push(...scan(target));
}

if (importCount < MIN_IMPORTS) {
  console.error(
    `✗ only ${importCount} imports scanned (floor ${MIN_IMPORTS}).\n` +
      '  The globs broke; an unrun check is not a pass.'
  );
  process.exit(1);
}

if (findings.length > 0) {
  const rows = findings.map(
    (f) =>
      `    ${f.pkg}: ${f.spec}\n` +
      `      imported at runtime by ${f.file}, but listed only in devDependencies`
  );
  console.error(
    `✗ runtime imports filed as devDependencies (${findings.length}):\n${rows.join('\n')}\n\n` +
      '  Typecheck, lint and tests all install devDependencies, so every local\n' +
      '  signal stays green while a production install lacks the package. Confirm\n' +
      '  with `npm ls <pkg> --omit=dev` and move it to dependencies.'
  );
  process.exit(1);
}

console.log(
  `✓ runtime imports are dependencies ` +
    `(${importCount} imports across ${TARGETS.length} package(s); control fired)`
);
