#!/usr/bin/env tsx
/**
 * check:ci-guard-mutations - does each declared guard actually have a test that
 * FAILS when the guard is deleted?
 *
 * WHY THIS EXISTS. A passing unit suite proves the code does not crash. It does
 * not prove any assertion pins the behaviour it names. Both halves of that gap
 * were paid for in one session:
 *
 *   - `colWidths: undefined` was handed to cli-table3, which reads
 *     `options.colWidths[0]` unconditionally. Every table narrow enough to need
 *     no shrinking threw. The change had been "verified" against the one wide
 *     table whose path returns an array, so nothing exercised the crash.
 *   - The replacement test for `wrapProse` was VACUOUS: it stayed green with the
 *     guard it claimed to test deleted, because a short word ahead of the long
 *     token makes both branches behave identically. Only mutating the source
 *     exposed it.
 *
 * `check:test-cli` cannot catch either by construction: it runs the tests and
 * reports that they passed. This gate runs them against a DELIBERATELY BROKEN
 * copy of the source and requires them to fail.
 *
 * TWO ARMS.
 *
 *   1. THE CLI ARM: the six `MUTANTS` below, each a find/replace on a
 *      packages/cli source file, each judged by one vitest file.
 *   2. THE HOOK ARM (worklist #de875def, 2026-11-21): every hook guard under
 *      `.claude/rediacc_hooks/guards/` that declares a top-level `DEFECT = (old,
 *      new)` or `MUTANTS = {name: (old, new)}`. Until this arm existed the gate
 *      never read either declaration, so a plan accept clause citing
 *      `npm run -s check:ci-guard-mutations` for a hook guard (RB3 and R4 of
 *      PLAN-two-track-merge-dev, among others) proved nothing about that guard.
 *      Each plant is applied to a SCRATCH COPY of the guard's source and the
 *      guard's own `test-<stem>.py` suite runs with that copy loaded in place of
 *      the real module; the suite must go red. How the copy is loaded, and why
 *      the real file is never written, is in
 *      `.ci/rediacc_ci/quality/guard_mutant_site.py` (the redirect); the
 *      declarations are read by `.ci/rediacc_ci/quality/guard_mutants.py`.
 *      Per guard: the UNPLANTED copy must pass, must be LOADED (a non-empty
 *      load log), must print something and must leave its private TMPDIR
 *      empty, or no verdict below it means anything. This pristine run is the
 *      ONLY run of these suites: `test_hooks_delegates.py` skips every suite
 *      this arm runs, so the empty-output and TMPDIR-leak refusals it used to
 *      apply live here (SILENT, LEAKED).
 *      Findings: a plant that leaves the suite green (UNDETECTED), a plant whose
 *      `old` no longer occurs outside its declaration (STALE), a MUTANTS entry
 *      naming more than one site (AMBIGUOUS; the suites' MUTANT_RUNNER refuses
 *      the same), a run that never loaded the copy (UNREACHED), a suite red
 *      with nothing planted (PRISTINE RED), a suite that timed out, and a
 *      declaration that cannot be read. A guard with NO sibling suite is the
 *      golden differential's subject (test_guards_differential.py plants the
 *      same DEFECT under check:ci-pytest); it is listed by name every run, and
 *      a missing golden or a stale plant is still a finding here.
 *
 * SAFETY. Mutation never touches the working tree. The CLI arm works in a
 * throwaway sandbox under `packages/cli/.guard-mutations.<pid>.<rand>.tmp/`
 * (matched by the existing `*.tmp` gitignore rule), because this tree is shared
 * with other sessions and an in-place mutation poisons their measurements even
 * when it is restored correctly afterwards. The hook arm writes only under an
 * `os.tmpdir()` mkdtemp directory: the planted sources, the redirect, the load
 * logs, and one private TMPDIR per suite run.
 *
 * CONTROL-FIRST. The gate self-fails when its own instrument cannot fire:
 *   - the pristine CLI sandbox must PASS (else the harness, not the guard, is broken)
 *   - every hook suite must pass, LOADING the copy, with nothing planted,
 *     printing something and leaving its private TMPDIR empty
 *   - `--selftest` plants a mutation that changes NOTHING into each arm and
 *     requires it reported as unprotected; plants a total break into a hook guard
 *     and requires a red; points the redirect at a module the suite never loads
 *     and requires UNREACHED; loads a copy that leaves a directory in TMPDIR
 *     and requires LEAKED; runs the declaration reader over a planted guards
 *     directory (stale, ambiguous, unreadable, valid); and runs a mutant of THIS
 *     FILE that skips the hook arm, which must exit non-zero.
 *
 * ADDING A CLI GUARD: append to MUTANTS. `find` must occur exactly once in `file`.
 * ADDING A HOOK GUARD: declare DEFECT / MUTANTS in the guard; nothing here changes.
 *
 * WALL TIME. The hook arm runs every suite at least twice (pristine and each
 * plant), in parallel up to `GUARD_MUTATIONS_JOBS` (default: the core count),
 * longest suite first. The summary line prints the wall time and the job count.
 *
 * ---- gate ----
 * step: Guard mutations
 * needs: node
 * run: tsx scripts/gates/check-guard-mutations.ts --selftest
 * lane: quality-packages
 * ---- end gate ----
 */
import { execFileSync, spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { availableParallelism, tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { refuse, refused } from '../lib/controls';

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PKG = join(REPO, 'packages/cli');
// UNIQUE per process. `npm run ci` is a parallel worker pool, so a fixed path lets one run `rm -rf` another's sandbox mid-flight - which surfaces as a control failure that a serial rerun cannot reproduce. Still ends in `.tmp`, so the existing gitignore rule covers it.
const SANDBOX = join(PKG, `.guard-mutations.${process.pid}.${randomBytes(4).toString('hex')}.tmp`);

const GUARDS_DIR = join(REPO, '.claude/rediacc_hooks/guards');
const GOLDENS_DIR = join(REPO, '.claude/rediacc_hooks/tests/goldens');
const CI_DIR = join(REPO, '.ci');
const REDIRECT = join(CI_DIR, 'rediacc_ci/quality/guard_mutant_site.py');
const SUITE_TIMEOUT_MS = 600_000;

interface Mutant {
  /** What the guard protects, in one line. */
  name: string;
  /** Source file, relative to packages/cli. */
  file: string;
  /** Exact text of the guard. Must appear exactly once. */
  find: string;
  /** The guard removed - what the code looked like when it was broken. */
  replace: string;
  /** Test file, relative to packages/cli, expected to FAIL once mutated. */
  test: string;
}

const MUTANTS: Mutant[] = [
  {
    name: 'colWidths is omitted, not passed as undefined, when a table already fits',
    file: 'src/services/core/output.ts',
    find: '...(widths ? { colWidths: widths } : {}),',
    replace: 'colWidths: widths,',
    test: 'src/services/__tests__/output.test.ts',
  },
  {
    name: 'wrapProse keeps an over-long FIRST token intact instead of emitting a blank line',
    file: 'src/services/core/output.ts',
    find: "if (candidate.length <= width || line === '') {",
    replace: 'if (candidate.length <= width) {',
    test: 'src/services/__tests__/output.test.ts',
  },
  {
    name: 'machine-readable relay lines are identified by the brace test, not loosely',
    file: 'src/services/executor/output-lines.ts',
    find: "if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return false;",
    replace: 'if (!trimmed) return false;',
    test: 'src/services/__tests__/machine-readable-relay.test.ts',
  },
  {
    name: 'withheld relay lines are WRAPPED when replayed, not dumped at full width',
    file: 'src/services/executor/output-lines.ts',
    find: 'for (const row of wrapProse(line, terminalWidth())) writeStderr(`${row}\\n`);',
    replace: 'writeStderr(`${line}\\n`);',
    test: 'src/services/__tests__/quiet-stderr-replay.test.ts',
  },
  {
    name: '--debug enables the relay firehose, not just REDIACC_DEBUG',
    file: 'src/services/executor/output-lines.ts',
    find: 'return debugEnabled() || Boolean(options.debug);',
    replace: 'return debugEnabled();',
    test: 'src/services/__tests__/quiet-stderr-replay.test.ts',
  },
  {
    name: 'the DAEMON path honours --debug too, not just the direct path',
    file: 'src/services/executor/daemon/client.ts',
    find: "if (event.level === 'error' || event.level === 'warning' || echoAll) {",
    replace: "if (event.level === 'error' || event.level === 'warning' || debugEnabled()) {",
    test: 'src/services/__tests__/quiet-stderr-replay.test.ts',
  },
];

/** A mutation that provably changes no behaviour, used only by --selftest. */
const NO_OP_MUTANT: Mutant = {
  name: 'CONTROL: a comment edit must NOT be reported as protected',
  file: 'src/services/core/output.ts',
  find: 'export function wrapProse(',
  replace: '/* selftest no-op */ export function wrapProse(',
  test: 'src/services/__tests__/output.test.ts',
};

/** The hook guard the selftest's live controls drive: chosen for a suite that runs in about a second. */
const HOOK_CONTROL_STEM = 'block_guarded_path_edit';
/** A second, real guard module the HOOK_CONTROL_STEM suite never loads: the UNREACHED control points the redirect at it. */
const HOOK_UNLOADED_STEM = 'block_long_sleep';

/**
 * Pristine text of every mutated file, snapshotted ONCE.
 *
 * Read from the sandbox, not the live tree, and never re-read: this worktree is
 * shared, and a peer session editing `output.ts` between two mutants would
 * otherwise make the occurrence assertion throw or mutate against shifted
 * content. One snapshot makes the whole run consistent with the sandbox it
 * actually tested.
 */
const pristine = new Map<string, string>();

/**
 * Refuse loudly when the subject is absent.
 *
 * Without this the gate dies on a raw ENOENT from `cpSync`, which is a failure
 * but not a legible one, and "no input" must be a hard, self-describing error
 * rather than something the reader has to decode. Registered in the repo's
 * anti-vacuity meta-gate, which points a validator at an empty tree and
 * requires a non-zero exit WITH a matching diagnostic.
 */
function assertSubjectPresent(): void {
  const missing: string[] = [];
  if (!existsSync(join(PKG, 'src'))) missing.push('packages/cli/src');
  for (const m of [...MUTANTS, NO_OP_MUTANT]) {
    for (const f of [m.file, m.test]) {
      if (!existsSync(join(PKG, f)) && !missing.includes(f)) missing.push(f);
    }
  }
  for (const rel of [
    '.claude/rediacc_hooks/guards',
    '.ci/rediacc_ci/quality/guard_mutants.py',
    '.ci/rediacc_ci/quality/guard_mutant_site.py',
    `.claude/rediacc_hooks/guards/test-${HOOK_CONTROL_STEM}.py`,
    `.claude/rediacc_hooks/guards/${HOOK_UNLOADED_STEM}.py`,
  ]) {
    if (!existsSync(join(REPO, rel))) missing.push(rel);
  }
  if (missing.length > 0) {
    refuse(
      `✗ required subject missing, so this gate can assert NOTHING:`,
      ...missing.map((f) => `    - ${f}`),
      `  A mutation gate with no source to mutate must fail, never report success.`
    );
  }
}

function buildSandbox(): void {
  rmSync(SANDBOX, { recursive: true, force: true });
  mkdirSync(SANDBOX, { recursive: true });
  cpSync(join(PKG, 'src'), join(SANDBOX, 'src'), { recursive: true });
  if (existsSync(join(PKG, 'package.json'))) {
    cpSync(join(PKG, 'package.json'), join(SANDBOX, 'package.json'));
  }
  // The config is RE-EXPORTED, never copied: it resolves its globalSetup and module cache by URLs relative to its own file (`../../scripts/lib/vitest-run-tmp.ts`), so a copy one directory deeper points them at a path that does not exist and the control fails with ERR_LOAD_URL. `--root SANDBOX` still roots `include` and `setupFiles` in the sandbox.
  if (existsSync(join(PKG, 'vitest.config.ts'))) {
    writeFileSync(
      join(SANDBOX, 'vitest.config.ts'),
      "export { default } from '../vitest.config.ts';\n"
    );
  }
  pristine.clear();
  for (const m of [...MUTANTS, NO_OP_MUTANT]) {
    if (!pristine.has(m.file)) pristine.set(m.file, readFileSync(join(SANDBOX, m.file), 'utf8'));
  }
}

/** Run one test file inside the sandbox. Returns true when it PASSED. */
function testPasses(testPath: string): boolean {
  try {
    execFileSync('npx', ['vitest', 'run', '--root', SANDBOX, testPath, '--reporter=dot'], {
      cwd: PKG,
      stdio: 'pipe',
      encoding: 'utf8',
    });
    return true;
  } catch {
    return false;
  }
}

function applyMutation(m: Mutant): void {
  const source = pristine.get(m.file);
  if (source === undefined) throw new Error(`no snapshot for ${m.file}`);
  const hits = source.split(m.find).length - 1;
  if (hits !== 1) {
    throw new Error(
      `mutant "${m.name}": its \`find\` text occurs ${hits} times in ${m.file}, expected exactly 1. ` +
        `The guard was probably edited; update the mutant to match the code.`
    );
  }
  writeFileSync(join(SANDBOX, m.file), source.replace(m.find, m.replace));
}

function restore(m: Mutant): void {
  writeFileSync(join(SANDBOX, m.file), pristine.get(m.file) ?? '');
}

/** The CLI arm, unchanged in substance since before the hook arm: returns the exit code it would have had alone. */
function runCliArm(selftest: boolean): number {
  console.log('CLI arm (packages/cli, vitest)');
  buildSandbox();

  // CONTROL: the untouched sandbox must pass, or nothing below means anything.
  const control = MUTANTS[0];
  if (!testPasses(control.test)) {
    console.error(
      `\n✗ CONTROL FAILED: ${control.test} does not pass against an UNMUTATED sandbox.\n` +
        `  The harness is broken, not the guard. No mutant result below would be trustworthy.`
    );
    rmSync(SANDBOX, { recursive: true, force: true });
    return 1;
  }
  console.log(`control: pristine sandbox passes ${control.test}`);

  const unprotected: string[] = [];
  for (const m of MUTANTS) {
    applyMutation(m);
    const stillGreen = testPasses(m.test);
    restore(m);
    if (stillGreen) {
      unprotected.push(m.name);
      console.log(`  UNPROTECTED  ${m.name}`);
    } else {
      console.log(`  protected    ${m.name}`);
    }
  }

  let selftestFailed = false;
  if (selftest) {
    applyMutation(NO_OP_MUTANT);
    const stillGreen = testPasses(NO_OP_MUTANT.test);
    restore(NO_OP_MUTANT);
    if (stillGreen) {
      console.log(`  selftest ok  a behaviour-neutral edit is correctly reported as unprotected`);
    } else {
      console.error(
        `\n✗ SELFTEST FAILED: a comment-only edit made ${NO_OP_MUTANT.test} fail.\n` +
          `  That means the test is sensitive to something other than behaviour, so a ` +
          `"protected" verdict from this gate cannot be trusted.`
      );
      selftestFailed = true;
    }
  }

  rmSync(SANDBOX, { recursive: true, force: true });

  if (selftestFailed) return 1;
  if (unprotected.length > 0) {
    console.error(
      `\n✗ ${unprotected.length} guard(s) have NO test that fails when the guard is deleted.\n` +
        unprotected.map((n) => `    - ${n}`).join('\n') +
        `\n\n  A green suite is not evidence for these. Sharpen the test until deleting the ` +
        `guard turns it red, the way the wrapProse test had to be sharpened.`
    );
    return 1;
  }

  console.log(
    `✓ CLI arm: all ${MUTANTS.length} declared guard(s) are pinned by a test that fails without them.`
  );
  return 0;
}

// ---------------------------------------------------------------------------------------------
// THE HOOK ARM
// ---------------------------------------------------------------------------------------------

/** One declared plant, as `guard_mutants.py` reports it. `spans` are UTF-8 byte offsets of `old` outside the declarations. */
export interface HookPlant {
  label: string;
  old: string;
  new: string;
  spans: [number, number][];
}

/** One hook guard that declares DEFECT and/or MUTANTS. `suite` is the sibling `test-<stem>.py`, or null. */
export interface HookGuard {
  stem: string;
  file: string;
  suite: string | null;
  plants: HookPlant[];
  errors: string[];
}

/** Read every declaring guard under `guardsDir` through the Python reader. Throws with the fix in the message when python3 cannot run it. */
export function readHookDeclarations(guardsDir: string): HookGuard[] {
  let out: string;
  try {
    out = execFileSync('python3', ['-m', 'rediacc_ci.quality.guard_mutants', guardsDir], {
      encoding: 'utf8',
      env: {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH ? `${CI_DIR}:${process.env.PYTHONPATH}` : CI_DIR,
      },
      maxBuffer: 64 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (err) {
    const e = err as { code?: string; stderr?: string };
    if (e.code === 'ENOENT') {
      throw new Error(
        'python3 is not on PATH. The hook guards and their suites are Python; install python3 (the toolchain pin in .devcontainer/toolchain.env) and rerun.'
      );
    }
    throw new Error(`the declaration reader failed: ${(e.stderr ?? String(err)).trim()}`);
  }
  return JSON.parse(out) as HookGuard[];
}

/**
 * A plant's applicability, before anything runs. Pure.
 *
 * DEFECT follows its suites: their runners `assert old in outside` and plant with `str.replace`, which replaces EVERY occurrence, so one or more sites is applicable and all of them are planted. A MUTANTS entry follows MUTANT_RUNNER (test-block_unverified_push.py), which asserts `outside.count(old) == 1`, so two or more is AMBIGUOUS.
 */
export function plantStatus(p: HookPlant): 'ok' | 'stale' | 'ambiguous' {
  if (p.spans.length === 0) return 'stale';
  if (p.label !== 'DEFECT' && p.spans.length > 1) return 'ambiguous';
  return 'ok';
}

/** `source` with every span replaced by `replacement`. Byte offsets, so a multi-byte character ahead of a span cannot shift it. Pure. */
export function plantBytes(source: Buffer, spans: [number, number][], replacement: string): Buffer {
  const parts: Buffer[] = [];
  let last = 0;
  for (const [start, end] of [...spans].sort((a, b) => a[0] - b[0])) {
    if (start < last || end > source.length || start > end) {
      throw new Error(`plant span [${start}, ${end}) overlaps or overruns the source`);
    }
    parts.push(source.subarray(last, start), Buffer.from(replacement, 'utf8'));
    last = end;
  }
  parts.push(source.subarray(last));
  return Buffer.concat(parts);
}

export interface SuiteRun {
  rc: number | null;
  loads: number;
  timedOut: boolean;
  seconds: number;
  tail: string;
  /** Entries the run left in its private TMPDIR, minus the shared tool caches `SHARED_TOOL_CACHE` names. */
  leftovers: string[];
  /** Bytes the suite wrote to stdout and stderr together. */
  outBytes: number;
}

/**
 * Fixed-name caches node and tsx keep under TMPDIR (`node-compile-cache`, `tsx-<uid>`), made by a suite that shells out to a tsx gate. One per user and reused rather than added to, so they are exempt by exact shape, never by prefix; anything else a suite leaves behind is a leak. The same pattern `test_hooks_delegates.py` applies to the suites it still runs.
 */
export const SHARED_TOOL_CACHE = /^(node-compile-cache|tsx-[0-9]+)$/;

/** The entries of a TMPDIR listing that count as a leak. Pure. */
export function tmpLeftovers(names: string[]): string[] {
  return names
    .filter((n) => !SHARED_TOOL_CACHE.test(n))
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

export type RunVerdict =
  | 'green'
  | 'caught'
  | 'undetected'
  | 'unreached'
  | 'broken'
  | 'pristine-red'
  | 'silent'
  | 'leaked'
  | 'timeout';

/**
 * The verdict for one suite run. Pure.
 *
 * `loads === 0` is checked BEFORE the exit code in both directions: a green run that never loaded the copy is not evidence the suite is blind, and a red one is not evidence it caught anything.
 *
 * A PRISTINE run is green only when it also printed something and left its private TMPDIR empty. Those two refusals used to live in `test_hooks_delegates.py`, which ran every one of these suites a second time under check:ci-pytest for exactly them; this run is now the only one, so it carries them. Empty output is what a stub returns (`silent`); a leftover directory is the leak that filled the /tmp inode cap on 2026-09-24 (`leaked`).
 */
export function runVerdict(
  kind: 'pristine' | 'plant',
  run: SuiteRun,
  guardBase?: string
): RunVerdict {
  if (run.timedOut) return 'timeout';
  if (run.loads === 0) return 'unreached';
  if (kind === 'pristine') {
    if (run.rc !== 0) return 'pristine-red';
    if (run.outBytes === 0) return 'silent';
    if (run.leftovers.length > 0) return 'leaked';
    return 'green';
  }
  if (run.rc === 0) return 'undetected';
  return plantNeverRan(run.tail, guardBase) ? 'broken' : 'caught';
}

/**
 * Whether a red run of a plant is the plant failing to compile or raising while the guard module loaded, which no suite assertion caught: a `SyntaxError` family error, or a module-level frame (`File "<guard>", line N, in <module>`) of the guard in the traceback. Pure.
 *
 * A red run read as 'caught' would credit the suite for a plant that never reached an assertion, so the gate would go green on a plant the suite is blind to.
 */
export function plantNeverRan(tail: string, guardBase?: string): boolean {
  // The error is the traceback's own line, `SyntaxError: <msg>` at the start of a line; the word quoted inside an assertion's message is not one.
  if (/^(?:SyntaxError|IndentationError|TabError)\b/m.test(tail)) return true;
  if (guardBase === undefined) return false;
  const escaped = guardBase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`File "[^"]*${escaped}", line \\d+, in <module>`).test(tail);
}

interface Job {
  stem: string;
  suite: string;
  label: string;
  kind: 'pristine' | 'plant';
  source: Buffer;
  /** The module whose compile is redirected. Normally the guard itself; the UNREACHED control points it elsewhere. */
  target: string;
  weight: number;
}

const liveChildren = new Set<number>();

/** Run one suite with `job.source` loaded in place of `job.target`. Never throws on a suite failure. */
function runSuite(job: Job, id: number): Promise<SuiteRun> {
  const dir = join(HOOK_SCRATCH, `job-${id}`);
  mkdirSync(join(dir, 'tmp'), { recursive: true });
  const source = join(dir, 'source.py');
  const log = join(dir, 'loads.log');
  writeFileSync(source, job.source);
  const started = Date.now();
  return new Promise((resolveRun) => {
    const child = spawn('python3', [join(GUARDS_DIR, job.suite)], {
      cwd: REPO,
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH ? `${SITE_DIR}:${process.env.PYTHONPATH}` : SITE_DIR,
        GUARD_MUTANT_TARGET: job.target,
        GUARD_MUTANT_SOURCE: source,
        GUARD_MUTANT_LOG: log,
        TMPDIR: join(dir, 'tmp'),
      },
    });
    if (child.pid !== undefined) liveChildren.add(child.pid);
    let tail = '';
    let outBytes = 0;
    const keep = (chunk: Buffer): void => {
      outBytes += chunk.length;
      tail = (tail + chunk.toString('utf8')).slice(-6000);
    };
    child.stdout.on('data', keep);
    child.stderr.on('data', keep);
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      killGroup(child.pid);
    }, SUITE_TIMEOUT_MS);
    const finish = (rc: number | null): void => {
      clearTimeout(timer);
      if (child.pid !== undefined) liveChildren.delete(child.pid);
      const loads = existsSync(log)
        ? readFileSync(log, 'utf8').split('\n').filter(Boolean).length
        : 0;
      const tmp = join(dir, 'tmp');
      const leftovers = existsSync(tmp) ? tmpLeftovers(readdirSync(tmp)) : [];
      rmSync(dir, { recursive: true, force: true });
      resolveRun({
        rc,
        loads,
        timedOut,
        seconds: (Date.now() - started) / 1000,
        tail,
        leftovers,
        outBytes,
      });
    };
    child.on('error', (err) => {
      tail += `\nspawn failed: ${err.message}`;
      finish(127);
    });
    child.on('close', (code) => finish(code));
  });
}

function killGroup(pid: number | undefined): void {
  if (pid === undefined) return;
  try {
    process.kill(-pid, 'SIGKILL');
  } catch {
    // Already gone: nothing to kill is the outcome a kill wants.
  }
}

/** Run `jobs` at most `width` at a time, heaviest first, and return the results in job order. */
async function runPool(jobs: Job[], width: number): Promise<SuiteRun[]> {
  const order = jobs.map((_, i) => i).sort((a, b) => jobs[b].weight - jobs[a].weight);
  const results: SuiteRun[] = new Array(jobs.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    while (next < order.length) {
      const i = order[next++];
      results[i] = await runSuite(jobs[i], i);
    }
  };
  await Promise.all(Array.from({ length: Math.min(width, jobs.length) }, worker));
  return results;
}

export interface HookFinding {
  stem: string;
  what: string;
  fix: string;
}

export interface HookReport {
  guards: HookGuard[];
  suiteGuards: number;
  delegated: string[];
  runs: number;
  findings: HookFinding[];
  lines: string[];
  seconds: number;
  width: number;
}

/** What a hook arm that ran nothing reports. Also the accumulator `runHookArm` starts from. */
export function emptyHookReport(): HookReport {
  return {
    guards: [],
    suiteGuards: 0,
    delegated: [],
    runs: 0,
    findings: [],
    lines: [],
    seconds: 0,
    width: 0,
  };
}

/**
 * The hook arm's ONE scratch directory, a module-level `os.tmpdir()` mkdtemp so check:ci-gate-tree-writes resolves every write below it as scratch. Unique per process for the reason SANDBOX is, and removed by `cleanup` on every exit path.
 */
const HOOK_SCRATCH = mkdtempSync(join(tmpdir(), 'guard-mutations-hook-'));
const SITE_DIR = join(HOOK_SCRATCH, 'site');

/** Put the redirect in place as the scratch `sitecustomize.py`, once. */
function ensureSite(): void {
  if (existsSync(join(SITE_DIR, 'sitecustomize.py'))) return;
  mkdirSync(SITE_DIR, { recursive: true });
  copyFileSync(REDIRECT, join(SITE_DIR, 'sitecustomize.py'));
}

function poolWidth(): number {
  const raw = process.env.GUARD_MUTATIONS_JOBS;
  const n = raw ? Number.parseInt(raw, 10) : availableParallelism();
  return Number.isFinite(n) && n > 0 ? n : 1;
}

/** Plan, run and judge every hook guard's plants. `planOnly` reads and classifies the declarations and runs no suite. */
async function runHookArm(opts: { planOnly: boolean }): Promise<HookReport> {
  const report = emptyHookReport();
  const started = Date.now();
  report.guards = readHookDeclarations(GUARDS_DIR);
  report.width = poolWidth();
  const jobs: Job[] = [];
  const plantJobs = new Map<string, number[]>();
  const pristineJob = new Map<string, number>();

  for (const g of report.guards) {
    for (const e of g.errors) {
      report.findings.push({
        stem: g.stem,
        what: `UNREADABLE declaration: ${e}`,
        fix: 'make the declaration a literal (old, new) pair of strings, as every other guard does',
      });
    }
    for (const p of g.plants) {
      const status = plantStatus(p);
      if (status === 'stale') {
        report.findings.push({
          stem: g.stem,
          what: `STALE ${p.label}: its \`old\` text no longer occurs outside its declaration: ${JSON.stringify(p.old.slice(0, 120))}`,
          fix: 'the guarded line moved or was rewritten; update the declaration to name the line as it reads now',
        });
      } else if (status === 'ambiguous') {
        report.findings.push({
          stem: g.stem,
          what: `AMBIGUOUS ${p.label}: its \`old\` text occurs ${p.spans.length} times outside the declarations`,
          fix: 'widen `old` until it names exactly one site, the rule MUTANT_RUNNER enforces in the suites',
        });
      }
    }
    if (g.suite === null) {
      report.delegated.push(g.stem);
      if (!existsSync(join(GOLDENS_DIR, `${g.stem}.jsonl`))) {
        report.findings.push({
          stem: g.stem,
          what: 'NO SUITE AND NO GOLDEN: nothing exists that could notice any of its plants',
          fix: `add test-${g.stem}.py beside the guard, or freeze its golden`,
        });
      }
      continue;
    }
    report.suiteGuards += 1;
    const guardPath = join(GUARDS_DIR, g.file);
    const source = readFileSync(guardPath);
    const weight = statSync(join(GUARDS_DIR, g.suite)).size;
    pristineJob.set(g.stem, jobs.length);
    jobs.push({
      stem: g.stem,
      suite: g.suite,
      label: 'pristine',
      kind: 'pristine',
      source,
      target: guardPath,
      weight,
    });
    const mine: number[] = [];
    for (const p of g.plants) {
      if (plantStatus(p) !== 'ok') continue;
      mine.push(jobs.length);
      jobs.push({
        stem: g.stem,
        suite: g.suite,
        label: p.label,
        kind: 'plant',
        source: plantBytes(source, p.spans, p.new),
        target: guardPath,
        weight,
      });
    }
    plantJobs.set(g.stem, mine);
  }

  if (opts.planOnly) {
    report.lines.push(
      `  plan: ${report.guards.length} declaring guard(s), ${report.suiteGuards} with a suite, ${jobs.length} suite run(s) planned`
    );
    report.seconds = (Date.now() - started) / 1000;
    return report;
  }

  ensureSite();
  const results = await runPool(jobs, report.width);
  report.runs = results.length;

  for (const g of report.guards) {
    if (g.suite === null) continue;
    const p = results[pristineJob.get(g.stem) ?? -1];
    const pv = runVerdict('pristine', p);
    const parts: string[] = [];
    let bad = pv !== 'green';
    if (pv !== 'green') {
      report.findings.push({
        stem: g.stem,
        what: `${pv.toUpperCase()} with NOTHING planted (rc ${p.rc}, ${p.loads} load(s)); no plant verdict for this guard can be trusted`,
        fix:
          pv === 'unreached'
            ? `the suite never compiled ${g.file} through the import system, so the redirect cannot reach it; drive the guard by import or dispatch.py`
            : pv === 'silent'
              ? `${g.suite} exited 0 and printed NOTHING, which is what a stub returns; make it print one line per case or a count`
              : pv === 'leaked'
                ? `${g.suite} left ${p.leftovers.length} entr(y/ies) in its private TMPDIR: ${p.leftovers.slice(0, 20).join(', ')}. Delete every temp directory the suite creates (try/finally or atexit plus rmtree); leaked fixture repos are what filled the /tmp inode cap on 2026-09-24`
                : `run python3 .claude/rediacc_hooks/guards/${g.suite} and fix what it prints. Last output:\n${indentTail(p.tail)}`,
      });
    }
    for (const i of plantJobs.get(g.stem) ?? []) {
      const r = results[i];
      const v = runVerdict('plant', r, basename(g.file));
      parts.push(`${jobs[i].label} ${v === 'caught' ? 'red' : v.toUpperCase()}`);
      if (v === 'caught' || pv !== 'green') continue;
      bad = true;
      report.findings.push({
        stem: g.stem,
        what:
          v === 'undetected'
            ? `UNDETECTED ${jobs[i].label}: ${g.suite} stays GREEN with it planted (${r.loads} load(s) of the planted copy)`
            : `${v.toUpperCase()} ${jobs[i].label} (rc ${r.rc}, ${r.loads} load(s), ${r.seconds.toFixed(0)}s)`,
        fix:
          v === 'undetected'
            ? `add a case to ${g.suite} that the planted line flips, so deleting the guarded line turns the suite red. Do not weaken or drop the declaration.`
            : v === 'broken'
              ? `the planted copy does not compile or raises while ${g.file} loads, so the red run proves nothing about ${g.suite}; fix the declaration so the plant changes only the guarded behaviour. Last output:\n${indentTail(r.tail)}`
              : `rerun python3 .claude/rediacc_hooks/guards/${g.suite}; last output:\n${indentTail(r.tail)}`,
      });
    }
    const skipped = g.plants.filter((pl) => plantStatus(pl) !== 'ok').length;
    report.lines.push(
      `  ${bad || skipped > 0 ? 'FINDING ' : 'ok      '} ${g.stem}  pristine ${pv === 'green' ? 'green' : pv.toUpperCase()} (${p.loads} loads, ${p.seconds.toFixed(0)}s)  ${parts.join(', ')}${skipped > 0 ? `  ${skipped} not runnable (see findings)` : ''}`
    );
  }
  report.seconds = (Date.now() - started) / 1000;
  return report;
}

function indentTail(tail: string): string {
  return tail
    .trim()
    .split('\n')
    .slice(-12)
    .map((l) => `        | ${l}`)
    .join('\n');
}

/** Print the report and return its exit code. Zero guards, or zero suite runs outside plan-only, is a refusal, never a pass. */
function judgeHookReport(report: HookReport, planOnly: boolean): number {
  if (report.guards.length === 0) {
    return refused(
      `\n✗ HOOK ARM saw ZERO declaring guards under .claude/rediacc_hooks/guards, so it verified nothing.`,
      `  Either the arm did not run or the reader lost the tree; its green would mean nothing.`
    );
  }
  if (!planOnly && report.runs === 0) {
    return refused(
      `\n✗ HOOK ARM ran ZERO suites over ${report.guards.length} declaring guards, so it verified nothing.`
    );
  }
  for (const l of report.lines) console.log(l);
  console.log(
    `  delegated (${report.delegated.length}, no test-<stem>.py; DEFECT is planted by test_guards_differential.py / test_guards_process_table.py under check:ci-pytest): ${report.delegated.join(', ')}`
  );
  const plants = report.guards.reduce((n, g) => n + g.plants.length, 0);
  const shape =
    `${report.guards.length} declaring guards (${report.suiteGuards} with a suite, ${report.delegated.length} delegated), ` +
    `${plants} plants, ${report.runs} suite runs, ${report.width} jobs, wall ${report.seconds.toFixed(1)}s`;
  if (report.findings.length > 0) {
    console.error(`\n✗ HOOK ARM: ${report.findings.length} finding(s) [${shape}]`);
    for (const f of report.findings) {
      console.error(`    - ${f.stem}: ${f.what}\n      fix: ${f.fix}`);
    }
    return 1;
  }
  if (planOnly) {
    console.log(
      `  PLAN ONLY: declarations read and classified, NO suite ran, nothing about detection is verified [${shape}]`
    );
    return 0;
  }
  console.log(`✓ HOOK ARM: every runnable plant turns its guard's suite red [${shape}]`);
  return 0;
}

// ---------------------------------------------------------------------------------------------
// HOOK ARM SELFTEST
// ---------------------------------------------------------------------------------------------

/**
 * A mutant of THIS FILE: the hook arm skipped, its report replaced by the empty one. Run as a copy in a temp directory with `--hook-only --plan-only`; it must exit non-zero, and the unmutated copy under the same flags must exit zero, or the zero-guard refusal is not what stands between a skipped arm and a green.
 */
// Every needle the self-copy edits is ASSEMBLED from parts: written whole, the literal would itself be a second occurrence in this file, and the occurrence check below would refuse the copy (measured on the first run of this control).
const SELF_MUTANT = {
  find: ['const hook = await', 'runHookArm({ planOnly });'].join(' '),
  replace: 'const hook = emptyHookReport();',
};

function occurrences(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

/** Run a copy of this gate with `mutate` applied, in a temp directory. Returns its exit code and stderr. */
function runSelfCopy(mutate: boolean): { rc: number; stderr: string } {
  // The gate AS TRACKED, read by its repo path rather than import.meta.url, so a copy of this file (a hand-run control of these controls) still tests the real gate here.
  let text = readFileSync(join(REPO, 'scripts/gates/check-guard-mutations.ts'), 'utf8');
  const swaps: [string, string][] = [
    [
      ['const REPO =', "resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');"].join(' '),
      `const REPO = ${JSON.stringify(REPO)};`,
    ],
    [
      ['from', "'../lib/controls';"].join(' '),
      `from ${JSON.stringify(join(REPO, 'scripts/lib/controls'))};`,
    ],
  ];
  if (mutate) swaps.push([SELF_MUTANT.find, SELF_MUTANT.replace]);
  for (const [find, replace] of swaps) {
    const n = occurrences(text, find);
    if (n !== 1)
      throw new Error(`self-copy: ${JSON.stringify(find)} occurs ${n} times, expected 1`);
    text = text.replace(find, replace);
  }
  const copy = join(HOOK_SCRATCH, `${mutate ? 'mutant' : 'copy'}-check-guard-mutations.ts`);
  writeFileSync(copy, text);
  try {
    execFileSync('npx', ['tsx', copy, '--hook-only', '--plan-only'], {
      cwd: REPO,
      stdio: 'pipe',
      encoding: 'utf8',
    });
    return { rc: 0, stderr: '' };
  } catch (err) {
    const e = err as { status?: number; stderr?: string };
    return { rc: e.status ?? 1, stderr: e.stderr ?? '' };
  }
}

/** `runSelfCopy`, with a broken copy step reported as a failed run instead of a crash that would hide every other control's line. */
function selfCopyOrFailure(mutate: boolean): { rc: number; stderr: string } {
  try {
    return runSelfCopy(mutate);
  } catch (err) {
    return {
      rc: -1,
      stderr: `the self-copy could not be built: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

/** A planted guards directory for the declaration reader: one valid guard, one stale, one ambiguous, one unreadable. */
function plantedGuardsDir(): string {
  const dir = join(HOOK_SCRATCH, 'planted-guards');
  mkdirSync(dir);
  writeFileSync(
    join(dir, 'block_valid.py'),
    '# a multi-byte character ahead of the span: \u00e9\u4e2d\nDEFECT = ("if x:", "if True:")\nMUTANTS = {"m": ("return 1", "return 0")}\ndef f(x):\n    if x:\n        return 1\n'
  );
  writeFileSync(join(dir, 'test-block_valid.py'), '# tests block_valid\n');
  writeFileSync(
    join(dir, 'block_stale.py'),
    'DEFECT = ("if gone:", "if True:")\ndef f(x):\n    return x\n'
  );
  writeFileSync(
    join(dir, 'block_ambiguous.py'),
    'MUTANTS = {"twice": ("return 1", "return 0")}\ndef f():\n    return 1\ndef g():\n    return 1\n'
  );
  writeFileSync(join(dir, 'block_unreadable.py'), 'DEFECT = ("only-one",)\n');
  writeFileSync(join(dir, 'block_undeclared.py'), 'def f():\n    return 1\n');
  return dir;
}

interface Control {
  name: string;
  ok: boolean;
  detail?: string;
}

async function hookSelftest(): Promise<Control[]> {
  const controls: Control[] = [];
  ensureSite();

  // 1. The reader and the classifier, both directions, on a planted directory.
  const planted = readHookDeclarations(plantedGuardsDir());
  const byStem = new Map(planted.map((g) => [g.stem, g]));
  const valid = byStem.get('block_valid');
  const validDefect = valid?.plants.find((p) => p.label === 'DEFECT');
  controls.push({
    name: 'reader: a valid DEFECT and MUTANTS entry are read, with their suite, and classify ok',
    ok:
      valid?.suite === 'test-block_valid.py' &&
      valid.plants.length === 2 &&
      valid.plants.every((p) => plantStatus(p) === 'ok'),
    detail: JSON.stringify(valid),
  });
  controls.push({
    name: 'reader: the span is a byte offset, so the plant lands on the line after a multi-byte character',
    ok:
      validDefect !== undefined &&
      plantBytes(
        readFileSync(join(HOOK_SCRATCH, 'planted-guards/block_valid.py')),
        validDefect.spans,
        'if True:'
      )
        .toString('utf8')
        .includes('    if True:\n        return 1') &&
      readFileSync(join(HOOK_SCRATCH, 'planted-guards/block_valid.py'), 'utf8').includes(
        'DEFECT = ("if x:"'
      ),
  });
  const stale = byStem.get('block_stale')?.plants[0];
  controls.push({
    name: 'reader: a DEFECT whose old text exists only in its own declaration is STALE',
    ok: stale !== undefined && plantStatus(stale) === 'stale',
    detail: JSON.stringify(stale),
  });
  const amb = byStem.get('block_ambiguous')?.plants[0];
  controls.push({
    name: 'reader: a MUTANTS entry naming two sites is AMBIGUOUS',
    ok: amb !== undefined && plantStatus(amb) === 'ambiguous',
    detail: JSON.stringify(amb),
  });
  controls.push({
    name: 'reader: a malformed declaration is an error, never skipped',
    ok: (byStem.get('block_unreadable')?.errors.length ?? 0) > 0,
  });
  controls.push({
    name: 'reader: a guard declaring nothing is not listed',
    ok: !byStem.has('block_undeclared'),
  });

  // 2. The verdict function, every branch.
  const r = (rc: number | null, loads: number, timedOut = false): SuiteRun => ({
    rc,
    loads,
    timedOut,
    seconds: 0,
    tail: '',
    leftovers: [],
    outBytes: 1,
  });
  const redTail = (tail: string): SuiteRun => ({ ...r(1, 3), tail });
  controls.push({
    name: 'verdict: a red plant whose output is a SyntaxError or a module-level frame of the guard is BROKEN, never caught; a red plant with an assertion failure is caught',
    ok:
      runVerdict('plant', redTail('  File "x.py", line 3\nSyntaxError: invalid syntax')) ===
        'broken' &&
      runVerdict(
        'plant',
        redTail('Traceback:\n  File "/g/block_x.py", line 9, in <module>\nNameError: x'),
        'block_x.py'
      ) === 'broken' &&
      runVerdict('plant', redTail('FAIL case 3: expected deny'), 'block_x.py') === 'caught' &&
      runVerdict(
        'plant',
        redTail('FAIL case 4: the reason quotes a SyntaxError: bad input, got allow'),
        'block_x.py'
      ) === 'caught' &&
      runVerdict(
        'plant',
        redTail('  File "/g/block_x.py", line 9, in run\nAssertionError'),
        'block_x.py'
      ) === 'caught',
  });
  controls.push({
    name: 'verdict: plant red with loads is caught; green with loads is UNDETECTED; no loads is UNREACHED either way',
    ok:
      runVerdict('plant', r(1, 3)) === 'caught' &&
      runVerdict('plant', r(0, 3)) === 'undetected' &&
      runVerdict('plant', r(1, 0)) === 'unreached' &&
      runVerdict('plant', r(0, 0)) === 'unreached' &&
      runVerdict('pristine', r(0, 3)) === 'green' &&
      runVerdict('pristine', r(1, 3)) === 'pristine-red' &&
      runVerdict('plant', r(null, 3, true)) === 'timeout',
  });
  controls.push({
    name: 'verdict: a green pristine run that printed nothing is SILENT and one that left a TMPDIR entry is LEAKED; the shared tool caches are not a leak, and a plant run is judged on neither',
    ok:
      runVerdict('pristine', { ...r(0, 3), outBytes: 0 }) === 'silent' &&
      runVerdict('pristine', { ...r(0, 3), leftovers: ['tmpabc'] }) === 'leaked' &&
      runVerdict('pristine', { ...r(1, 3), leftovers: ['tmpabc'] }) === 'pristine-red' &&
      runVerdict('plant', { ...r(1, 3), leftovers: ['tmpabc'], outBytes: 0 }) === 'caught' &&
      tmpLeftovers(['node-compile-cache', 'tsx-1000', 'tmpabc', 'tsx-x']).join(',') ===
        'tmpabc,tsx-x',
  });

  // 3. Live runs of a real suite, through the same runner the arm uses.
  const guardPath = join(GUARDS_DIR, `${HOOK_CONTROL_STEM}.py`);
  const suite = `test-${HOOK_CONTROL_STEM}.py`;
  const real = readFileSync(guardPath);
  const base = { stem: HOOK_CONTROL_STEM, suite, target: guardPath, weight: 0 };
  const live: Job[] = [
    { ...base, label: 'pristine', kind: 'pristine', source: real },
    {
      ...base,
      label: 'NO-OP',
      kind: 'plant',
      source: Buffer.concat([
        real,
        Buffer.from('\n# guard-mutations selftest: a comment changes no behaviour\n'),
      ]),
    },
    {
      ...base,
      label: 'TOTAL BREAK',
      kind: 'plant',
      source: Buffer.from(
        'raise SystemExit("guard-mutations selftest: the planted copy refuses to load")\n'
      ),
    },
    {
      ...base,
      label: 'UNREACHED',
      kind: 'plant',
      source: real,
      target: join(GUARDS_DIR, `${HOOK_UNLOADED_STEM}.py`),
    },
    {
      ...base,
      label: 'LEAK',
      kind: 'pristine',
      source: Buffer.concat([
        real,
        Buffer.from(
          '\nimport tempfile as _gm_tempfile\n_gm_tempfile.mkdtemp(prefix="guard-mutations-selftest-leak-")\n'
        ),
      ]),
    },
  ];
  const [pristineRun, noop, total, unreached, leak] = await runPool(live, live.length);
  controls.push({
    name: `live: ${suite} passes with the unplanted copy loaded through the redirect`,
    ok: runVerdict('pristine', pristineRun) === 'green',
    detail: `rc ${pristineRun.rc}, ${pristineRun.loads} loads\n${indentTail(pristineRun.tail)}`,
  });
  controls.push({
    name: 'live: a behaviour-neutral plant is reported UNDETECTED (a suite that cannot see a plant is a finding)',
    ok: runVerdict('plant', noop) === 'undetected',
    detail: `rc ${noop.rc}, ${noop.loads} loads`,
  });
  controls.push({
    name: 'live: a total break of the planted copy turns the suite red, so the redirect injects what it is given',
    ok: runVerdict('plant', total) === 'caught',
    detail: `rc ${total.rc}, ${total.loads} loads`,
  });
  controls.push({
    name: 'live: a redirect aimed at a module the suite never loads is UNREACHED, never UNDETECTED or caught',
    ok: runVerdict('plant', unreached) === 'unreached',
    detail: `rc ${unreached.rc}, ${unreached.loads} loads`,
  });
  controls.push({
    name: 'live: the unplanted run printed output and left its TMPDIR empty (the control for the LEAK run below)',
    ok: pristineRun.outBytes > 0 && pristineRun.leftovers.length === 0,
    detail: `${pristineRun.outBytes} bytes, leftovers ${pristineRun.leftovers.join(', ')}`,
  });
  controls.push({
    name: 'live: a copy that leaves a directory in TMPDIR makes a passing pristine run LEAKED, naming the entry',
    ok:
      leak.rc === 0 &&
      runVerdict('pristine', leak) === 'leaked' &&
      leak.leftovers.some((n) => n.startsWith('guard-mutations-selftest-leak-')),
    detail: `rc ${leak.rc}, ${leak.loads} loads, leftovers ${leak.leftovers.join(', ')}`,
  });

  // 4. A mutant of this gate that skips the hook arm must go red; its unmutated copy must not.
  const unmutated = selfCopyOrFailure(false);
  const mutant = selfCopyOrFailure(true);
  controls.push({
    name: 'self: the unmutated gate copy plans the hook arm and exits 0 (control for the mutant below)',
    ok: unmutated.rc === 0,
    detail: unmutated.stderr.slice(-800),
  });
  controls.push({
    name: 'self: a gate mutant that skips the hook arm exits non-zero, naming ZERO declaring guards',
    ok: mutant.rc !== 0 && mutant.stderr.includes('ZERO declaring guards'),
    detail: `rc ${mutant.rc}: ${mutant.stderr.slice(-800)}`,
  });
  return controls;
}

function printControls(controls: Control[]): number {
  let failed = 0;
  for (const c of controls) {
    if (c.ok) {
      console.log(`  selftest ok  ${c.name}`);
    } else {
      failed += 1;
      console.error(`  SELFTEST FAILED  ${c.name}${c.detail ? `\n        ${c.detail}` : ''}`);
    }
  }
  return failed;
}

async function main(): Promise<number> {
  const selftest = process.argv.includes('--selftest');
  const hookOnly = process.argv.includes('--hook-only');
  const planOnly = process.argv.includes('--plan-only');
  console.log('Guard Mutations');
  console.log('='.repeat(60));

  assertSubjectPresent();

  const cliCode = hookOnly ? 0 : runCliArm(selftest);

  console.log(`\nHOOK arm (.claude/rediacc_hooks/guards, DEFECT and MUTANTS)`);
  const hook = await runHookArm({ planOnly });
  let code = judgeHookReport(hook, planOnly);

  if (selftest) {
    const controls = await hookSelftest();
    if (controls.length === 0 || printControls(controls) > 0) code = 1;
  }
  return cliCode !== 0 ? cliCode : code;
}

function cleanup(): void {
  for (const pid of liveChildren) killGroup(pid);
  rmSync(SANDBOX, { recursive: true, force: true });
  rmSync(HOOK_SCRATCH, { recursive: true, force: true });
}
for (const sig of ['SIGINT', 'SIGTERM'] as const) {
  process.on(sig, () => {
    cleanup();
    process.exit(130);
  });
}
// `refuse` exits from inside the arms; this is what still removes the scratch then.
process.on('exit', cleanup);

main()
  .then((code) => {
    cleanup();
    process.exit(code);
  })
  .catch((err: unknown) => {
    console.error(
      `✗ check:ci-guard-mutations crashed: ${err instanceof Error ? err.message : String(err)}`
    );
    cleanup();
    process.exit(1);
  });
