/**
 * Output: quiet on success, complete on failure.
 *
 * TWO DELIBERATE CHOICES, both against the instinct to tidy up.
 *
 * Failure blocks stream the moment a gate fails rather than being held to the
 * end, because an agent tailing a fifteen-minute run should see the first red
 * as it happens.
 *
 * Captured output is printed UNMODIFIED and UNTRUNCATED: no indentation, no
 * head/tail elision. Twenty failing gates is a lot of text, and that is
 * accepted -- truncation is how a diagnostic becomes useless, and the whole
 * point of the runner is that one run surfaces every failure instead of the
 * `&&` chain's first one.
 *
 * See agent/PLAN-npm-ci-parallel-parity.md section 4.4.
 */
import type { GateResult } from './pool';

export interface ReporterOptions {
  /** Column width for gate ids, so the streamed lines align. */
  idWidth: number;
  /** Human-readable stream. */
  out: (text: string) => void;
  /** Machine-readable document sink, used only by footer() under --json. */
  jsonOut?: (text: string) => void;
}

export interface RunMeta {
  jobs: number;
  failFast: boolean;
  /** Human description of a partial selection, e.g. "--only check:ci-*". */
  selection?: string;
  wallMs: number;
}

const RULE = '='.repeat(64);

function secs(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function gates(n: number): string {
  return n === 1 ? '1 gate' : `${n} gates`;
}

function why(result: GateResult): string {
  if (result.vacuity !== undefined) return `exit 0 but ${result.vacuity}`;
  if (result.exitCode === null) return 'killed';
  return `exit ${result.exitCode}`;
}

export function createReporter(opts: ReporterOptions) {
  const pad = (id: string): string => id.padEnd(opts.idWidth);

  return {
    header(gateCount: number, meta: RunMeta): void {
      const mode = meta.failFast ? 'fail-fast' : 'keep-going';
      opts.out(`ci-runner: ${gates(gateCount)}, ${meta.jobs} workers, ${mode}\n`);
      // A partial run reporting green is the vacuity failure this whole
      // design exists to prevent, so the selection is stated loudly at
      // both ends of the output and carried in the JSON as partial:true.
      if (meta.selection !== undefined) {
        opts.out(`ci-runner: PARTIAL RUN, selection: ${meta.selection}\n`);
      }
    },

    // Only under --verbose. At --jobs 1 a five-minute gate otherwise looks
    // exactly like a hang, and ci:serial is the mode you reach for when
    // something is already suspicious.
    start(id: string): void {
      opts.out(`  ..    ${pad(id)}\n`);
    },

    finish(result: GateResult): void {
      if (result.status === 'ok') {
        opts.out(`  ok    ${pad(result.id)} ${secs(result.ms).padStart(7)}\n`);
        return;
      }
      if (result.status === 'skipped') {
        opts.out(`  SKIP  ${pad(result.id)}         ${result.reason ?? ''}\n`);
        return;
      }
      // BLOCKED IS NOT FAIL, AND THE PER-GATE LINE MUST SAY SO. The footer
      // counted the two separately from the start while this line still
      // printed FAIL for both, so a run read "8 failed" above nine FAIL lines.
      // A status that is only honest in the summary is not honest: the reader
      // scanning for what to fix is reading THESE lines.
      if (result.status === 'blocked') {
        opts.out(`BLOCK ${pad(result.id)} ${secs(result.ms).padStart(7)}   could not run here\n`);
        opts.out('  --- why ---\n');
        const why_ = (result.stderr || result.stdout).trim();
        opts.out(
          why_ === '' ? '  (said nothing, which is itself a defect)\n' : ensureNewline(why_)
        );
        opts.out('\n');
        return;
      }
      opts.out(`FAIL  ${pad(result.id)} ${secs(result.ms).padStart(7)}   ${why(result)}\n`);
      opts.out(`  rerun: ${result.rerun}\n`);
      opts.out('  --- stdout ---\n');
      opts.out(result.stdout === '' ? '  (stdout was empty)\n' : ensureNewline(result.stdout));
      opts.out('  --- stderr ---\n');
      opts.out(result.stderr === '' ? '  (stderr was empty)\n' : ensureNewline(result.stderr));
      opts.out('\n');
    },

    footer(results: readonly GateResult[], meta: RunMeta): number {
      const failed = results.filter((r) => r.status === 'fail');
      const skipped = results.filter((r) => r.status === 'skipped');
      const blocked = results.filter((r) => r.status === 'blocked');
      const ok = results.filter((r) => r.status === 'ok');
      const serialMs = results.reduce((sum, r) => sum + r.ms, 0);
      const speedup = meta.wallMs > 0 ? serialMs / meta.wallMs : 0;
      // BLOCKED DOES NOT REDDEN THE RUN. A gate that could not run has said
      // nothing about the code, and treating "this machine lacks ruff" as a
      // finding is what turns a pre-push lane into a wall nobody keeps. It is
      // never silent though -- it is counted below, listed by name with the
      // gate's own message, and recorded in the receipt for the guard to warn
      // on. Under CI the toolchain is present, so a gate exiting CANNOT_RUN
      // there is a broken lane and shows up as a plain non-zero to the workflow.
      const exitCode = failed.length > 0 || skipped.length > 0 ? 1 : 0;

      opts.out(`${RULE}\n`);
      opts.out(
        `${gates(results.length)}: ${ok.length} ok, ${failed.length} failed, ${skipped.length} skipped` +
          (blocked.length > 0 ? `, ${blocked.length} BLOCKED (could not run)` : '') +
          `     wall ${secs(meta.wallMs)} (serial ${secs(serialMs)}, ${speedup.toFixed(1)}x)\n`
      );
      if (meta.selection !== undefined) {
        opts.out(`PARTIAL RUN, selection: ${meta.selection}. This is NOT a full gate run.\n`);
      }
      opts.out(`${RULE}\n`);

      const slowest = [...results].sort((a, b) => b.ms - a.ms).slice(0, 8);
      if (slowest.length > 0 && slowest[0].ms > 0) {
        opts.out('slowest:\n');
        for (const r of slowest) {
          if (r.ms === 0) continue;
          opts.out(`  ${secs(r.ms).padStart(7)}  ${r.id}\n`);
        }
      }

      if (failed.length > 0) {
        opts.out('FAILED:\n');
        for (const r of failed) opts.out(`  ${pad(r.id)}  ${r.rerun}\n`);
      }
      if (skipped.length > 0) {
        opts.out('SKIPPED:\n');
        for (const r of skipped) opts.out(`  ${pad(r.id)}  ${r.reason ?? ''}\n`);
      }
      if (blocked.length > 0) {
        // Named, with the gate's own words. The whole point of the status is
        // that the reader can tell a missing tool from a real finding, and
        // that distinction is only visible if the reason is printed.
        opts.out('BLOCKED (could not run here; NOT a verdict on the code):\n');
        for (const r of blocked) {
          const why = (r.stderr || r.stdout).trim().split('\n').filter(Boolean).slice(-3);
          opts.out(`  ${pad(r.id)}\n`);
          for (const line of why) opts.out(`      ${line}\n`);
        }
      }
      if (failed.length > 0) {
        opts.out('rerun all failures:\n');
        opts.out(`  ${failed.map((r) => r.rerun).join(' && ')}\n`);
      }
      opts.out(`${RULE}\n`);

      opts.jsonOut?.(
        `${JSON.stringify(
          {
            partial: meta.selection !== undefined,
            selection: meta.selection ?? null,
            jobs: meta.jobs,
            failFast: meta.failFast,
            wallMs: meta.wallMs,
            serialMs,
            ok: ok.length,
            failed: failed.length,
            blocked: blocked.length,
            skipped: skipped.length,
            exitCode,
            gates: results,
          },
          null,
          2
        )}\n`
      );

      return exitCode;
    },
  };
}

function ensureNewline(text: string): string {
  return text.endsWith('\n') ? text : `${text}\n`;
}
