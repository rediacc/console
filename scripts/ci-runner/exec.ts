/**
 * Run one gate: spawn it, capture stdout and stderr SEPARATELY, time it.
 *
 * THE SEPARATION IS THE POINT. A wrapper that merges the two streams hides an
 * entire defect class this repo has been bitten by: progress text written to
 * stdout, and output swallowed by a wrapper that only ever forwarded one
 * stream. The house rule ("Run the real thing ... read stdout and stderr
 * SEPARATELY") exists because of it. `--merge-output` is the deliberate opt-in
 * for a gate whose interleaving genuinely matters.
 *
 * See agent/plans/PLAN-npm-ci-parallel-parity.md section 4.4.
 */
import { spawn } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import type { GateSpec } from './manifest';

export interface ExecOutcome {
  /** Process exit code. null when the process died on a signal. */
  code: number | null;
  stdout: string;
  stderr: string;
  ms: number;
  /**
   * User+system CPU of every descendant the gate's shell reaped (bash `times`, second line: RUSAGE_CHILDREN). Absent on Windows-native, where the wrapper is not used, and when the wrapper itself died before reporting (a signal to the outer shell). A descendant that was reparented away (a daemon) is NOT counted; run.ts cross-checks against the /proc sampler for that.
   */
  cpuMs?: number;
  /**
   * Set when the process exited 0 but the runner still counts it a failure.
   * Carries the diagnostic to print in place of an exit code.
   */
  vacuity?: string;
}

/**
 * THE RUSAGE WRAPPER (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.1). The gate runs in a SUBSHELL with fd 3 closed, and the outer shell writes `times` to fd 3 after reaping it.
 *
 * A subshell, not the plan's `trap "times >&3" EXIT; eval "$1" 3>&-`, measured 2026-09-30 for two reasons: an `exit N` inside the gate runs the EXIT trap while `3>&-` is still in force, so the report is lost for exactly the gates that exit explicitly; and a gate that sets its own EXIT trap replaces the wrapper's (bash has one slot). Closing fd 3 for the gate keeps a daemon that inherits it from holding the pipe open and delaying `close`.
 *
 * The positional parameters are cleared and `$0` stays `bash`, so the gate body sees what a bare `bash -c <run>` gave it. Cost: one extra fork per gate, and a signal-killed gate now surfaces as exit 128+n from the outer shell, which settle() maps back to the signal message.
 */
const RUSAGE_WRAPPER =
  '( __ci_run=$1; shift; eval "$__ci_run" ) 3>&-; __ci_rc=$?; times >&3; exit $__ci_rc';

/** Seconds from one `times` field, `1m2.345s`; the decimal mark follows LC_NUMERIC. */
function timesField(field: string): number {
  const m = /^(\d+)m([\d.,]+)s$/.exec(field);
  return m === null ? Number.NaN : Number(m[1]) * 60 + Number(m[2].replace(',', '.'));
}

/** The children line of `times` output, as ms of user+sys; undefined when the report is missing or malformed. */
function parseTimes(text: string): number | undefined {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return undefined;
  const fields = lines[1].trim().split(/\s+/);
  if (fields.length !== 2) return undefined;
  const total = timesField(fields[0]) + timesField(fields[1]);
  return Number.isFinite(total) ? Math.round(total * 1000) : undefined;
}

/** The signal a shell exit status of 128+n stands for, or undefined when it is an ordinary status. */
function signalFromStatus(code: number): string | undefined {
  if (code <= 128 || code > 128 + 64) return undefined;
  const n = code - 128;
  const name = Object.entries(os.constants.signals).find(([, v]) => v === n)?.[0];
  return name ?? `signal ${n}`;
}

/**
 * The cores the pool granted one gate at launch (pool.ts admit). THE CONTRACT of agent/plans/PLAN-prepush-full-cpu.md part 1: `CI_RUNNER_CORES=<cores>` reaches the gate's process, and `CI_CORE_LEASE_HELD=1` beside it when the grant is backed by the machine-wide lease, so a child sizing itself through `granted_cores()` (.ci/rediacc_ci/core_lease.py) or `grantedCores()` (lease-client.ts) uses the grant and never leases the same cores a second time.
 */
export interface Grant {
  cores: number;
  leaseHeld: boolean;
}

/** The env names of the grant contract, shared with lease-client.ts and core_lease.py. */
export const CORES_ENV = 'CI_RUNNER_CORES';
export const LEASE_HELD_ENV = 'CI_CORE_LEASE_HELD';

/**
 * The child environment for one gate: this process's env, the gate's declared env, then the grant, last so no declaration can contradict the number the pool budgeted. Without a grant (a direct execGate call outside the pool) the env passes through unchanged. A lease this process does not hold is never claimed: when `leaseHeld` is false an inherited CI_CORE_LEASE_HELD is removed rather than forwarded.
 */
export function gateEnv(
  spec: Pick<GateSpec, 'env'>,
  grant: Grant | undefined,
  base: NodeJS.ProcessEnv = process.env
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = spec.env ? { ...base, ...localEnv(spec.env) } : { ...base };
  if (grant === undefined) return env;
  env[CORES_ENV] = String(Math.max(1, Math.floor(grant.cores)));
  if (grant.leaseHeld) env[LEASE_HELD_ENV] = '1';
  else delete env[LEASE_HELD_ENV];
  return env;
}

export interface ExecOptions {
  cwd: string;
  mergeOutput: boolean;
  /** The pool's grant for this launch; see `Grant`. */
  grant?: Grant;
  /**
   * When set, a forkless /proc tree sampler is attached to every gate spawn and
   * writes `<profileDir>/<gate-id>.jsonl`. This is the ONLY place a CI gate's
   * process tree is observable from the outside: the spawn below is the single
   * parent of every gate, and a BASH_ENV trap inside the gate is replaced by any
   * script's own EXIT trap (test-worklist-v5.sh:60 has one). The sampler is a
   * detached child that exits by itself when the gate's pid is gone; it never
   * changes the gate's exit code and its absence is a missing file, never an error.
   */
  profileDir?: string;
  profileRunId?: string;
}

/**
 * A PASS: line, optionally wrapped in the green escape that log_pass() emits.
 * Mirrors PASS_RE in .ci/rediacc_ci/battery.py, including the real ESC
 * byte: an earlier version of that pattern spelled the byte '\x1b', which
 * POSIX ERE reads as the literal text "x1b", so the summary matched nothing at
 * all and every colour-emitting gate test contributed zero visible evidence.
 * Built through fromCharCode so the source carries no raw control character.
 */
const PASS_LINE = new RegExp(`^(?:${String.fromCharCode(27)}\\[0;32m)?PASS:`, 'm');

/**
 * The battery counts a gate test that exits 0 without emitting a single
 * PASS: line as a FAILURE, because it asserted nothing. Flattening the battery
 * into the pool would silently drop that rule and leave those 57 tests weaker
 * locally than they are in CI, so the runner carries it instead.
 */
function vacuityCheck(spec: GateSpec, code: number | null, output: string): string | undefined {
  if (spec.qualityGateTest !== true || code !== 0) return undefined;
  if (PASS_LINE.test(output)) return undefined;
  return 'exited 0 without a single PASS: line (asserted nothing)';
}

/**
 * The part of a gate's declared env that means something outside Actions. A value holding a `${{ ... }}` expression (a ref name, a secret) is evaluated only by the workflow; injected verbatim it became a literal string, and three gates that read a branch or a token failed locally on it (2026-09-26).
 */
export function localEnv(env: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(env).filter(([, value]) => !value.includes('${{')));
}

export function execGate(spec: GateSpec, opts: ExecOptions): Promise<ExecOutcome> {
  return new Promise((resolve) => {
    const started = Date.now();
    const out: string[] = [];
    const err: string[] = [];

    // bash, not sh: several gate bodies use bashisms, and npm runs scripts through a shell anyway. stdin is closed so a gate that waits on input fails instead of hanging the whole pool.
    // The gate's declared `env` (the same values its CI step sets) goes into the child. Without it the local run was not the CI run: tutorial-player's PUBLIC_VIDEO_CDN_BASE_URL was declared here and never applied, so the gate failed in every clean clone and passed in CI (2026-09-26). The pool's grant goes in last (`gateEnv`).
    // Windows-native (Git Bash) keeps the bare spawn and reports wall time only: its `times` reports nothing useful for native children.
    const wrapped = process.platform !== 'win32';
    const child = spawn(
      'bash',
      wrapped ? ['-c', RUSAGE_WRAPPER, 'bash', spec.run] : ['-c', spec.run],
      {
        cwd: opts.cwd,
        env: gateEnv(spec, opts.grant),
        // fd 3 is opened on every platform so the spawn has one shape; unwrapped, nothing writes to it.
        stdio: ['ignore', 'pipe', 'pipe', 'pipe'],
      }
    );
    const rusage: string[] = [];
    // Read even when unwrapped: a pipe left paused may never reach EOF, and `close` waits for every stdio stream.
    const fd3 = child.stdio[3];
    if (fd3 !== null && fd3 !== undefined && 'setEncoding' in fd3) {
      fd3.setEncoding('utf8');
      fd3.on('data', (c: string) => {
        rusage.push(c);
      });
    }

    // RECORDS MUST LAND OUTSIDE THE REPO. A relative or in-tree profileDir writes capture files into the working tree -- the ci-runner's own selftest did exactly that and left selftest_pass.jsonl / selftest_fail.jsonl at the repo root. An unusable directory means no profile, never a file in the tree.
    const profileDir =
      opts.profileDir !== undefined &&
      path.isAbsolute(opts.profileDir) &&
      !path.resolve(opts.profileDir).startsWith(path.resolve(opts.cwd) + path.sep)
        ? opts.profileDir
        : undefined;
    if (profileDir !== undefined && child.pid !== undefined && spec.noProfile !== true) {
      // Detached and unreferenced: the runner must not wait on the sampler, and the sampler must not keep the runner alive. `--t0` is the absolute clock E4 needs to decide whether two gates' lifetimes overlapped.
      try {
        const sampler = spawn(
          'python3',
          [
            path.join(opts.cwd, '.claude/hooks/stop/wl_ressample.py'),
            '--watch',
            String(child.pid),
            '--out',
            path.join(profileDir, `${spec.id.replace(/[^A-Za-z0-9_.-]/g, '_')}.jsonl`),
            '--interval-ms',
            // 500, not 2000: measured on the first profiled run, p50 gate wall was 4.0 s and 224 of 293 gates finished under 6 s, so a 2 s tick left 221 captures with one or two samples -- unjudgeable by the sampler's own anti-vacuity rule. Every tick is forkless /proc reads, so the finer cadence costs nothing that matters.
            '500',
            '--run',
            opts.profileRunId ?? String(started),
            '--t0',
            String(started),
          ],
          { cwd: opts.cwd, stdio: 'ignore', detached: true }
        );
        sampler.unref();
        sampler.on('error', () => {
          /* a missing sampler costs a profile, never a gate */
        });
      } catch {
        /* same: profiling is best-effort by contract */
      }
    }

    // Optional chains only because a four-entry stdio loses node's typed overload; both are 'pipe' above, so neither is ever null.
    child.stdout?.setEncoding('utf8');
    child.stderr?.setEncoding('utf8');
    child.stdout?.on('data', (c: string) => {
      out.push(c);
    });
    child.stderr?.on('data', (c: string) => {
      (opts.mergeOutput ? out : err).push(c);
    });

    const settle = (code: number | null, extraErr?: string): void => {
      if (extraErr !== undefined) err.push(extraErr);
      const stdout = out.join('');
      const stderr = err.join('');
      resolve({
        code,
        stdout,
        stderr,
        ms: Date.now() - started,
        cpuMs: wrapped ? parseTimes(rusage.join('')) : undefined,
        vacuity: vacuityCheck(spec, code, stdout + stderr),
      });
    };

    child.on('error', (e: Error) => {
      settle(127, `ci-runner: could not spawn gate: ${e.message}\n`);
    });
    child.on('close', (code, signal) => {
      // The wrapper's outer shell reports a killed gate as 128+n (it cannot exec the last command, so the gate is never the spawned process itself). Mapped back to the message a direct kill always produced, so "killed" stays distinguishable from a verdict. Exit 77 is below the range and passes through untouched.
      const viaStatus = wrapped && code !== null ? signalFromStatus(code) : undefined;
      if (signal === null && viaStatus === undefined) settle(code);
      else settle(null, `ci-runner: gate terminated by signal ${signal ?? viaStatus}\n`);
    });
  });
}
