/**
 * Pure builders for the verification commands and calendar of a scheduled backup (F9, F12).
 *
 * No imports from the unit generator, which imports this module: the generator owns the unit text (directives,
 * priority, quotas) and this module owns the renet argv and the strategy `verify` block's meaning.
 *
 * Every argv here is parsed against renet's declared flags by backup-schedule-renet-contract.test.ts. None of them
 * carries `--accept-identity-change`: a scheduled unit never forces an identity change (D-identity).
 */

import { createHash } from 'node:crypto';
import type { BackupStrategyConfig } from '../../types/index.js';
import type { UnitScope } from './backup-schedule-targets.js';
import { readCapBytesPerSecond } from './backup-strategy-validate.js';

/** `--next-due` of the timer: a repository is picked only once its last verify is this old. */
const FULL_VERIFY_NEXT_DUE = '7d';

export interface VerifySettings {
  off: boolean;
  spotAfterRun: boolean;
  deepSchedule?: string;
}

export function verifySettings(strategy: BackupStrategyConfig): VerifySettings {
  const v = strategy.verify;
  return {
    off: v?.off === true,
    spotAfterRun: v?.spotAfterRun !== false,
    deepSchedule: v?.deepSchedule,
  };
}

/** Unit key suffixes. A dot separator, like the repo-override units, so remote scans parse them as strategies of their own. */
export const VERIFY_UNIT_SUFFIX = '.verify';
export const ALERT_UNIT_SUFFIX = '.alert';

export function alertUnitFileName(unitName: string): string {
  return `rediacc-backup-${unitName}${ALERT_UNIT_SUFFIX}.service`;
}

/** `--repo <guid>` for an include scope, `--exclude-repo <guid>` otherwise, as the snapshot command carries them. */
export function scopeFlags(scope: UnitScope): string[] {
  return scope.include
    ? scope.include.map((guid) => `--repo ${guid}`)
    : scope.exclude.map((guid) => `--exclude-repo ${guid}`);
}

function head(renet: string, verb: string, datastore: string, scope: UnitScope): string[] {
  return [`${renet} backup ${verb}`, `--datastore ${datastore}`, ...scopeFlags(scope)];
}

/** The verify run at the end of the snapshot service. */
export function spotVerifyCommand(renet: string, datastore: string, scope: UnitScope): string {
  return [...head(renet, 'verify', datastore, scope), '--level spot'].join(' ');
}

/** The timer's rotating full verify. The read cap is emitted only when the strategy sets one, so renet's default (50M) otherwise stands. */
export function fullVerifyCommand(
  renet: string,
  datastore: string,
  scope: UnitScope,
  strategy: BackupStrategyConfig
): string {
  const parts = [
    ...head(renet, 'verify', datastore, scope),
    '--level full',
    `--next-due ${FULL_VERIFY_NEXT_DUE}`,
  ];
  const readCap = readCapBytesPerSecond(strategy.readBandwidthLimit);
  if (readCap !== undefined) parts.push(`--read-bwlimit ${readCap}`);
  return parts.join(' ');
}

/** The failure report: a fixed reason that names the unit and carries nothing from the config. */
export function failureReportCommand(
  renet: string,
  datastore: string,
  scope: UnitScope,
  failedUnit: string,
  kind: 'snapshot' | 'verify'
): string {
  const level = kind === 'verify' ? ' --level full' : '';
  return [
    ...head(renet, 'report', datastore, scope),
    `--kind ${kind}${level}`,
    '--status failed',
    `--reason 'systemd unit ${failedUnit} failed'`,
  ].join(' ');
}

/**
 * When the full-verify timer fires: the strategy's `deepSchedule`, else daily at a time derived from the unit name
 * (01:00 to 05:59), so units on one machine and machines across a fleet do not all verify in the same minute.
 * Deterministic, since the rendered text is hashed. The cron conversion is passed in because the unit generator owns it and imports this module.
 */
export function verifyOnCalendar(
  unitName: string,
  settings: VerifySettings,
  cronToCalendar: (cron: string) => string
): string {
  if (settings.deepSchedule) return cronToCalendar(settings.deepSchedule);
  const digest = createHash('sha256').update(unitName, 'utf8').digest();
  const hour = 1 + (digest[0] % 5);
  const minute = digest[1] % 60;
  return `*-*-* ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`;
}
