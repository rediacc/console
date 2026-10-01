#!/usr/bin/env tsx
/**
 * The quick lane's typecheck: the SAME project set `check:types` covers, through tsc's incremental caches.
 *
 * WHY IT EXISTS. On 2026-10-01 a TS2322 in packages/cli/src/commands/__tests__/repo-container.test.ts reached CI. `check:types` is `slow: true` (CI step p90 124.8 s, local samples 100-690 s contended), so `npm run ci:quick` deferred it, and nothing else in the quick lane reads a test tsconfig: `build:cli` compiles packages/cli/tsconfig.json, which excludes `**\/*.test.ts`.
 *
 * WHY A MIRROR AND NOT A SECOND LIST. The project set is READ from package.json's `check:types` at run time, clause by clause, so it cannot drift from the gate it stands in for. A clause this file does not recognise is a refusal, never a skip: a mirror that quietly checks fewer projects than its original is the vacuity this gate exists to close.
 *
 * HOW EACH CLAUSE IS MIRRORED:
 *   - `tsc -b <dirs>` runs verbatim. Build mode is already incremental; its tsbuildinfo lives in each package's dist.
 *   - `tsc --noEmit -p <config>` gains `--incremental --tsBuildInfoFile <CACHE_DIR>/<slug>.tsbuildinfo`. The cache sits outside the repository (see CACHE_DIR), so no tsconfig changes and nothing lands in the tree.
 *   - `npm run typecheck --workspace packages/www` becomes the `tsc --noEmit` half of that script over packages/www/tsconfig.json. `astro sync` is SKIPPED and printed as skipped on every run: it rewrites packages/www/.astro while other quick gates run, and costs 7.8 s (measured 2026-10-01). The types it generates are read as last synced; the full `check:types` re-syncs.
 *   - the workers clause (`rediacc_ci.quality.typecheck_workers`) becomes one incremental project per `workers/<x>/tsconfig.json`, discovered at the same depth the Python gate uses. A worker with no node_modules is a loud failure naming the install command, because its types resolve from its own node_modules.
 *
 * Measured 2026-10-01 on 24 cores, one project at a time: cold 2.1-20.7 s per project, warm 1.6-5.0 s.
 *
 * THE STAMP: A PROJECT WHOSE INPUTS ARE UNCHANGED SINCE ITS LAST CLEAN RUN IS NOT RE-RUN. Warm incremental tsc still rebuilds the whole program (5-6 s and about 8 CPU-s per project), which put this gate at 25-29 s in the lane and over check:ci-gate-manifest's tier ceiling. After a run exits 0, a stamp records every input that run could have read, and the next run skips the project only when all of them still match:
 *   - every file in the program, as `tsc --listFiles` printed it on that clean run (lib files, node_modules declarations, the workspace dist), by size and mtime, falling back to a sha1 of the content when the mtime moved;
 *   - the ROOT file set, re-expanded from the include/exclude globs by tsc's own config parser on every run, so a NEW file the globs pick up is a change even though no stamped file moved;
 *   - the tsconfig and its whole `extends` chain, the nearest package.json above every program file (an `exports` or `types` change re-routes resolution without touching a listed file), and the root and project lockfiles plus node_modules/.package-lock.json (an install can add an `@types` package that tsc includes automatically);
 *   - the TypeScript version and the exact tsc arguments.
 * A run that fails deletes the stamp, so a red project is re-checked until it is green. A clean run whose output names no program file writes NO stamp: a stamp over zero files would match forever, which is a vacuous green.
 *
 * RESIDUAL, named rather than hidden: a module-resolution lookup that FAILED quietly on the clean run (a candidate path probed and absent, then a later candidate used) is not recorded, so a file appearing at an earlier candidate outside the root globs, the lockfiles and the stamped package.json files would be missed; and a content change that keeps both size and mtime identical is read as unchanged, as make and `tsc -b` read it. The full `check:types` in CI runs uncached and is the backstop for both.
 */
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
/**
 * tsbuildinfo files and stamps, one directory per checkout, OUTSIDE the repository: check:ci-gate-tree-writes counts even the gitignored .ci/cache as the shared tree, and a cache nothing else reads has no reason to sit beside the gates that read the tree.
 */
export const CACHE_DIR = path.join(
  os.homedir(),
  '.cache',
  'rediacc-typecheck',
  REPO_ROOT.replace(/^\/+/, '').replace(/\//g, '-')
);
const WORKERS_CLAUSE = 'PYTHONPATH=.ci python3 -m rediacc_ci.quality.typecheck_workers';
const WWW_CLAUSE = 'npm run typecheck --workspace packages/www';
const WWW_EXPECTED = 'astro sync && tsc --noEmit';
const WORKERS_INSTALL = 'PYTHONPATH=.ci python3 -m rediacc_ci.quality.typecheck_workers --install';
/**
 * The fewest project steps the REAL check:types may yield. Measured 2026-10-01: 12 (1 build-mode clause, 6 `--noEmit -p` clauses, packages/www, 4 workers). Fewer means the parse or the discovery lost projects, and a green over the remainder would claim the whole set.
 */
export const MIN_PROJECTS = 10;

/** One tsc invocation. `build` runs first and alone, because the noEmit projects resolve the workspace packages through the dist it writes. */
export interface TscStep {
  readonly label: string;
  readonly phase: 'build' | 'check';
  readonly args: readonly string[];
  /** The tsconfig a `check` step reads, for the stamp. */
  readonly config?: string;
}

export interface Plan {
  readonly steps: readonly TscStep[];
  /** Named, printed on every run: what this mirror does NOT do that the original does. */
  readonly skipped: readonly string[];
}

export class PlanRefusal extends Error {}

/** `packages/cli/tsconfig.test.json` -> `packages_cli_tsconfig.test.json.tsbuildinfo`. */
export function cacheFile(config: string, dir: string = CACHE_DIR): string {
  return path.join(dir, `${config.replace(/[^A-Za-z0-9_.-]/g, '_')}.tsbuildinfo`);
}

function checkStep(label: string, config: string, dir: string = CACHE_DIR): TscStep {
  return {
    label,
    phase: 'check',
    args: ['--noEmit', '--incremental', '--tsBuildInfoFile', cacheFile(config, dir), '-p', config],
    config,
  };
}

/** Refuses a real plan below MIN_PROJECTS (or `floor`), naming it VACUOUS. */
export function refuseBelowFloor(plan: Plan, floor: number = MIN_PROJECTS): void {
  if (plan.steps.length < floor) {
    throw new PlanRefusal(
      `VACUOUS: check:types yielded ${plan.steps.length} project step(s), below the floor of ${floor} (MIN_PROJECTS). The parse or the worker discovery lost projects, so a green here would claim a set it did not check.`
    );
  }
}

interface FileStamp {
  readonly size: number;
  readonly mtimeMs: number;
  readonly sha1: string;
}

interface Stamp {
  readonly v: 1;
  readonly tsc: string;
  readonly args: readonly string[];
  readonly roots: readonly string[];
  /** Absolute path -> fingerprint, or null for an input that was ABSENT (a lockfile a project does not have); its appearance is a change. */
  readonly files: Readonly<Record<string, FileStamp | null>>;
}

/** The stamp beside the step's own tsbuildinfo. */
export function stampPath(step: TscStep): string {
  const at = step.args.indexOf('--tsBuildInfoFile');
  return (step.args[at + 1] ?? '').replace(/\.tsbuildinfo$/, '.stamp.json');
}

const sha1 = (buf: Buffer): string => createHash('sha1').update(buf).digest('hex');

function fingerprint(abs: string): FileStamp | null {
  try {
    const st = fs.statSync(abs);
    if (!st.isFile()) return null;
    return { size: st.size, mtimeMs: st.mtimeMs, sha1: sha1(fs.readFileSync(abs)) };
  } catch {
    return null;
  }
}

function unchanged(abs: string, want: FileStamp | null): boolean {
  let st: fs.Stats;
  try {
    st = fs.statSync(abs);
  } catch {
    return want === null;
  }
  if (want === null || !st.isFile() || st.size !== want.size) return false;
  if (st.mtimeMs === want.mtimeMs) return true;
  return sha1(fs.readFileSync(abs)) === want.sha1;
}

/** Root files (the include/exclude expansion) and the config chain, from tsc's own parser. Undefined on any config error, which makes the project run. */
export function projectShape(
  cwd: string,
  config: string
): { roots: string[]; configs: string[] } | undefined {
  const abs = path.resolve(cwd, config);
  try {
    const parsed = ts.getParsedCommandLineOfConfigFile(
      abs,
      {},
      {
        ...ts.sys,
        onUnRecoverableConfigFileDiagnostic: () => {
          throw new Error('unrecoverable tsconfig');
        },
      }
    );
    if (parsed === undefined || parsed.errors.length > 0) return undefined;
    return {
      roots: [...parsed.fileNames].map((f) => path.resolve(path.dirname(abs), f)).sort(),
      configs: [
        abs,
        ...((parsed.options.configFile as ts.TsConfigSourceFile | undefined)?.extendedSourceFiles ??
          []),
      ],
    };
  } catch {
    return undefined;
  }
}

function tscVersion(tsc: string): string {
  try {
    const pkg = path.join(path.dirname(tsc), '..', 'package.json');
    return (JSON.parse(fs.readFileSync(pkg, 'utf-8')) as { version?: string }).version ?? '?';
  } catch {
    return '?';
  }
}

/** The program files `--listFiles` printed: absolute paths that exist. Diagnostics never start with a path separator. */
function listedFiles(output: string): string[] {
  return output
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => path.isAbsolute(l) && fs.existsSync(l));
}

/** The nearest package.json above `file`, memoised per directory. */
function nearestPackageJson(file: string, memo: Map<string, string | null>): string | null {
  const seen: string[] = [];
  let dir = path.dirname(file);
  for (;;) {
    const hit = memo.get(dir);
    if (hit !== undefined) {
      for (const d of seen) memo.set(d, hit);
      return hit;
    }
    seen.push(dir);
    const candidate = path.join(dir, 'package.json');
    if (fs.existsSync(candidate)) {
      for (const d of seen) memo.set(d, candidate);
      return candidate;
    }
    const up = path.dirname(dir);
    if (up === dir) {
      for (const d of seen) memo.set(d, null);
      return null;
    }
    dir = up;
  }
}

/** Every input of a clean run, per the THE STAMP list in this file's header. */
function stampInputs(cwd: string, config: string, programFiles: readonly string[]): string[] {
  const shape = projectShape(cwd, config);
  const configDir = path.dirname(path.resolve(cwd, config));
  const memo = new Map<string, string | null>();
  const packageJsons = programFiles
    .map((f) => nearestPackageJson(f, memo))
    .filter((p): p is string => p !== null);
  const locks = [cwd, configDir].flatMap((d) => [
    path.join(d, 'package-lock.json'),
    path.join(d, 'node_modules', '.package-lock.json'),
  ]);
  return [...new Set([...programFiles, ...(shape?.configs ?? []), ...packageJsons, ...locks])];
}

/**
 * Writes the stamp for a CLEAN run and reports whether it did. Refuses (returns false) when the output listed no program file, or fewer than the roots: a stamp that records nothing would never go stale. Refuses too when any input was modified from one second before `startedAt` onward: tsc may have read the earlier content, and stamping the later one would let the next run skip a version nothing checked.
 */
export function writeStamp(
  cwd: string,
  tsc: string,
  step: TscStep,
  output: string,
  startedAt: number
): boolean {
  if (step.config === undefined) return false;
  const file = stampPath(step);
  const shape = projectShape(cwd, step.config);
  const program = listedFiles(output);
  if (shape === undefined || program.length === 0 || program.length < shape.roots.length) {
    // tree-write: safe the stamp sits beside its tsbuildinfo in CACHE_DIR, under the home directory (the selftest passes a temp dir)
    fs.rmSync(file, { force: true });
    return false;
  }
  const files: Record<string, FileStamp | null> = {};
  for (const f of stampInputs(cwd, step.config, program)) {
    const fp = fingerprint(f);
    if (fp !== null && fp.mtimeMs >= startedAt - 1000) {
      // tree-write: safe the stamp sits beside its tsbuildinfo in CACHE_DIR, under the home directory (the selftest passes a temp dir)
      fs.rmSync(file, { force: true });
      return false;
    }
    files[f] = fp;
  }
  const stamp: Stamp = {
    v: 1,
    tsc: tscVersion(tsc),
    args: [...step.args],
    roots: shape.roots,
    files,
  };
  // tree-write: safe the stamp sits beside its tsbuildinfo in CACHE_DIR, under the home directory (the selftest passes a temp dir)
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // tree-write: safe the stamp sits beside its tsbuildinfo in CACHE_DIR, under the home directory (the selftest passes a temp dir)
  fs.writeFileSync(file, JSON.stringify(stamp));
  return true;
}

/** Why the project must run, or undefined when every stamped input still matches. */
export function staleReason(cwd: string, tsc: string, step: TscStep): string | undefined {
  if (step.config === undefined) return 'not a stamped step';
  let stamp: Stamp;
  try {
    stamp = JSON.parse(fs.readFileSync(stampPath(step), 'utf-8')) as Stamp;
  } catch {
    return 'no stamp from a clean run';
  }
  if (stamp.v !== 1 || stamp.tsc !== tscVersion(tsc)) return 'TypeScript version changed';
  if (JSON.stringify(stamp.args) !== JSON.stringify(step.args)) return 'tsc arguments changed';
  const shape = projectShape(cwd, step.config);
  if (shape === undefined) return 'the tsconfig did not parse cleanly';
  if (JSON.stringify(shape.roots) !== JSON.stringify(stamp.roots))
    return 'the root file set changed';
  const entries = Object.entries(stamp.files);
  if (entries.length === 0) return 'the stamp records no inputs';
  for (const [f, want] of entries) {
    if (!unchanged(f, want)) return `${path.relative(cwd, f)} changed`;
  }
  return undefined;
}

/**
 * The plan for a `check:types` script body. Pure apart from the two injected readers, so the selftest drives it with fixtures.
 *
 * `wwwTypecheck` is packages/www's own `typecheck` script; `workerConfigs` lists `workers/<x>/tsconfig.json` paths.
 */
export function planFrom(
  script: string,
  wwwTypecheck: string | undefined,
  workerConfigs: readonly string[]
): Plan {
  const steps: TscStep[] = [];
  const skipped: string[] = [];
  const clauses = script
    .split('&&')
    .map((c) => c.trim().replace(/\s+/g, ' '))
    .filter((c) => c !== '');
  for (const clause of clauses) {
    const build = /^tsc -b (.+)$/.exec(clause);
    // A flag among the operands (`tsc -b --force a`) changes what build mode does, so it falls through to the refusal below rather than being mirrored by a guess.
    if (build !== null && !build[1].split(' ').some((d) => d.startsWith('-'))) {
      const dirs = build[1].split(' ');
      steps.push({ label: `tsc -b ${dirs.join(' ')}`, phase: 'build', args: ['-b', ...dirs] });
      continue;
    }
    const check = /^tsc --noEmit -p (\S+)$/.exec(clause);
    if (check !== null) {
      steps.push(checkStep(check[1], check[1]));
      continue;
    }
    if (clause === WWW_CLAUSE) {
      if (wwwTypecheck?.trim().replace(/\s+/g, ' ') !== WWW_EXPECTED) {
        throw new PlanRefusal(
          `packages/www's typecheck script is '${wwwTypecheck ?? '(absent)'}', not '${WWW_EXPECTED}', so the mirror no longer knows what it runs. Update planFrom() in scripts/ci-runner/typecheck-incremental.ts.`
        );
      }
      steps.push(checkStep('packages/www/tsconfig.json', 'packages/www/tsconfig.json'));
      skipped.push('astro sync for packages/www (generated content types read as last synced)');
      continue;
    }
    if (clause === WORKERS_CLAUSE) {
      if (workerConfigs.length === 0) {
        throw new PlanRefusal(
          'check:types typechecks workers/*/tsconfig.json and this mirror found none, so its worker half would check nothing. The layout moved; update the discovery here and in rediacc_ci.quality.typecheck_workers together.'
        );
      }
      for (const config of workerConfigs) steps.push(checkStep(config, config));
      continue;
    }
    throw new PlanRefusal(
      `check:types gained a clause this mirror does not understand: '${clause}'. Teach planFrom() in scripts/ci-runner/typecheck-incremental.ts to mirror it; skipping it would make the quick lane check less than its name says.`
    );
  }
  if (steps.length === 0) {
    throw new PlanRefusal(
      'the check:types script yielded ZERO tsc projects, so this gate would check nothing. Its green would mean nothing.'
    );
  }
  return { steps, skipped };
}

/** `workers/<x>/tsconfig.json` at depth 2, sorted, the set rediacc_ci.quality.typecheck_workers discovers. */
function workerConfigs(root: string): string[] {
  const dir = path.join(root, 'workers');
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && fs.existsSync(path.join(dir, d.name, 'tsconfig.json')))
    .map((d) => `workers/${d.name}/tsconfig.json`)
    .sort();
}

interface StepResult {
  readonly step: TscStep;
  readonly code: number | null;
  readonly ms: number;
  readonly output: string;
  /** Skipped by the stamp: every input matched the last clean run. */
  readonly unchanged?: boolean;
}

function runTsc(tsc: string, step: TscStep, cwd: string): Promise<StepResult> {
  const started = Date.now();
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [tsc, ...step.args], { cwd, env: process.env });
    let output = '';
    child.stdout.on('data', (b: Buffer) => {
      output += b.toString();
    });
    child.stderr.on('data', (b: Buffer) => {
      output += b.toString();
    });
    child.on('error', (err) => {
      resolve({ step, code: null, ms: Date.now() - started, output: String(err) });
    });
    child.on('close', (code) => {
      resolve({ step, code, ms: Date.now() - started, output });
    });
  });
}

/** One `check` step behind the stamp: skipped when nothing it reads changed, else run with `--listFiles` so a clean run can be stamped and a red one un-stamped. */
type TscRunner = (tsc: string, step: TscStep, cwd: string) => Promise<StepResult>;

/**
 * tsc's own command line run IN THIS PROCESS: `executeCommandLine` is exactly what bin/tsc calls, with a `sys` that captures output and the exit status. For the selftest only, whose fixtures cost about 0.37 s each as a spawn, almost all of it loading the compiler, and about a tenth of that here; the stamp cases spawned 13 times and put this gate's selftest at 6.5 s standalone and most of its 20 s in a saturated lane. It is a runtime export absent from typescript.d.ts, so `inProcessRunner()` answers undefined when an upgrade removes it and the selftest falls back to spawning.
 */
function inProcessRunner(): TscRunner | undefined {
  const exec = (ts as unknown as { executeCommandLine?: unknown }).executeCommandLine;
  if (typeof exec !== 'function') return undefined;
  return (_tsc, step, cwd) => {
    const started = Date.now();
    let output = '';
    let code: number | null = null;
    const prev = process.cwd();
    process.chdir(cwd);
    try {
      const sys: ts.System = {
        ...ts.sys,
        // PINNED, not inherited: the compiler kept the FIRST call's directory across calls, so a second fixture read the first one's tsconfig (found by this selftest on its first in-process run).
        getCurrentDirectory: () => cwd,
        resolvePath: (p: string) => path.resolve(cwd, p),
        write: (text: string) => {
          output += text;
        },
        writeOutputIsTTY: () => false,
        exit: (status?: number) => {
          code = status ?? 0;
        },
      };
      (exec as (s: ts.System, cb: () => void, args: readonly string[]) => void)(sys, () => {}, [
        ...step.args,
      ]);
    } catch (err) {
      output += String(err);
      code = code ?? 1;
    } finally {
      process.chdir(prev);
    }
    return Promise.resolve({ step, code, ms: Date.now() - started, output });
  };
}

async function runChecked(
  tsc: string,
  step: TscStep,
  cwd: string,
  runner: TscRunner = runTsc
): Promise<StepResult> {
  const started = Date.now();
  if (staleReason(cwd, tsc, step) === undefined) {
    return { step, code: 0, ms: Date.now() - started, output: '', unchanged: true };
  }
  const r = await runner(tsc, { ...step, args: [...step.args, '--listFiles'] }, cwd);
  if (r.code === 0) {
    writeStamp(cwd, tsc, step, r.output, started);
  } else if (step.config !== undefined) {
    // tree-write: safe the stamp sits beside its tsbuildinfo in CACHE_DIR, under the home directory (the selftest passes a temp dir)
    fs.rmSync(stampPath(step), { force: true });
  }
  // The file list is the stamp's input, not something a reader needs beside a diagnostic.
  const shown = r.output
    .split('\n')
    .filter((l) => !(path.isAbsolute(l.trim()) && fs.existsSync(l.trim())))
    .join('\n');
  return { ...r, step, output: shown };
}

/** Runs every `build` step in order, then the `check` steps `width` at a time. A failed build stops the run: the checks would read a stale dist and report against it. */
async function execute(tsc: string, plan: Plan, cwd: string, width: number): Promise<StepResult[]> {
  const results: StepResult[] = [];
  for (const step of plan.steps.filter((s) => s.phase === 'build')) {
    const r = await runTsc(tsc, step, cwd);
    results.push(r);
    if (r.code !== 0) return results;
  }
  const queue = plan.steps.filter((s) => s.phase === 'check');
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  const workers = Array.from({ length: Math.max(1, Math.min(width, queue.length)) }, async () => {
    for (let step = queue.shift(); step !== undefined; step = queue.shift()) {
      results.push(await runChecked(tsc, step, cwd));
    }
  });
  await Promise.all(workers);
  return results;
}

const secs = (ms: number): string => `${(ms / 1000).toFixed(1)}s`;

function tscPath(root: string): string | undefined {
  const p = path.join(root, 'node_modules', 'typescript', 'bin', 'tsc');
  return fs.existsSync(p) ? p : undefined;
}

async function selftest(): Promise<number> {
  const failures: string[] = [];
  const require_ = (cond: boolean, message: string): void => {
    if (!cond) failures.push(message);
  };
  let assertions = 0;
  const check = (cond: boolean, message: string): void => {
    assertions += 1;
    require_(cond, message);
  };
  const refuses = (fn: () => unknown): boolean => {
    try {
      fn();
      return false;
    } catch (err) {
      return err instanceof PlanRefusal;
    }
  };

  // THE REAL SCRIPT PARSES, and into the projects named. A parser that returned [] would turn this gate green over nothing.
  const pkg = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'package.json'), 'utf-8')) as {
    scripts: Record<string, string>;
  };
  const www = JSON.parse(
    fs.readFileSync(path.join(REPO_ROOT, 'packages', 'www', 'package.json'), 'utf-8')
  ) as { scripts: Record<string, string> };
  const real = planFrom(
    pkg.scripts['check:types'] ?? '',
    www.scripts.typecheck,
    workerConfigs(REPO_ROOT)
  );
  const labels = real.steps.map((s) => s.label);
  check(
    labels.includes('packages/cli/tsconfig.test.json'),
    'the real plan must include packages/cli/tsconfig.test.json, the project the 2026-10-01 TS2322 lived in'
  );
  check(
    real.steps.some((s) => s.phase === 'build'),
    'the real plan must keep the tsc -b build-mode clause'
  );
  check(
    real.steps.length >= MIN_PROJECTS && !refuses(() => refuseBelowFloor(real)),
    `the real plan holds only ${real.steps.length} step(s), below MIN_PROJECTS ${MIN_PROJECTS}`
  );
  // THE FLOOR FIRES: the real plan with its workers lost (the discovery collapsing to nothing beyond a single worker) drops below MIN_PROJECTS and is refused as VACUOUS.
  const shrunk: Plan = {
    ...real,
    steps: real.steps.filter((st) => !st.label.startsWith('workers/')).slice(0, MIN_PROJECTS - 1),
  };
  let vacuous = '';
  try {
    refuseBelowFloor(shrunk);
  } catch (err) {
    vacuous = (err as Error).message;
  }
  check(vacuous.startsWith('VACUOUS'), 'a plan below MIN_PROJECTS must be refused as VACUOUS');

  // Both directions on the parser: a known clause becomes a step, an unknown one is REFUSED rather than skipped.
  const one = planFrom('tsc --noEmit -p a/tsconfig.json', undefined, []);
  check(
    one.steps.length === 1 && one.steps[0].args.includes('--incremental'),
    'a --noEmit clause must become one incremental step'
  );
  check(
    refuses(() => planFrom('tsc --noEmit -p a.json && eslint .', undefined, [])),
    'an unknown clause must be refused, not skipped'
  );
  check(
    refuses(() => planFrom('', undefined, [])),
    'an empty script must be refused'
  );
  check(
    refuses(() => planFrom(WORKERS_CLAUSE, undefined, [])),
    'a workers clause with no workers must be refused'
  );
  check(
    refuses(() => planFrom(WWW_CLAUSE, 'astro check', [])),
    'a changed www typecheck script must be refused, or the mirror checks something else than the original'
  );

  // THE INCREMENTAL CACHE MUST NOT SWALLOW AN ERROR. tsc stores diagnostics in tsbuildinfo, so a WARM second run over an unchanged bad file has to fail again; then a fixed file must pass on the same cache. Driven through the same runTsc() the real run uses, on the motivating shape.
  const tsc = tscPath(REPO_ROOT);
  if (tsc === undefined) {
    failures.push(
      'typescript is not installed (node_modules/typescript/bin/tsc missing). Run `npm install && npm run install:natives`.'
    );
  } else {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'typecheck-incremental-'));
    try {
      fs.writeFileSync(
        path.join(dir, 'tsconfig.json'),
        JSON.stringify({
          compilerOptions: { strict: true, types: [], lib: ['ES2022'], skipLibCheck: true },
          include: ['*.ts'],
        })
      );
      const bad =
        'const maybe: string | undefined = process.env.X;\nexport const r: Record<string, unknown> = maybe;\n';
      fs.writeFileSync(
        path.join(dir, 'probe.ts'),
        `declare const process: { env: Record<string, string | undefined> };\n${bad}`
      );
      const step = checkStep('probe', 'tsconfig.json', path.join(dir, '.cache'));
      // The COLD run is a real spawn, so the wrapper the real run uses is under test; the warm and fixed runs go in-process (see inProcessRunner) to keep this selftest cheap in a saturated lane.
      const later = inProcessRunner() ?? runTsc;
      const cold = await runTsc(tsc, step, dir);
      const warm = await later(tsc, step, dir);
      check(
        cold.code !== 0 && cold.output.includes('TS2322'),
        `a planted TS2322 must fail the cold run, got exit ${cold.code}: ${cold.output.slice(0, 200)}`
      );
      check(
        fs.existsSync(cacheFile('tsconfig.json', path.join(dir, '.cache'))),
        'CONTROL: the cold run must write its tsbuildinfo, or the warm run below is not warm'
      );
      check(
        warm.code !== 0 && warm.output.includes('TS2322'),
        `the WARM run over the same bad file must fail again, got exit ${warm.code}`
      );
      fs.writeFileSync(
        path.join(dir, 'probe.ts'),
        'export const r: Record<string, unknown> = { ok: true };\n'
      );
      const fixed = await later(tsc, step, dir);
      check(
        fixed.code === 0,
        `CONTROL: the fixed file must pass on the same cache, got exit ${fixed.code}: ${fixed.output.slice(0, 200)}`
      );
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }

    // THE STAMP IS SOUND ONLY IF EVERY KIND OF INPUT CHANGE RE-CHECKS. Each case changes one kind of input after a clean, stamped run and requires the next run to RE-CHECK (and, where the change is an error, to FAIL); the unchanged case requires a SKIP, or the stamp saves nothing and the cases prove nothing about it. Fixture mtimes are set into the past because a stamp refuses inputs modified inside its own run window.
    const sdir = fs.mkdtempSync(path.join(os.tmpdir(), 'typecheck-stamp-'));
    let age = 1000;
    const put = (rel: string, text: string): void => {
      const abs = path.join(sdir, rel);
      fs.writeFileSync(abs, text);
      age -= 10;
      const when = new Date(Date.now() - age * 1000);
      fs.utimesSync(abs, when, when);
    };
    try {
      put(
        'base.json',
        JSON.stringify({
          compilerOptions: { strict: true, types: [], noLib: true, skipLibCheck: true },
        })
      );
      put('tsconfig.json', JSON.stringify({ extends: './base.json', include: ['src/*.ts'] }));
      fs.mkdirSync(path.join(sdir, 'src'));
      // `noLib` with the eight global types tsc demands: the fixtures need only primitives, and parsing the ES2022 lib on every one of thirteen runs was most of their cost.
      put(
        'src/shim.d.ts',
        ['Array<T>', 'Boolean', 'Function', 'IArguments', 'Number', 'Object', 'RegExp', 'String']
          .map((t) => `interface ${t} {}`)
          .concat(['interface CallableFunction {}', 'interface NewableFunction {}'])
          .join('\n')
      );
      put('src/a.ts', "export const a: string = 'a';\n");
      const step = checkStep('stamp', 'tsconfig.json', path.join(sdir, '.cache'));
      const inProcess = inProcessRunner();
      check(
        inProcess !== undefined,
        'typescript no longer exports executeCommandLine at runtime; the stamp cases below fall back to spawning tsc (slower, still sound). Update inProcessRunner().'
      );
      const run = () => runChecked(tsc, step, sdir, inProcess ?? runTsc);
      const first = await run();
      check(
        first.code === 0 && first.unchanged !== true,
        `stamp: the first run must CHECK and pass, got exit ${first.code}: ${first.output.slice(0, 300)}`
      );
      check(fs.existsSync(stampPath(step)), 'stamp: a clean run must write its stamp');
      check(
        (await run()).unchanged === true,
        'stamp CONTROL: an unchanged project must be SKIPPED'
      );
      put('src/a.ts', 'export const a: string = 1;\n');
      const edited = await run();
      check(
        edited.unchanged !== true && edited.code !== 0 && edited.output.includes('TS2322'),
        `stamp: an EDITED file must be re-checked and its error caught, got exit ${edited.code}`
      );
      check(!fs.existsSync(stampPath(step)), 'stamp: a red run must delete the stamp');
      check((await run()).code !== 0, 'stamp: a red project must stay red on the next run');
      put('src/a.ts', "export const a: string = 'a';\n");
      check((await run()).code === 0, 'stamp CONTROL: the repaired file passes');
      put('src/b.ts', 'export const b: number = "b";\n');
      const added = await run();
      check(
        added.unchanged !== true && added.code !== 0,
        `stamp: a NEW file the include globs pick up must be re-checked and fail, got exit ${added.code}`
      );
      fs.rmSync(path.join(sdir, 'src', 'b.ts'));
      check((await run()).code === 0, 'stamp CONTROL: removing the bad file passes again');
      check((await run()).unchanged === true, 'stamp CONTROL: and the next run skips');
      // SAME SIZE, different content: `string` and `number` are both six bytes, so only the mtime and the content hash can see this edit.
      put('src/a.ts', "export const a: number = 'a';\n");
      const sameSize = await run();
      check(
        sameSize.unchanged !== true && sameSize.code !== 0,
        `stamp: a SAME-SIZE edit must be re-checked and fail, got exit ${sameSize.code}`
      );
      put('src/a.ts', "export const a: string = 'a';\n");
      check((await run()).code === 0, 'stamp CONTROL: the same-size repair passes');
      check(
        (await run()).unchanged === true,
        'stamp CONTROL: settled again before the next change'
      );
      put(
        'tsconfig.json',
        JSON.stringify({ extends: './base.json', include: ['src/*.ts'] }, null, 1)
      );
      check((await run()).unchanged !== true, 'stamp: a changed tsconfig must re-check');
      check(
        (await run()).unchanged === true,
        'stamp CONTROL: settled again before the next change'
      );
      put(
        'base.json',
        JSON.stringify({
          compilerOptions: { strict: false, types: [], noLib: true, skipLibCheck: true },
        })
      );
      check(
        (await run()).unchanged !== true,
        'stamp: a changed config in the extends chain must re-check'
      );
      check(
        (await run()).unchanged === true,
        'stamp CONTROL: settled again before the next change'
      );
      put('package-lock.json', '{}\n');
      check((await run()).unchanged !== true, 'stamp: a lockfile appearing must re-check');
      check(
        (await run()).unchanged === true,
        'stamp CONTROL: settled again before the next change'
      );
      // Inside the run window: an input modified during the run must not be stamped.
      fs.writeFileSync(path.join(sdir, 'src', 'a.ts'), "export const a: string = 'b';\n");
      const racing = await run();
      check(
        racing.code === 0 && !fs.existsSync(stampPath(step)),
        'stamp: an input modified inside the run window must leave NO stamp'
      );
      check(
        !writeStamp(sdir, tsc, step, 'no paths here\n', 0),
        'stamp: a clean run whose output lists no program file must NOT be stamped (it would never go stale)'
      );
    } finally {
      fs.rmSync(sdir, { recursive: true, force: true });
    }
  }

  if (failures.length > 0) {
    process.stderr.write('CONTROL FAILED: typecheck-incremental --selftest did not fire\n');
    for (const f of failures) process.stderr.write(`  - ${f}\n`);
    return 1;
  }
  process.stdout.write(`typecheck-incremental: selftest ok (${assertions} assertions)\n`);
  return 0;
}

async function main(argv: readonly string[]): Promise<number> {
  if (argv.includes('--selftest')) return selftest();
  const tsc = tscPath(REPO_ROOT);
  if (tsc === undefined) {
    process.stderr.write(
      'typecheck-incremental: typescript is not installed (node_modules/typescript/bin/tsc missing), so nothing was checked.\n  fix: npm install && npm run install:natives\n'
    );
    return 1;
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'package.json'), 'utf-8')) as {
    scripts?: Record<string, string>;
  };
  const script = pkg.scripts?.['check:types'];
  if (script === undefined) {
    process.stderr.write(
      'typecheck-incremental: package.json has no check:types script to mirror, so nothing was checked.\n'
    );
    return 1;
  }
  const wwwPkg = JSON.parse(
    fs.readFileSync(path.join(REPO_ROOT, 'packages', 'www', 'package.json'), 'utf-8')
  ) as { scripts?: Record<string, string> };
  let plan: Plan;
  try {
    plan = planFrom(script, wwwPkg.scripts?.typecheck, workerConfigs(REPO_ROOT));
    refuseBelowFloor(plan);
  } catch (err) {
    if (err instanceof PlanRefusal) {
      process.stderr.write(`typecheck-incremental: ${err.message}\n`);
      return 1;
    }
    throw err;
  }
  const missingDeps = plan.steps
    .map((s) => s.label)
    .filter((l) => l.startsWith('workers/'))
    .filter((l) => !fs.existsSync(path.join(REPO_ROOT, path.dirname(l), 'node_modules')));
  if (missingDeps.length > 0) {
    process.stderr.write(
      `typecheck-incremental: ${missingDeps.length} worker project(s) have no node_modules, so their types cannot resolve and they would be UNCHECKED: ${missingDeps.join(', ')}\n  fix: ${WORKERS_INSTALL}\n`
    );
    return 1;
  }

  const started = Date.now();
  const width = Math.max(1, Math.min(8, os.availableParallelism() - 1));
  const results = await execute(tsc, plan, REPO_ROOT, width);
  const wall = Date.now() - started;
  const failed = results.filter((r) => r.code !== 0);
  const notRun = plan.steps.length - results.length;
  for (const r of results) {
    process.stdout.write(
      `  ${r.code === 0 ? 'ok  ' : 'FAIL'} ${secs(r.ms).padStart(6)}  ${r.step.label}${r.unchanged === true ? '  (unchanged since its last clean run)' : ''}\n`
    );
  }
  for (const s of plan.skipped) process.stdout.write(`  skipped: ${s}\n`);
  if (failed.length > 0 || notRun > 0) {
    for (const r of failed) {
      process.stderr.write(
        `\ntypecheck-incremental: ${r.step.label} FAILED (exit ${r.code})\n${r.output}` +
          `  rerun: npx tsc ${r.step.args.join(' ')}\n`
      );
    }
    if (notRun > 0) {
      process.stderr.write(
        `typecheck-incremental: ${notRun} project(s) NOT RUN because a build-mode step failed first; fix it and rerun.\n`
      );
    }
    return 1;
  }
  const builds = plan.steps.filter((s) => s.phase === 'build').length;
  const skippedUnchanged = results.filter((r) => r.unchanged === true).length;
  process.stdout.write(
    `typecheck-incremental: ${results.length} project step(s) clean in ${secs(wall)} (${builds} build-mode, ${results.length - builds - skippedUnchanged} incremental --noEmit checked, ${skippedUnchanged} unchanged since a clean run; floor ${MIN_PROJECTS}, cache ${CACHE_DIR}), mirroring package.json check:types\n`
  );
  return 0;
}

if (
  process.argv[1] !== undefined &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main(process.argv.slice(2))
    .then((code) => {
      process.exitCode = code;
    })
    .catch((err: unknown) => {
      process.stderr.write(
        `typecheck-incremental: ${err instanceof Error ? err.stack : String(err)}\n`
      );
      process.exitCode = 1;
    });
}
