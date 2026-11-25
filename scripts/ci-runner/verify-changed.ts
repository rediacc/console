#!/usr/bin/env tsx
/**
 * `npx tsx scripts/ci-runner/verify-changed.ts --changed [--base <ref>] [--dry-run]`: the one verify command for a unit of work.
 *
 * WHY (agent/plans/PLAN-drain-throughput.md DT6, Design B). A writer used to assemble its own checks from three selectors and a typecheck, one command per step and several turns per unit. This maps the changed files to the three step kinds and runs them one after another (CPU stays low), one summary line per step, one exit code.
 *
 *   1. vitest: a changed `.ts`/`.tsx` file under a vitest package runs its sibling test (`__tests__/<name>.test.ts` or `<name>.test.ts`); a changed test runs itself; a file with no sibling falls back to `vitest related`.
 *   2. pytest: any changed `.py` runs the files `rediacc_ci.pytest_impact` selects (the existing selector, not a copy). A FULL verdict is printed and skipped, since the full suite is the CI backstop.
 *   3. typecheck: one `tsc --noEmit` per touched project, through an incremental buildinfo in CACHE_DIR (typecheck-incremental.ts). A package-less file touches no project.
 *
 * THE CHANGE SET. In a lease (the git dir differs from the common dir) it is the merge-base of HEAD with the main checkout's HEAD against the working tree, so the lease's own commits count. In the main checkout it is the working tree against HEAD plus untracked files. `--base <ref>` overrides the base in both.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isEntryPoint } from '../lib/entry-point.js';
import { CACHE_DIR, cacheFile } from './typecheck-incremental';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

/** Packages whose tests run under their own vitest config (the root config refuses to run). */
const VITEST_PACKAGES = ['packages/cli', 'packages/shared', 'packages/provisioning'] as const;

/** Project roots a changed file can belong to, with the tsconfig that judges it. */
const PROJECTS: readonly { dir: string; config: string }[] = [
  { dir: 'packages/cli', config: 'packages/cli/tsconfig.test.json' },
  { dir: 'packages/shared', config: 'packages/shared/tsconfig.test.json' },
  { dir: 'packages/provisioning', config: 'packages/provisioning/tsconfig.test.json' },
  { dir: 'packages/e2e-tests', config: 'packages/e2e-tests/tsconfig.json' },
  { dir: 'private/account', config: 'private/account/tsconfig.json' },
  { dir: 'scripts', config: 'scripts/tsconfig.json' },
];

export type Step =
  | { kind: 'vitest'; label: string; cwd: string; args: string[] }
  | { kind: 'pytest'; label: string }
  | { kind: 'typecheck'; label: string; config: string };

const TS_RE = /\.(ts|tsx|mts)$/;
const TEST_RE = /\.test\.(ts|tsx)$/;

function projectOf(file: string): { dir: string; config: string } | undefined {
  return PROJECTS.find((p) => file.startsWith(`${p.dir}/`));
}

/** The sibling test of a source file, when one exists on disk. */
export function siblingTest(file: string, exists: (p: string) => boolean): string | undefined {
  const dir = path.posix.dirname(file);
  const base = path.posix.basename(file).replace(TS_RE, '');
  return [`${dir}/__tests__/${base}.test.ts`, `${dir}/${base}.test.ts`].find(exists);
}

function put(map: Map<string, Set<string>>, key: string, value: string): void {
  map.set(key, (map.get(key) ?? new Set()).add(value));
}

/** The plan for a change set: vitest steps per package, one pytest step when a `.py` changed, one typecheck per touched project. */
export function planSteps(changed: readonly string[], exists: (p: string) => boolean): Step[] {
  const steps: Step[] = [];
  const direct = new Map<string, Set<string>>();
  const related = new Map<string, Set<string>>();
  const touched = new Set<string>();
  let anyPy = false;
  for (const file of [...changed].sort((a, b) => a.localeCompare(b))) {
    if (file.endsWith('.py')) anyPy = true;
    const project = projectOf(file);
    if (project && TS_RE.test(file)) touched.add(project.config);
    const pkg = VITEST_PACKAGES.find((p) => file.startsWith(`${p}/`));
    if (!pkg || !TS_RE.test(file) || !exists(file)) continue;
    const rel = (f: string): string => f.slice(pkg.length + 1);
    if (TEST_RE.test(file)) {
      put(direct, pkg, rel(file));
      continue;
    }
    const sibling = siblingTest(file, exists);
    if (sibling) put(direct, pkg, rel(sibling));
    else put(related, pkg, rel(file));
  }
  for (const [pkg, files] of direct)
    steps.push({
      kind: 'vitest',
      label: `vitest ${pkg} (${[...files].join(' ')})`,
      cwd: pkg,
      args: ['vitest', 'run', '--reporter=dot', ...files],
    });
  for (const [pkg, files] of related)
    steps.push({
      kind: 'vitest',
      label: `vitest related ${pkg} (${[...files].join(' ')})`,
      cwd: pkg,
      args: ['vitest', 'related', '--run', '--passWithNoTests', '--reporter=dot', ...files],
    });
  if (anyPy) steps.push({ kind: 'pytest', label: 'pytest (pytest_impact selection)' });
  for (const config of [...touched].sort((a, b) => a.localeCompare(b)))
    steps.push({ kind: 'typecheck', label: `typecheck ${config}`, config });
  return steps;
}

function git(args: string[]): string {
  const r = spawnSync('git', args, { cwd: REPO_ROOT, encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`git ${args.join(' ')}: ${r.stderr.trim()}`);
  return r.stdout;
}

const lines = (s: string): string[] => s.split('\n').filter(Boolean);

/** The changed paths of the lease or the working tree, deleted files left out. */
export function changedFiles(base?: string): string[] {
  const inLease =
    git(['rev-parse', '--git-dir']).trim() !== git(['rev-parse', '--git-common-dir']).trim();
  let from = base;
  if (!from && inLease) {
    // the main checkout is the parent of the common git dir
    const main = path.dirname(
      path.resolve(REPO_ROOT, git(['rev-parse', '--git-common-dir']).trim())
    );
    const tip = spawnSync('git', ['-C', main, 'rev-parse', 'HEAD'], {
      encoding: 'utf8',
    }).stdout.trim();
    from = tip ? git(['merge-base', 'HEAD', tip]).trim() : 'HEAD';
  }
  const set = new Set(lines(git(['diff', '--name-only', '--diff-filter=d', from ?? 'HEAD'])));
  for (const f of lines(git(['ls-files', '--others', '--exclude-standard']))) set.add(f);
  return [...set].sort((a, b) => a.localeCompare(b));
}

interface Result {
  label: string;
  rc: number;
  ms: number;
  note?: string;
}

function run(cmd: string, args: string[], cwd: string, env?: NodeJS.ProcessEnv): number {
  const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', env: { ...process.env, ...env } });
  return r.status ?? 1;
}

function runPytest(base?: string): Omit<Result, 'label' | 'ms'> {
  const env = { ...process.env, PYTHONPATH: '.ci' };
  const args = ['-m', 'rediacc_ci.pytest_impact', '--json', ...(base ? ['--base', base] : [])];
  const sel = spawnSync('python3', args, { cwd: REPO_ROOT, encoding: 'utf8', env });
  if (sel.status !== 0) {
    process.stderr.write(sel.stderr);
    return { rc: sel.status ?? 1, note: 'selector failed' };
  }
  const out = JSON.parse(sel.stdout) as { pytestScope: string; reason: string; files: string[] };
  if (out.pytestScope === 'full')
    return { rc: 0, note: `SKIPPED: selector says FULL (${out.reason}); CI runs the whole suite` };
  if (out.files.length === 0) return { rc: 0, note: 'no test file selected' };
  const rc = run('python3', ['-m', 'pytest', '-q', ...out.files], REPO_ROOT, { PYTHONPATH: '.ci' });
  return { rc, note: `${out.files.length} file(s)` };
}

function execute(step: Step, base?: string): Omit<Result, 'label' | 'ms'> {
  if (step.kind === 'vitest') return { rc: run('npx', step.args, path.join(REPO_ROOT, step.cwd)) };
  if (step.kind === 'pytest') return runPytest(base);
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  const info = cacheFile(step.config);
  return {
    rc: run(
      'npx',
      ['tsc', '--noEmit', '--incremental', '--tsBuildInfoFile', info, '-p', step.config],
      REPO_ROOT
    ),
  };
}

export function main(argv: string[]): number {
  if (!argv.includes('--changed')) {
    process.stderr.write(
      'usage: npx tsx scripts/ci-runner/verify-changed.ts --changed [--base <ref>] [--dry-run]\n'
    );
    return 2;
  }
  const bi = argv.indexOf('--base');
  const base = bi >= 0 ? argv[bi + 1] : undefined;
  if (bi >= 0 && !base) {
    process.stderr.write('--base needs a ref\n');
    return 2;
  }
  const changed = changedFiles(base);
  const steps = planSteps(changed, (p) => fs.existsSync(path.join(REPO_ROOT, p)));
  process.stdout.write(`verify: ${changed.length} changed file(s), ${steps.length} step(s)\n`);
  for (const f of changed) process.stdout.write(`  changed ${f}\n`);
  // An OK over zero steps would read as a verified unit while nothing ran.
  if (steps.length === 0) {
    process.stderr.write(
      `verify: VACUOUS: ${changed.length === 0 ? 'no changed file' : 'no step maps to the changed files'}, so nothing would be verified; name the unit's own acceptance check instead.\n`
    );
    return 1;
  }
  if (argv.includes('--dry-run')) {
    for (const s of steps) process.stdout.write(`  plan ${s.label}\n`);
    return 0;
  }
  const results: Result[] = [];
  for (const step of steps) {
    const t0 = Date.now();
    const r = execute(step, base);
    results.push({ label: step.label, ms: Date.now() - t0, ...r });
  }
  for (const r of results)
    process.stdout.write(
      `verify: rc=${r.rc} ${(r.ms / 1000).toFixed(1)}s ${r.label}${r.note ? ` [${r.note}]` : ''}\n`
    );
  const bad = results.filter((r) => r.rc !== 0).length;
  process.stdout.write(`verify: ${bad === 0 ? 'OK' : `FAILED (${bad} step(s))`}\n`);
  return bad === 0 ? 0 : 1;
}

if (isEntryPoint(import.meta.filename)) process.exit(main(process.argv.slice(2)));
