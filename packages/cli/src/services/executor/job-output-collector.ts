/**
 * The detached job's output reconstruction (see job-client.ts): the event
 * stream folded back into the stdout, stderr and step timings of a
 * synchronous run.
 */

import type { RenetEvent } from './types.js';

/**
 * Accumulates a detached job's event stream back into the stdout, stderr, and
 * step timings a synchronous run would have produced.
 *
 * This exists because a detached job's spool is ALWAYS NDJSON (`job run` forces
 * events mode, cmd/renet/job_commands.go), so a status-to-result mapping has no
 * captured text to hand back unless it is reconstructed here. The reconstruction
 * is byte-faithful: renet emits the exact same string either as an `output`
 * event or as a `Println` on the synchronous path
 * (cmd/renet/execute_command.go), so concatenating `output` messages
 * newline-terminated reproduces the non-events stdout, bridge relay prefixes and
 * all. That is precisely what `parseCapturedJson` expects.
 *
 * Kept dependency-free and separate from rendering on purpose: capturing the
 * output must not depend on whether, or how, the caller wants it drawn.
 */
export interface JobOutputCollector {
  /** Fold one decoded event into the accumulated output. */
  consume(event: RenetEvent): void;
  /** The reconstructed stdout, byte-faithful with a synchronous run. */
  readonly stdout: string;
  /** The reconstructed stderr (error and warning log lines). */
  readonly stderr: string;
  /** Step timings recovered from `step_done` events. */
  readonly steps: { name: string; duration_ms: number; detail?: string }[];
}

/**
 * The text an `output` event contributes to reconstructed stdout, or ''.
 *
 * renet's non-events path prints each line with Println, which always appends
 * exactly one newline; mirror that byte-for-byte so the reconstruction matches.
 */
function outputEventText(event: RenetEvent): string {
  return event.type === 'output' && event.msg != null ? `${event.msg}\n` : '';
}

/** The text an error/warning `log` event contributes to reconstructed stderr, or ''. */
function logEventText(event: RenetEvent): string {
  const isProblem = event.level === 'error' || event.level === 'warning';
  return event.type === 'log' && isProblem && event.msg != null ? `${event.msg}\n` : '';
}

/** The step timing a `step_done` event contributes, or null when incomplete. */
function stepDoneEntry(
  event: RenetEvent
): { name: string; duration_ms: number; detail?: string } | null {
  if (event.type !== 'step_done' || !event.name || typeof event.duration_ms !== 'number') {
    return null;
  }
  return {
    name: event.name,
    duration_ms: event.duration_ms,
    ...(event.detail ? { detail: event.detail } : {}),
  };
}

export function createJobOutputCollector(): JobOutputCollector {
  let stdout = '';
  let stderr = '';
  const steps: { name: string; duration_ms: number; detail?: string }[] = [];

  return {
    consume(event: RenetEvent): void {
      stdout += outputEventText(event);
      stderr += logEventText(event);
      const step = stepDoneEntry(event);
      if (step) steps.push(step);
    },
    get stdout() {
      return stdout;
    },
    get stderr() {
      return stderr;
    },
    get steps() {
      return steps;
    },
  };
}
