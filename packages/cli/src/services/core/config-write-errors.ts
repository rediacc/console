/**
 * The refusals of a config write made inside an executor request
 * (agent/plans/PLAN-rmcp-writeback.md).
 *
 * A command the hosted executor dispatches runs against a request-scoped config
 * (request-context.ts RequestConfigScope). A write it cannot persist must end the
 * command before any host side effect: the config write precedes the command's
 * machine job, so throwing here means no volume, fork or VM is created whose
 * only record would die with the request.
 */

import { t } from '../../i18n/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { currentRequestContext } from './request-context.js';

/** The served result's error code for a config change the executor cannot save. */
export const CONFIG_WRITE_UNAVAILABLE = 'CONFIG_WRITE_UNAVAILABLE';

/**
 * A version-bumping config write the executor cannot persist. Thrown from the
 * request-scoped write path; the scope records the code so the dispatch reports
 * it as the result's `errorCode`.
 */
export class ConfigWriteUnavailableError extends CliExitError {
  constructor(command: string) {
    super(CONFIG_WRITE_UNAVAILABLE, t('errors.proxy.configWriteUnavailable', { command }));
    this.name = 'ConfigWriteUnavailableError';
  }
}

/** The command the current request runs ("repo create"), for a refusal's message. */
export function currentCommandName(): string {
  return currentRequestContext()?.output.commandName ?? 'unknown';
}
