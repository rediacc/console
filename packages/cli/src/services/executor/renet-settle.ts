import type { JobOutputCollector } from './job-client.js';
import { buildRenetExitError } from './renet-output.js';

/**
 * Events mode: renet sends the failure reason (the child's stderr detail) as an error-level log event, so the raw ssh stderr alone is empty. Fold the collector's error/warning lines in so the exit error and the failure echo carry the reason.
 */
export function mergeEventsStderr(rawStderr: string, eventStderr: string): string {
  if (!eventStderr) return rawStderr;
  return rawStderr && !rawStderr.endsWith('\n')
    ? `${rawStderr}\n${eventStderr}`
    : rawStderr + eventStderr;
}

/**
 * The post-run step of an executed renet command: reconstruct stdout and stderr, and build the exit error and the combined output. A failed events-mode run folds the collector's log lines in. A successful one does not: warnings reach the operator live from the event stream (daemon/client.ts renders every warning event, createStdoutHandler forwards to options.onEvent), and merging them again would feed them to surfaceRenetWarnings a second time.
 */
export function settleRenetRun(input: {
  exitCode: number;
  stdout: string;
  stderr: string;
  collector?: Pick<JobOutputCollector, 'stdout' | 'stderr'>;
  machineName?: string;
}): { stdout: string; stderr: string; combined: string; error: string | undefined } {
  const { exitCode, collector, machineName } = input;
  const stdout = collector ? collector.stdout : input.stdout;
  const stderr =
    collector && exitCode !== 0 ? mergeEventsStderr(input.stderr, collector.stderr) : input.stderr;
  return {
    stdout,
    stderr,
    combined: stdout + stderr,
    error: exitCode === 0 ? undefined : buildRenetExitError(exitCode, stderr, stdout, machineName),
  };
}
