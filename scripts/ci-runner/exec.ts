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
 * See agent/PLAN-npm-ci-parallel-parity.md section 4.4.
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import type { GateSpec } from './manifest';

export interface ExecOutcome {
  /** Process exit code. null when the process died on a signal. */
  code: number | null;
  stdout: string;
  stderr: string;
  ms: number;
  /**
   * Set when the process exited 0 but the runner still counts it a failure.
   * Carries the diagnostic to print in place of an exit code.
   */
  vacuity?: string;
}

export interface ExecOptions {
  cwd: string;
  mergeOutput: boolean;
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
 * Mirrors PASS_RE in .ci/scripts/test/run-all.sh:64, including the real ESC
 * byte: an earlier version of that pattern spelled the byte '\x1b', which
 * POSIX ERE reads as the literal text "x1b", so the summary matched nothing at
 * all and every colour-emitting gate test contributed zero visible evidence.
 * Built through fromCharCode so the source carries no raw control character.
 */
const PASS_LINE = new RegExp(`^(?:${String.fromCharCode(27)}\\[0;32m)?PASS:`, 'm');

/**
 * run-all.sh:74-81 counts a gate test that exits 0 without emitting a single
 * PASS: line as a FAILURE, because it asserted nothing. Flattening the battery
 * into the pool would silently drop that rule and leave those 57 tests weaker
 * locally than they are in CI, so the runner carries it instead.
 */
function vacuityCheck(spec: GateSpec, code: number | null, output: string): string | undefined {
  if (spec.qualityGateTest !== true || code !== 0) return undefined;
  if (PASS_LINE.test(output)) return undefined;
  return 'exited 0 without a single PASS: line (asserted nothing)';
}

export function execGate(spec: GateSpec, opts: ExecOptions): Promise<ExecOutcome> {
  return new Promise((resolve) => {
    const started = Date.now();
    const out: string[] = [];
    const err: string[] = [];

    // bash, not sh: several gate bodies use bashisms, and npm runs scripts
    // through a shell anyway. stdin is closed so a gate that waits on input
    // fails instead of hanging the whole pool.
    const child = spawn('bash', ['-c', spec.run], {
      cwd: opts.cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    // RECORDS MUST LAND OUTSIDE THE REPO. A relative or in-tree profileDir writes
    // capture files into the working tree -- the ci-runner's own selftest did exactly
    // that and left selftest_pass.jsonl / selftest_fail.jsonl at the repo root. An
    // unusable directory means no profile, never a file in the tree.
    const profileDir =
      opts.profileDir !== undefined &&
      path.isAbsolute(opts.profileDir) &&
      !path.resolve(opts.profileDir).startsWith(path.resolve(opts.cwd) + path.sep)
        ? opts.profileDir
        : undefined;
    if (profileDir !== undefined && child.pid !== undefined && spec.noProfile !== true) {
      // Detached and unreferenced: the runner must not wait on the sampler, and the
      // sampler must not keep the runner alive. `--t0` is the absolute clock E4 needs
      // to decide whether two gates' lifetimes overlapped.
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
            // 500, not 2000: measured on the first profiled run, p50 gate wall was 4.0 s and
            // 224 of 293 gates finished under 6 s, so a 2 s tick left 221 captures with one
            // or two samples -- unjudgeable by the sampler's own anti-vacuity rule. Every
            // tick is forkless /proc reads, so the finer cadence costs nothing that matters.
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

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (c: string) => {
      out.push(c);
    });
    child.stderr.on('data', (c: string) => {
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
        vacuity: vacuityCheck(spec, code, stdout + stderr),
      });
    };

    child.on('error', (e: Error) => {
      settle(127, `ci-runner: could not spawn gate: ${e.message}\n`);
    });
    child.on('close', (code, signal) => {
      if (signal === null) settle(code);
      else settle(null, `ci-runner: gate terminated by signal ${signal}\n`);
    });
  });
}
