/**
 * `rdc backup immutability show|set` and `rdc backup undelete`: the delayed-deletion window of the
 * chunk store (D-immutable, decision O4).
 *
 * The window is DELAYED DELETION, enforced by the account server: a snapshot delete, a lineage
 * purge or a retention change that keeps less waits `immutableDays` before it takes effect, and
 * `undelete` (or `purge --cancel`) undoes it until then. It is not store-level immutability, and
 * nothing here calls it that. All of it is control-plane: no machine is reached.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { outputService } from '../services/core/output.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';

/** The longest window the account accepts; it bounds how long an erasure request takes. */
const MAX_WINDOW_DAYS = 30;

/** GET and PUT /backups/immutability. A shortening waits in `pendingDays` until `shortenAfter`. */
interface ImmutabilityResponse {
  immutableDays: number;
  pendingDays: number | null;
  shortenAfter: string | null;
}

/** POST /backups/snapshots/:id/undelete. False when the row was not waiting for deletion. */
interface UndeleteResponse {
  snapshotId: string;
  undeleted: boolean;
}

/** `YYYY-MM-DD HH:MM` (UTC) of an ISO instant. */
const minuteOf = (iso: string): string => iso.replace('T', ' ').slice(0, 16);

/** Parse whole days, 0 to 30. Anything else is refused before a call: a window decides how long deleted data stays recoverable. */
function parseDays(raw: string): number {
  if (!/^\d+$/.test(raw) || Number(raw) > MAX_WINDOW_DAYS) {
    throw new ValidationError(
      t('commands.backup.immutability.set.invalid', { value: raw, max: MAX_WINDOW_DAYS })
    );
  }
  return Number(raw);
}

/** The window in force, and a waiting shortening beside it: the old window keeps applying until the date named. */
function reportWindow(state: ImmutabilityResponse): void {
  outputService.info(
    state.immutableDays > 0
      ? t('commands.backup.immutability.show.window', { days: state.immutableDays })
      : t('commands.backup.immutability.show.off')
  );
  if (state.pendingDays !== null && state.shortenAfter) {
    outputService.warn(
      t('commands.backup.immutability.pending', {
        days: state.pendingDays,
        current: state.immutableDays,
        when: minuteOf(state.shortenAfter),
      })
    );
  }
}

async function runShow(): Promise<void> {
  assertHostedBackupAccount();
  const state = await accountServerFetch<ImmutabilityResponse>(
    '/account/api/v1/backups/immutability'
  );
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(state, format);
    return;
  }
  reportWindow(state);
}

async function runSet(rawDays: string): Promise<void> {
  const days = parseDays(rawDays);
  assertHostedBackupAccount();
  const state = await accountServerFetch<ImmutabilityResponse>(
    '/account/api/v1/backups/immutability',
    { method: 'PUT', body: { immutableDays: days } }
  );
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(state, format);
    return;
  }
  // A raise applies at once; a shortening waits out the old window, and saying "now N days" then would claim a protection the server has not yet reduced.
  if (state.pendingDays !== null && state.shortenAfter) {
    reportWindow(state);
    return;
  }
  outputService.success(
    days > 0
      ? t('commands.backup.immutability.set.applied', { days: state.immutableDays })
      : t('commands.backup.immutability.set.appliedOff')
  );
}

async function runUndelete(snapshotId: string): Promise<void> {
  assertHostedBackupAccount();
  const result = await accountServerFetch<UndeleteResponse>(
    `/account/api/v1/backups/snapshots/${encodeURIComponent(snapshotId)}/undelete`,
    { method: 'POST' }
  );
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(result, format);
    return;
  }
  if (result.undeleted) {
    outputService.success(t('commands.backup.undelete.success', { snapshot: snapshotId }));
  } else {
    outputService.info(t('commands.backup.undelete.notWaiting', { snapshot: snapshotId }));
  }
}

/** Register `backup immutability {show,set}` and `backup undelete`. */
export function registerBackupImmutability(backup: Command): void {
  const immutability = backup
    .command('immutability')
    .description(t('commands.backup.immutability.description'));
  immutability
    .command('show')
    .description(t('commands.backup.immutability.show.description'))
    .action(async () => {
      try {
        await runShow();
      } catch (error) {
        handleError(error);
      }
    });
  immutability
    .command('set')
    .argument('<days>', t('commands.backup.immutability.set.daysArgument'))
    .description(t('commands.backup.immutability.set.description'))
    .action(async (days: string) => {
      try {
        await runSet(days);
      } catch (error) {
        handleError(error);
      }
    });

  backup
    .command('undelete')
    .argument('<snapshot-id>', t('commands.backup.snapshots.snapshotIdArgument'))
    .description(t('commands.backup.undelete.description'))
    .action(async (snapshotId: string) => {
      try {
        await runUndelete(snapshotId);
      } catch (error) {
        handleError(error);
      }
    });
}
