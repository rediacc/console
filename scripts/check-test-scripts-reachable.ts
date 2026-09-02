/**
 * check:ci-test-scripts-reachable — every package's test suite is either RUN by
 * CI or DOCUMENTED as a deliberate omission. Never neither.
 *
 * THE CLASS THIS CATCHES, and it has bitten four times in this repo:
 *
 *   - `private/account/web`: the gate ran 1 of its 34 test files. The other 33
 *     could go red while CI stayed green.
 *   - `packages/www`: 2 files, 27 tests, invoked by nothing at all.
 *   - `packages/shared`: run by CI but absent from the local gate manifest, so
 *     `npm run ci` never ran it. Wiring it immediately caught a REAL break — a
 *     pinned count that a new command had silently moved.
 *   - `packages/json`: 28 Rediaccfile templates, run by nothing, and it cannot
 *     be wired today because every template needs a licensed rediacc repo on a
 *     VM.
 *
 * An unrun suite reads exactly like a passing one. That is the whole problem:
 * nothing goes red, no one is told, and the coverage is imaginary.
 *
 * THE RULE. For each package with a `test`/`test:*` script, ONE of:
 *   (a) something in .github/workflows or .ci/scripts or the ci-runner manifest
 *       names that package, so CI can reach it; or
 *   (b) the package is named in the "Deliberately not in CI" section of
 *       packages/e2e-tests/README.md, which is this repo's single discoverable
 *       index of intentional omissions (the rediacc/console#521 CI-visibility
 *       requirement).
 *
 * Deliberately NOT asserted here: that the CI reference actually executes the
 * suite. Proving execution needs a trace, and this gate is a REACHABILITY floor,
 * not a substitute for reading the chain — the account suite is invoked three
 * hops deep and the word `vitest` appears nowhere on that path, which is exactly
 * how a name-based grep produced a WRONG finding earlier in this program. What
 * this gate guarantees is narrower and still worth having: a package's tests
 * cannot be invisible to BOTH CI and the omissions record.
 *
 * Run: npx tsx scripts/check-test-scripts-reachable.ts
 *
 * Control-first: every run proves the detector on a synthetic package that is
 * neither referenced nor documented, and refuses a scan that read nothing.
 */

import { readFileSync } from 'node:fs';
import { refuse } from './lib/controls';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/** Where a package may be REFERENCED such that CI could reach it. */
const CI_SURFACES = [
  '.github/workflows/*.yml',
  '.ci/scripts/**/*.sh',
  '.ci/scripts/**/*.cjs',
  '.ci/scripts/**/*.py',
  'scripts/ci-runner/manifest.ts',
  'package.json',
];

/** The repo's single index of intentional omissions. */
const OMISSIONS_DOC = 'packages/e2e-tests/README.md';
const OMISSIONS_HEADING = '## Deliberately not in CI';

/** Package manifests to consider. The root workspace is not a package. */
const PACKAGE_GLOBS = [
  'packages/*/package.json',
  'private/account/package.json',
  'private/account/web/package.json',
  'workers/*/package.json',
];

/** A scan finding fewer than this many packages means the globs broke. */
const MIN_PACKAGES = 6;

interface Pkg {
  name: string;
  dir: string;
  scripts: string[];
}

function packagesWithTests(root: string, globs: string[]): Pkg[] {
  const out: Pkg[] = [];
  for (const pattern of globs) {
    for (const rel of globSync(pattern, { cwd: root, absolute: false })) {
      let json: { name?: string; scripts?: Record<string, string> };
      try {
        json = JSON.parse(readFileSync(join(root, rel), 'utf8'));
      } catch {
        continue;
      }
      const scripts = Object.keys(json.scripts ?? {}).filter(
        (k) => k === 'test' || k.startsWith('test:')
      );
      // `test:watch` alone is a developer convenience, not a suite.
      const real = scripts.filter((s) => !s.endsWith(':watch'));
      if (real.length === 0 || !json.name) continue;
      out.push({ name: json.name, dir: rel.replace(/\/package\.json$/, ''), scripts: real });
    }
  }
  return out;
}

/**
 * Lines across the CI surfaces that plausibly INVOKE a test, not merely mention
 * a package.
 *
 * The first draft of this gate collected the whole text and asked whether it
 * contained the package name. That does not fire: the root package.json says
 * `npm run build -w @rediacc/json`, so a package CI merely BUILDS counted as
 * test-reachable, and removing packages/json's omission entry left the gate
 * green. A gate that cannot fail on the exact shape it was written for is the
 * trap this repo keeps paying for, so the reference now has to look like a
 * test.
 */
const TEST_TOKEN = /\btest\b|test:|vitest|playwright|gotestsum|drill|spec\b/i;

function ciTestLines(root: string, globs: string[]): string[] {
  const lines: string[] = [];
  for (const pattern of globs) {
    for (const rel of globSync(pattern, { cwd: root, absolute: false })) {
      let text: string;
      try {
        text = readFileSync(join(root, rel), 'utf8');
      } catch {
        continue; // unreadable file is simply not a reference
      }
      for (const line of text.split('\n')) {
        if (TEST_TOKEN.test(line)) lines.push(line);
      }
    }
  }
  return lines;
}

function omissionsSection(root: string): string {
  try {
    const doc = readFileSync(join(root, OMISSIONS_DOC), 'utf8');
    const i = doc.indexOf(OMISSIONS_HEADING);
    if (i === -1) return '';
    // To the next top-level heading, so a mention elsewhere in the file does
    // NOT count as a documented omission.
    const rest = doc.slice(i + OMISSIONS_HEADING.length);
    const end = rest.indexOf('\n## ');
    return end === -1 ? rest : rest.slice(0, end);
  } catch {
    return '';
  }
}

function unreachable(root: string, pkgs: Pkg[]): Pkg[] {
  const ci = ciTestLines(root, CI_SURFACES);
  const omitted = omissionsSection(root);
  return pkgs.filter(
    (p) => !ci.some((l) => l.includes(p.name) || l.includes(p.dir)) && !omitted.includes(p.dir)
  );
}

// ── Control: the real detector, both directions, on a real fixture ─────────
{
  const pkgs = packagesWithTests(ROOT, PACKAGE_GLOBS);
  if (pkgs.length < MIN_PACKAGES) {
    console.error(
      `✗ only ${pkgs.length} package(s) with test scripts found (floor ${MIN_PACKAGES}).\n` +
        '  The globs broke, or a submodule is not checked out. An unrun check is not a pass.'
    );
    process.exit(1);
  }
  // A package no CI surface names and no omission documents MUST be reported.
  //
  // The directory is JOINED rather than written as one literal, and that is not
  // cosmetic: `test-gate-paths-exist.sh` reads a literal `packages/<name>` string
  // as a claim that the path is real, and reports it as a dead path constant.
  // This one must NOT exist -- a control that points at a real package proves
  // nothing -- so the two gates would deadlock over it. Runtime-built paths are
  // out of that gate's scope by design (its own `test_detector_ignores_runtime_
  // and_glob_paths` case), which is the honest category for a synthetic fixture.
  const ghostDir = ['packages', '__ghost__'].join('/');
  const ghost: Pkg = { name: '@rediacc/__no_such_package__', dir: ghostDir, scripts: ['test'] };
  if (unreachable(ROOT, [ghost]).length !== 1) {
    refuse(
      '✗ instrument control did not fire: a package that is neither referenced by CI',
      '  nor documented as an omission was NOT reported, so a green run means nothing.'
    );
  }
  // And a package that IS documented must NOT be reported, or the gate would
  // fail forever and get deleted rather than obeyed.
  const documented: Pkg = { name: '@rediacc/json', dir: 'packages/json', scripts: ['test'] };
  if (unreachable(ROOT, [documented]).length !== 0) {
    refuse(
      '✗ instrument control over-reports: packages/json IS documented under',
      `  "${OMISSIONS_HEADING}" in ${OMISSIONS_DOC}, and was still flagged.`
    );
  }
}

const pkgs = packagesWithTests(ROOT, PACKAGE_GLOBS);
const missing = unreachable(ROOT, pkgs);

if (missing.length > 0) {
  console.error(
    `✗ package test suites that CI cannot reach and no record explains (${missing.length}):\n` +
      missing.map((p) => `    ${p.name}  (${p.dir})  scripts: ${p.scripts.join(', ')}`).join('\n') +
      '\n\n' +
      '  An unrun suite reads exactly like a passing one: nothing goes red and\n' +
      '  nobody is told, so the coverage is imaginary. Either wire it into CI, or\n' +
      `  record it under "${OMISSIONS_HEADING}" in ${OMISSIONS_DOC} with the REASON\n` +
      '  and a measured runtime, the way suite 26 and packages/json are.'
  );
  process.exit(1);
}

console.log(
  `✓ every package test suite is CI-reachable or a documented omission ` +
    `(${pkgs.length} packages; control fired both ways)`
);
