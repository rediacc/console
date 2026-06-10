import { DEFAULTS } from '@rediacc/shared/config';
import type { LocalExecuteResult } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { isAgentEnvironment } from './agent-guard.js';
import { getOutputFormat } from './errors.js';

const LOCAL_EXECUTION_FAILED_CODE = 'LOCAL_EXECUTION_FAILED';

const MAX_OUTPUT_TAIL_CHARS = 500;

/**
 * Tail of the captured renet output worth showing under the error: adds the
 * raw context when the one-line `result.error` reason isn't enough. Returns
 * undefined when there is nothing new to show (empty, or already contained
 * in the message).
 */
function failureOutputTail(message: string, stderr?: string, stdout?: string): string | undefined {
  const output = (stderr?.trim() ? stderr : stdout)?.trim();
  if (!output) return undefined;

  const tail =
    output.length > MAX_OUTPUT_TAIL_CHARS ? `…${output.slice(-MAX_OUTPUT_TAIL_CHARS)}` : output;
  // Single-line tails that the enriched error already carries add nothing.
  if (!tail.includes('\n') && message.includes(tail.replace(/^Error:\s*/, ''))) {
    return undefined;
  }
  return tail;
}

export function renderLocalExecutionFailure(
  result: Pick<
    LocalExecuteResult,
    'error' | 'errorCode' | 'errorGuidance' | 'stderr' | 'stdout' | 'outputEchoed'
  > & {
    exitCode?: number;
  },
  fallbackMessage: string
): void {
  const message = result.error ?? fallbackMessage;
  const code = result.errorCode ?? LOCAL_EXECUTION_FAILED_CODE;
  const exitCode = typeof result.exitCode === 'number' ? result.exitCode : 1;
  // Skip the tail when the executor already echoed the full output
  // (non-capture failure path).
  const outputTail = result.outputEchoed
    ? undefined
    : failureOutputTail(message, result.stderr, result.stdout);

  if (getOutputFormat() === 'json') {
    const envelope = {
      success: false,
      command: outputService.getCommandName() ?? DEFAULTS.TELEMETRY.UNKNOWN,
      data: null,
      errors: [
        {
          code,
          message,
          guidance: result.errorGuidance,
          retryable: false,
        },
      ],
      warnings: outputService.getWarnings(),
      metrics: { duration_ms: outputService.getDurationMs() },
    };
    process.stdout.write(`${JSON.stringify(envelope, null, 2)}\n`);

    // In agent mode, exit immediately so truncated output can't hide the error
    if (isAgentEnvironment()) {
      process.exit(exitCode);
    }
    process.exitCode = exitCode;
    return;
  }

  outputService.error(message);
  if (outputTail) {
    process.stderr.write(`--- renet output ---\n${outputTail}\n---\n`);
  }
  if (isAgentEnvironment()) {
    process.exit(exitCode);
  }
  process.exitCode = exitCode;
}
