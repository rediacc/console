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
import { KILL_GRACE_MS } from './gate-timeout';
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
  /** Set when the runner killed the gate at its limit (gate-timeout.ts): the limit in ms. `code` is null and stderr carries a TIMED OUT line. */
  timedOutMs?: number;
}

/**
 * THE RUSAGE WRAPPER (agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.1). The gate runs in a SUBSHELL with fd 3 closed, and the outer shell writes `times` to fd 3 after reaping it.
 *
 * A subshell, not the plan's `trap "times >&3" EXIT; eval "$1" 3>&-`, measured 2026-09-30 for two reasons: an `exit N` inside the gate runs the EXIT trap while `3>&-` is still in force, so the report is lost for exactly the gates that exit explicitly; and a gate that sets its own EXIT trap replaces the wrapper's (bash has one slot). Closing fd 3 for the gate keeps a daemon that inherits it from holding the pipe open and delaying `close`.
 *
 * The positional parameters are cleared and `$0` stays `bash`, so the gate body sees what a bare `bash -c <run>` gave it. Cost: one extra fork per gate, and a signal-killed gate now surfaces as exit 128+n from the outer shell, which settle() maps back to the signal message.
 *
 * THE RUNNER-DEATH WATCH (fd 4). Each gate leads its own process group (LIVE), so a runner that dies without running its signal handler (SIGKILL, the OOM killer) no longer takes its gates with it: measured 2026-10-07, a gate of a SIGKILLed runner was still alive 3 s later and would have run forever. fd 4 is a pipe whose other end only the runner holds, and nothing is ever written to it, so a background `read` on it returns EOF exactly when the runner is gone, by any death; the watcher then SIGKILLs the whole group, itself included, with `kill -KILL 0` (pid 0 is the sender's own process group) rather than `-$$`: the spawned `bash` may be a wrapper that execs bash as its child (this machine's bashcov-sup shim), and then the group leader is not `$$`, so `-$$` named no group and the first version of this watch killed nothing (measured 2026-10-07). It also polls its own shell once a second and exits when that is gone: a gate that kills its outer shell directly (`kill -9 $$`, a selftest case) would otherwise leave the watcher holding fd 4, and `close`, which waits on every stdio stream, would never fire (measured: the first version hung the selftest exactly there). Chosen over the other two candidates: the gate's stdin would carry the same EOF, but a gate that reads stdin would then block on a live runner instead of seeing /dev/null's EOF (selftest:e2e-stdin pins that); `prctl(PR_SET_PDEATHSIG)` needs a helper binary, is Linux-only, and fires on the death of the spawning THREAD rather than the process. This needs only bash builtins, so it works wherever the wrapper does (Linux, macOS). The gate itself runs with fd 4 closed, so no descendant can hold the watch open or read from it; the watcher has its output on /dev/null and fd 3 closed, so it never delays `close` or the `times` report; and on a normal exit the outer shell kills it before reporting.
 */
const RUSAGE_WRAPPER =
  '{ while :; do read -r -t 1 -u 4 _; __r=$?; if [ $__r -le 128 ] && [ $__r -ne 0 ]; then kill -KILL 0; fi; kill -0 $$ 2>/dev/null || exit 0; done; } </dev/null >/dev/null 2>&1 3>&- & __ci_w=$!; ' +
  '( __ci_run=$1; shift; eval "$__ci_run" ) 3>&- 4<&-; __ci_rc=$?; kill $__ci_w 2>/dev/null; times >&3; exit $__ci_rc';

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
  /** The gate's kill timer, ms (gate-timeout.ts gateTimeoutMs). Absent means no timer. */
  timeoutMs?: number;
}

/**
 * EVERY GATE RUNS IN ITS OWN PROCESS GROUP, and this is the table of the live ones. A gate is a tree (bash, npm, sh, node, esbuild, a browser), and killing only the pid the runner spawned leaves the rest running and holding the output pipes, so `close` never fires and the runner waits anyway. The group is the unit both kills address: the per-gate timer and the runner's own SIGTERM/SIGINT handler (`killLiveGates`). Before 2026-10-07 the gates shared the runner's group, so a SIGTERM to the runner alone left every running gate orphaned and still working (measured: `kill -TERM <runner>` exited 143 with the planted gate still alive).
 */
interface LiveGate {
  id: string;
  started: number;
  pgid: number;
}
const LIVE = new Map<number, LiveGate>();

/** The gates running right now, oldest first, with how long each has run. */
export function liveGates(now: number = Date.now()): { id: string; ms: number; pgid: number }[] {
  return [...LIVE.values()]
    .sort((a, b) => a.started - b.started)
    .map((g) => ({ id: g.id, ms: now - g.started, pgid: g.pgid }));
}

/** Signal one gate's whole process group; false when it is already gone. */
function signalGroup(pgid: number, signal: NodeJS.Signals): boolean {
  try {
    process.kill(-pgid, signal);
    return true;
  } catch {
    return false;
  }
}

/** Set once the runner is stopping on a signal: from then on execGate starts nothing, or the pool would launch the next gate into the gap the killed one left. */
let refusing = false;
export function refuseNewGates(): void {
  refusing = true;
}
/** True once refuseNewGates ran, so a caller can stop printing start lines for gates that will never start. */
export function refusingNewGates(): boolean {
  return refusing;
}

/** Signal every live gate's process group; returns how many groups were still there to receive it. */
export function killLiveGates(signal: NodeJS.Signals): number {
  let n = 0;
  for (const g of LIVE.values()) if (signalGroup(g.pgid, signal)) n += 1;
  return n;
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
    // NEVER SETTLES, on purpose: the signal handler exits the process within its grace. Settling would let the pool record a FAIL for a gate that never ran and let the run finish into a footer and a --json document that a capture would upload as a real measurement.
    if (refusing) return;

    // bash, not sh: several gate bodies use bashisms, and npm runs scripts through a shell anyway. stdin is closed so a gate that waits on input fails instead of hanging the whole pool.
    // The gate's declared `env` (the same values its CI step sets) goes into the child. Without it the local run was not the CI run: tutorial-player's PUBLIC_VIDEO_CDN_BASE_URL was declared here and never applied, so the gate failed in every clean clone and passed in CI (2026-09-26). The pool's grant goes in last (`gateEnv`).
    // Windows-native (Git Bash) keeps the bare spawn and reports wall time only: its `times` reports nothing useful for native children.
    const wrapped = process.platform !== 'win32';
    // `detached` makes the outer shell a process-group (and session) leader, so `kill(-pid)` reaches every process of the gate and none of the runner's (see LIVE). Not on Windows-native, where there are no process groups to address.
    const child = spawn(
      'bash',
      wrapped ? ['-c', RUSAGE_WRAPPER, 'bash', spec.run] : ['-c', spec.run],
      {
        cwd: opts.cwd,
        env: gateEnv(spec, opts.grant),
        // fd 3 (the `times` report) and fd 4 (the runner-death watch, never written) are opened on every platform so the spawn has one shape; unwrapped, nothing uses them.
        stdio: ['ignore', 'pipe', 'pipe', 'pipe', 'pipe'],
        detached: wrapped,
      }
    );
    const pgid = wrapped ? child.pid : undefined;
    if (pgid !== undefined) LIVE.set(pgid, { id: spec.id, started, pgid });
    const rusage: string[] = [];
    // Read even when unwrapped: a pipe left paused may never reach EOF, and `close` waits for every stdio stream.
    const fd3 = child.stdio[3];
    if (fd3 !== null && fd3 !== undefined && 'setEncoding' in fd3) {
      fd3.setEncoding('utf8');
      fd3.on('data', (c: string) => {
        rusage.push(c);
      });
    }
    // The watch's runner end: nothing is written either way, but it is drained for the same reason as fd 3, and held by `child` for the gate's whole life, so it closes only when this process does.
    const fd4 = child.stdio[4];
    if (fd4 !== null && fd4 !== undefined && 'resume' in fd4) fd4.resume();

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

    // THE KILL TIMER. SIGTERM to the whole group at the limit, SIGKILL after KILL_GRACE_MS, and a forced settle after twice that: a descendant that put itself in another group (a daemon) can hold the pipes open past every kill, and the runner must still move on and name the gate.
    let timedOut = false;
    let forced = false;
    let settled = false;
    const timers: NodeJS.Timeout[] = [];
    const limit = opts.timeoutMs;
    if (limit !== undefined && limit > 0) {
      timers.push(
        setTimeout(() => {
          timedOut = true;
          if (pgid !== undefined) signalGroup(pgid, 'SIGTERM');
          else child.kill('SIGTERM');
          timers.push(
            setTimeout(() => {
              if (pgid !== undefined) signalGroup(pgid, 'SIGKILL');
              else child.kill('SIGKILL');
            }, KILL_GRACE_MS),
            setTimeout(() => {
              forced = true;
              for (const s of [child.stdout, child.stderr, child.stdio[3], child.stdio[4]])
                s?.destroy();
              settle(null);
            }, 2 * KILL_GRACE_MS)
          );
        }, limit)
      );
    }

    const settle = (code: number | null, extraErr?: string): void => {
      if (settled) return;
      settled = true;
      for (const t of timers) clearTimeout(t);
      if (pgid !== undefined) LIVE.delete(pgid);
      if (timedOut && limit !== undefined) {
        const ms = Date.now() - started;
        // The timer's line REPLACES the signal message: "terminated by signal SIGTERM" would read as something outside the runner killing the gate.
        err.push(
          `ci-runner: gate ${spec.id} TIMED OUT after ${(ms / 1000).toFixed(1)}s (limit ${(limit / 1000).toFixed(0)}s, scripts/ci-runner/gate-timeout.ts); its process group was killed\n` +
            (forced
              ? `ci-runner: a descendant of ${spec.id} outside its process group (setsid, a daemon) still held its output pipes ${(2 * KILL_GRACE_MS) / 1000}s later and was left running; the runner stopped waiting on it\n`
              : '')
        );
        resolve({
          code: null,
          stdout: out.join(''),
          stderr: err.join(''),
          ms,
          timedOutMs: limit,
        });
        return;
      }
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
