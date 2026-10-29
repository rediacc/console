/**
 * Pure unit-content generators for scheduled backups.
 *
 * Everything in this module is deterministic: given the same inputs it
 * produces byte-identical output. That determinism is a contract the
 * reconciler depends on, SHA-256 hashes of the rendered content drive
 * the unchanged/updated classification, so any hidden nondeterminism
 * (timestamps, iteration order) would reclassify every deploy as "updated"
 * and defeat idempotency.
 */

import { createHash } from 'node:crypto';
import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { isSensitiveKey } from '@rediacc/shared/telemetry';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';
import { envFilePath } from './backup-env-file.js';
import type { UnitScope } from './backup-schedule-targets.js';
import {
  assertStrategySchedulable,
  effectiveBandwidthLimit,
  invalidCronReason,
  readCapBytesPerSecond,
  STRATEGY_UPLOAD_PARALLELISM,
} from './backup-strategy-validate.js';

/** SHA-256 hex digest for UTF-8 content, used by the reconciler for diff. */
export function sha256Hex(content: string): string {
  return createHash('sha256').update(content, 'utf8').digest('hex');
}

/** Convert a 5-field cron expression to systemd OnCalendar format. */
export function cronToOnCalendar(cron: string): string {
  const invalid = invalidCronReason(cron);
  if (invalid) throw new Error(invalid);
  const parts = cron.trim().split(/\s+/);

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  const dowMap: Record<string, string> = {
    '0': 'Sun',
    '1': 'Mon',
    '2': 'Tue',
    '3': 'Wed',
    '4': 'Thu',
    '5': 'Fri',
    '6': 'Sat',
    '7': 'Sun',
  };

  const monthPart = month === '*' ? '*' : month.padStart(2, '0');
  const dayPart = dayOfMonth === '*' ? '*' : dayOfMonth.padStart(2, '0');
  const datePart = `*-${monthPart}-${dayPart}`;

  const hourStr = toTimerField(hour);
  const minStr = toTimerField(minute);
  const timePart = `${hourStr}:${minStr}:00`;

  let dowPrefix = '';
  if (dayOfWeek !== '*') {
    const days = dayOfWeek.split(',').map((d) => dowMap[d] ?? d);
    dowPrefix = `${days.join(',')} `;
  }

  return `${dowPrefix}${datePart} ${timePart}`;
}

// systemd's OnCalendar syntax uses `..` for ranges (cron uses `-`) and comma-separated lists. Support list-of-ranges like cron's "0-2,4-23".
function toTimerField(value: string): string {
  if (value === '*') return '*';
  if (value.startsWith('*/')) return `00/${value.slice(2)}`;
  return value
    .split(',')
    .map((part) => {
      const dashIndex = part.indexOf('-');
      if (dashIndex === -1) return part.padStart(2, '0');
      return `${part.slice(0, dashIndex).padStart(2, '0')}..${part
        .slice(dashIndex + 1)
        .padStart(2, '0')}`;
    })
    .join(',');
}

/**
 * Redact sensitive values in rendered commands: the
 * `systemd-run --setenv=KEY=value` form used by on-demand backups. Safe to
 * print in dry-run, debug, and agent contexts.
 */
export function sanitizeBackupOutput(content: string): string {
  return content.replaceAll(
    /--setenv=([A-Z0-9_]+)=(?:'([^']*)'|(\S+))/g,
    (_m, key: string, quoted: string | undefined, _bare: string | undefined) => {
      if (!isSensitiveKey(key.toLowerCase())) return _m;
      return quoted === undefined ? `--setenv=${key}=[REDACTED]` : `--setenv=${key}='[REDACTED]'`;
    }
  );
}

interface BackupBuild {
  commands: string[];
  envVars: Record<string, string>;
}

/**
 * The scheduled command for a chunk-store (hosted-service) destination.
 *
 * Carries NO credentials, which is the whole point of the destination kind:
 * the machine authenticates with its signed repo licence blob and the server
 * hands back a short-lived grant, so nothing sensitive reaches the unit file
 * or its EnvironmentFile.
 *
 * Repositories reach argv as GUIDs only: `--repo <guid>` for an include scope,
 * `--exclude-repo <guid>` otherwise. The scope is resolved from the config by
 * backup-schedule-targets.ts; a name never reaches renet, which refuses one.
 */
function buildChunkStoreCommand(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[],
  datastore: string,
  remoteRenetPath: string,
  scope: UnitScope
): string {
  const parts = [`${remoteRenetPath} backup snapshot`, `--datastore ${datastore}`];
  // `mode: cold` was REFUSED here until 2026-08-15, because `backup snapshot` had no way to express it and scheduling one would have run a HOT snapshot where the operator asked for cold, their stated intent silently inverted. The verb now has --cold, so the mode is emitted instead of rejected.
  //
  // ORDERING HAZARD, and it bites inside a timer at 03:00: renet must be deployed to a machine BEFORE a unit carrying --cold is written to it. An older renet dies at cobra's flag parse, and the failure surfaces as a backup that silently never ran. `backup schedule` seeds the binary first, which is what keeps this in the right order.
  if ((strategy.mode ?? BACKUP_DEFAULTS.MODE) === 'cold') parts.push('--cold');
  if (scope.include) {
    for (const guid of scope.include) parts.push(`--repo ${guid}`);
  } else {
    for (const guid of scope.exclude) parts.push(`--exclude-repo ${guid}`);
  }
  // The cap is the tightest of the strategy's and its destinations' (effectiveBandwidthLimit), in bytes/second. Parallelism is always pinned: a capped run fanned over renet's default workers only queues them on the one budget.
  const bwlimit = effectiveBandwidthLimit(strategy, destinations);
  if (bwlimit !== undefined) parts.push(`--bwlimit ${bwlimit}`);
  parts.push(`--parallelism ${STRATEGY_UPLOAD_PARALLELISM}`);
  // The read cap is strategy level (the read is local, not tied to a destination) and is emitted ONLY when set, so every other unit gets the verb's gentle default and an older renet is not handed a flag it does not know. --hash-parallelism is never emitted: the verb default (1) stands.
  const readCap = readCapBytesPerSecond(strategy.readBandwidthLimit);
  if (readCap !== undefined) parts.push(`--read-bwlimit ${readCap}`);
  return parts.join(' ');
}

/**
 * The scope of a strategy with no include or exclude list. A strategy that has
 * either must be resolved through the config first (strategyUnitSpecs), so this
 * default refuses rather than emitting names or widening to everything.
 */
function unresolvedScope(strategy: BackupStrategyConfig): UnitScope {
  if (strategy.include?.length || strategy.exclude?.length) {
    throw new Error(
      'This backup strategy selects repositories by name; resolve them to GUIDs through the config (strategyUnitSpecs) before rendering a command.'
    );
  }
  return { exclude: [] };
}

/** One command per strategy run + the env-vars for the whole unit. */
export function buildBackupCommands(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[],
  datastore: string,
  remoteRenetPath: string,
  scope: UnitScope = unresolvedScope(strategy)
): BackupBuild {
  const envVars: Record<string, string> = {};

  // A HARD ERROR, not a skip. Emitting nothing is the defect the hosted-service branch was written to fix: a timer that backed up nothing with no error anywhere. The rules live in backup-strategy-validate.ts, shared with `backup strategy bind`. One run is ONE snapshot whatever the number of destinations: a second identical command would upload the same cells again and commit a second manifest for the same point in time.
  assertStrategySchedulable(strategy, destinations);
  return {
    commands: [buildChunkStoreCommand(strategy, destinations, datastore, remoteRenetPath, scope)],
    envVars,
  };
}

/**
 * Jitter for the pre-backup renewal. A fleet of machines whose timers all fire
 * on the hour would otherwise arrive at the account server as one burst; 45s
 * spreads them without meaningfully delaying a backup that routinely runs for
 * hours.
 */
const LICENSE_RENEW_JITTER = '45s';

/**
 * The best-effort licence renewal that runs before every scheduled backup.
 *
 * Scheduled backups validate at the strict Full tier and the machine holds no
 * account credentials, so before self-renewal existed a fork licence simply
 * hard-expired after 7 days and the unattended backup died silently. `renet
 * license renew` presents the installed blob as its own bearer credential, so
 * the machine can refresh without ever holding a token.
 *
 * The `-` prefix on ExecStartPre is doing two jobs and both are load-bearing:
 *   - a renewal the server refuses (one lapsed repo, a network blip) must never
 *     stop the backup of every OTHER repo on the machine;
 *   - a renet older than this feature exits non-zero on the unknown `license`
 *     command, and without the prefix that would take out backups on every
 *     machine whose binary has not been re-provisioned yet.
 */
function licenseRenewCommand(remoteRenetPath: string): string {
  return `-${remoteRenetPath} license renew --jitter ${LICENSE_RENEW_JITTER}`;
}

/**
 * A backup is background work and runs below the repositories it protects, on CPU and on disk: a hosting provider once took a machine offline over a backup's CPU load (operator order 2026-10-29). These are the unit-file form of the `nice -n 10 ionice -c 2 -n 7` prefix (best-effort I/O at its lowest level; the idle class can starve a snapshot without bound) that the renet function puts on an ad-hoc snapshot; the ad-hoc strategy run passes the same three properties to systemd-run. The I/O properties are a no-op under the mq-deadline and none schedulers (the default on virtio and NVMe); there the read cap on the verb (`--read-bwlimit`) carries the bound.
 */
export const LOW_PRIORITY_PROPERTIES = [
  'Nice=10',
  'IOSchedulingClass=best-effort',
  'IOSchedulingPriority=7',
] as const;
const LOW_PRIORITY_DIRECTIVES = LOW_PRIORITY_PROPERTIES.join('\n');

/**
 * The `systemd-run` line `backup run` uses when a strategy has no deployed unit: the strategy's commands (which carry its cap and parallelism) inside a transient unit at the same low priority a scheduled unit gets.
 */
export function buildAdhocSystemdRun(unit: string, commands: string[]): string {
  const props = LOW_PRIORITY_PROPERTIES.map((p) => `-p ${p}`).join(' ');
  const fullCmd = commands.join(' && ');
  return `sudo systemd-run --unit=${unit} --remain-after-exit ${props} /bin/bash -c '${fullCmd.replaceAll("'", "'\\''")}'`;
}

interface ServiceUnitBuild {
  /** Full systemd .service file content. */
  serviceContent: string;
  /** Env vars to write to a 0600 EnvironmentFile= sidecar. */
  envVars: Record<string, string>;
}

/**
 * Generate systemd service unit for a backup strategy. Credentials are
 * returned separately so the caller can write them to the EnvironmentFile=
 * sidecar rather than embedding them in the world-readable unit.
 */
export function generateServiceUnit(
  strategyName: string,
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[],
  datastore: string,
  remoteRenetPath: string,
  scope?: UnitScope
): ServiceUnitBuild {
  const { commands, envVars } = buildBackupCommands(
    strategy,
    destinations,
    datastore,
    remoteRenetPath,
    scope
  );
  const execLines = commands.map((cmd) => `ExecStart=${cmd}`);
  const envFileLine =
    Object.keys(envVars).length > 0 ? `EnvironmentFile=${envFilePath(strategyName)}\n` : '';
  const renewLine = `ExecStartPre=${licenseRenewCommand(remoteRenetPath)}\n`;

  // TimeoutStartSec=infinity: backups can legitimately take > 24 h for a
  // first full seed of a large repo. Any finite cap eventually bites.
  //
  // TimeoutStopSec is what systemd allows renet AFTER a SIGTERM before it SIGKILLs, and the two modes need very different budgets:
  //
  // hot (90s): renet aborts the transfer and deletes its datastore snapshot, bounded at 60s renet-side. Without a window systemd would SIGKILL mid-cleanup and orphan the snapshot. cold (960s): a SIGTERM inside the outage window leaves containers STOPPED, and renet's handler must bring every one of them back before it exits. That restart is bounded at 15 min renet-side
  // (coldRestartTimeout), so a 90s window would SIGKILL mid-restart and leave the repositories down, converting a clean shutdown into the exact outage cold mode exists to keep brief. The budget is the renet bound plus a minute of slack.
  //
  // Reconcile repairs a machine left in that state within a tick, but a backstop measured in minutes is not a reason to hand systemd a knife.
  const stopTimeout = (strategy.mode ?? BACKUP_DEFAULTS.MODE) === 'cold' ? 960 : 90;
  const serviceContent = `[Unit]
Description=Rediacc Scheduled Backup (${strategyName})
After=network-online.target

[Service]
Type=oneshot
${LOW_PRIORITY_DIRECTIVES}
TimeoutStartSec=infinity
TimeoutStopSec=${stopTimeout}
${envFileLine}${renewLine}${execLines.join('\n')}

[Install]
WantedBy=multi-user.target
`;

  return { serviceContent, envVars };
}

/** Generate systemd timer unit for a backup strategy. */
export function generateTimerUnit(strategyName: string, onCalendar: string): string {
  return `[Unit]
Description=Rediacc Backup Timer (${strategyName})

[Timer]
OnCalendar=${onCalendar}
Persistent=true

[Install]
WantedBy=timers.target
`;
}
