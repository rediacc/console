import { DEFAULTS } from '@rediacc/shared/config';
import { outputService } from '../services/output.js';
import type { LocalExecuteResult } from '../services/local-executor.js';
import { getOutputFormat } from './errors.js';

const LOCAL_EXECUTION_FAILED_CODE = 'LOCAL_EXECUTION_FAILED';

export function renderLocalExecutionFailure(
  result: Pick<LocalExecuteResult, 'error' | 'errorCode' | 'errorGuidance'> & {
    exitCode?: number;
  },
  fallbackMessage: string
): void {
  const message = result.error ?? fallbackMessage;
  const code = result.errorCode ?? LOCAL_EXECUTION_FAILED_CODE;

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
    if (typeof result.exitCode === 'number') {
      process.exitCode = result.exitCode;
    }
    return;
  }

  outputService.error(message);
  if (typeof result.exitCode === 'number') {
    process.exitCode = result.exitCode;
  }
}
