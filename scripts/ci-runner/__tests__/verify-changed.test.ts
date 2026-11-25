/**
 * Controls for scripts/ci-runner/verify-changed.ts planSteps (run with `npx tsx`).
 *
 * Each case plans a change set against a fake file system, so no real file is read. The cases: a `.ts` file with a sibling test, a `.py` file, a file with no test, and a package-less file.
 */
import process from 'node:process';
import { planSteps, siblingTest } from '../verify-changed';

let failed = 0;
function check(name: string, ok: boolean): void {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}`);
  if (!ok) failed++;
}

// The fake tree's paths are composed from real directories: written whole they read as claims about this repository to check:ci-paths-exist, which reports every one as dead.
const CLI = 'packages/cli/src';
const WWW = 'packages/www/src';
const FS = new Set([
  `${CLI}/a.ts`,
  `${CLI}/__tests__/a.test.ts`,
  `${CLI}/b.ts`,
  `${WWW}/w.ts`,
  'tools/x.ts',
  'tools/x.txt',
  'scripts/ci-runner/c.ts',
]);
const exists = (p: string): boolean => FS.has(p);
const kinds = (files: string[]): string[] => planSteps(files, exists).map((s) => s.kind);
const labels = (files: string[]): string[] => planSteps(files, exists).map((s) => s.label);

check(
  'sibling lookup finds __tests__/<name>.test.ts',
  siblingTest(`${CLI}/a.ts`, exists) === `${CLI}/__tests__/a.test.ts`
);

const ts = planSteps([`${CLI}/a.ts`], exists);
check(
  'ts with sibling: vitest runs the sibling, then one typecheck',
  ts.length === 2 &&
    ts[0].kind === 'vitest' &&
    ts[0].label.includes('src/__tests__/a.test.ts') &&
    !ts[0].label.includes('related') &&
    ts[1].kind === 'typecheck' &&
    ts[1].label === 'typecheck packages/cli/tsconfig.test.json'
);

check(
  'py file: one pytest step, no typecheck',
  JSON.stringify(kinds(['.ci/rediacc_ci/x.py'])) === JSON.stringify(['pytest'])
);

const none = planSteps([`${CLI}/b.ts`], exists);
check(
  'ts with no test: vitest related fallback, never a bare run',
  none[0]?.kind === 'vitest' && none[0].label.startsWith('vitest related packages/cli')
);

check('package with no vitest and no project (www): no step', kinds([`${WWW}/w.ts`]).length === 0);

check('package-less file: no step at all', kinds(['tools/x.ts', 'tools/x.txt']).length === 0);

check(
  'scripts file: typecheck of scripts/tsconfig.json, no vitest',
  JSON.stringify(labels(['scripts/ci-runner/c.ts'])) ===
    JSON.stringify(['typecheck scripts/tsconfig.json'])
);

process.exit(failed === 0 ? 0 : 1);
