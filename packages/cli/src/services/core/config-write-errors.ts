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

import { TELEMETRY_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { currentRequestContext } from './request-context.js';

/** The served result's error code for a config change the executor has no store to save to. */
export const CONFIG_WRITE_UNAVAILABLE = 'CONFIG_WRITE_UNAVAILABLE';
/** The served result's error code for a push that kept losing the compare-and-swap. */
const CONFIG_CONFLICT = 'CONFIG_CONFLICT';
/** The served result's error code for a push the config store refused or never answered. */
const CONFIG_WRITE_FAILED = 'CONFIG_WRITE_FAILED';

/**
 * A version-bumping config write the executor cannot persist: the request scope
 * has no writeback. The scope records the code so the dispatch reports it as the
 * result's `errorCode`.
 */
export class ConfigWriteUnavailableError extends CliExitError {
  constructor(command: string) {
    super(CONFIG_WRITE_UNAVAILABLE, t('errors.proxy.configWriteUnavailable', { command }));
    this.name = 'ConfigWriteUnavailableError';
  }
}

/** A push that lost the compare-and-swap on every replay: another writer kept changing the config. */
export class ConfigConflictError extends CliExitError {
  constructor(command: string, attempts: number) {
    super(
      CONFIG_CONFLICT,
      t('errors.proxy.configConflict', { command, attempts: String(attempts) }),
      { retryable: true }
    );
    this.name = 'ConfigConflictError';
  }
}

/** A push the config store refused, or could not be reached for; `reason` is the store's own answer. */
export class ConfigWriteFailedError extends CliExitError {
  constructor(command: string, reason: string, options: { retryable?: boolean } = {}) {
    super(CONFIG_WRITE_FAILED, t('errors.proxy.configWriteFailed', { command, reason }), {
      retryable: options.retryable ?? false,
    });
    this.name = 'ConfigWriteFailedError';
  }
}

/** The error code of a failed request-scoped write: the error's own when it carries one. */
export function configWriteFailureCode(error: unknown): string {
  return error instanceof CliExitError ? error.code : CONFIG_WRITE_FAILED;
}

/** The command the current request runs ("repo create"), for a refusal's message. */
export function currentCommandName(): string {
  return currentRequestContext()?.output.commandName ?? TELEMETRY_DEFAULTS.UNKNOWN;
}
