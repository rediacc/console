/**
 * The spinner-and-timing wrapper around one slow step of a call (see local-executor.ts).
 */

import { t } from '../../i18n/index.js';
import { formatDuration } from '../../utils/format.js';
import { startSpinner, stopSpinner } from '../../utils/spinner.js';
import { outputService } from '../core/output.js';

/** Run a step with spinner + timing. Shows "Loading..." then "✓ Loaded (1.2s)" on the same line. */
export async function timedStep<T>(
  spinnerText: string,
  successKey: string,
  fn: () => Promise<T>
): Promise<T> {
  const start = Date.now();
  const spinner = startSpinner(spinnerText);
  try {
    const result = await fn();
    const successText = t(successKey, { duration: formatDuration(Date.now() - start) });
    if (spinner) {
      stopSpinner(true, successText);
    } else {
      outputService.info(successText);
    }
    return result;
  } catch (error) {
    if (spinner) stopSpinner(false);
    throw error;
  }
}
