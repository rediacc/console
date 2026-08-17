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
 * See agent/0731-2/PLAN-npm-ci-parallel-parity.md section 4.4.
 */
import { spawn } from 'node:child_process';
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
