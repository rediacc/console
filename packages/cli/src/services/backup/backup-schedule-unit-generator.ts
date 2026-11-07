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
import { formatDuration } from '@rediacc/shared/backup/duration';
import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { isSensitiveKey } from '@rediacc/shared/telemetry';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { envFilePath } from './backup-env-file.js';
import { cronMaxGapSeconds } from './backup-schedule-interval.js';
import type { UnitRun, UnitScope } from './backup-schedule-targets.js';
import {
  ALERT_UNIT_SUFFIX,
  alertUnitFileName,
  failureReportCommand,
  fullVerifyCommand,
  scopeFlags,
  spotVerifyCommand,
  VERIFY_UNIT_SUFFIX,
  verifyOnCalendar,
  verifySettings,
} from './backup-schedule-verify.js';
import {
  assertStrategySchedulable,
  cpuQuotaValue,
  DEFAULT_CPU_LIMIT_PERCENT,
  destinationTarget,
  effectiveBandwidthLimit,
  HOME_STORE_ID,
  invalidCronReason,
  parseCpuLimitPercent,
  readCapBytesPerSecond,
  STRATEGY_UPLOAD_PARALLELISM,
} from './backup-strategy-validate.js';

/** renet's flag on every chunk-store session verb (private/renet cmd/renet/backup_endpoints.go flagExpectAccountServer). */
export const EXPECT_ACCOUNT_SERVER_FLAG = '--expect-account-server';

/** renet's flag naming the registered store a session writes to (private/renet, box R2). */
export const STORE_FLAG = '--store';

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

/** The run deadline never drops below this: a repo needs room to hash, upload and commit. */
const DEADLINE_FLOOR_SECONDS = 600;
/** ... and never rises above this: a run past two hours is hung, and the next tick should take its place. */
const DEADLINE_CAP_SECONDS = 7200;
/** Headroom the systemd backstop adds beyond twice the deadline. */
const START_TIMEOUT_SLACK_SECONDS = 600;
/** Cap of the timer's randomized delay. */
const JITTER_CAP_SECONDS = 60;

/** The run deadline of a target: three times its length, clamped to 10 minutes .. 2 hours (D-rpo). */
function deadlineSeconds(targetSeconds: number): number {
  return Math.min(Math.max(3 * targetSeconds, DEADLINE_FLOOR_SECONDS), DEADLINE_CAP_SECONDS);
}

/** The finite `TimeoutStartSec=` backstop of a target unit: 2 x deadline + 10 minutes. renet ends the run at the deadline itself; this only covers a renet that cannot. */
function startTimeoutSeconds(targetSeconds: number): number {
  return 2 * deadlineSeconds(targetSeconds) + START_TIMEOUT_SLACK_SECONDS;
}

/** The timer's randomized delay: min(T/5, 60s), the same figure renet's nextExpected arithmetic assumes. */
function jitterSeconds(targetSeconds: number): number {
  return Math.min(Math.floor(targetSeconds / 5), JITTER_CAP_SECONDS);
}

/**
 * The flags a unit's run settings add to the verb. The verb's own defaults stand for anything unset,
 * and `--cell-bytes` in particular is omitted unless chosen: 0 keeps the repository's recorded grid.
 * `--accept-grid-change` is never emitted, so a scheduled unit cannot re-seed a repository.
 *
 * A target replaces `--expected-interval`: renet derives the next expected run from the target, its
 * jitter and its grace, which a cron's longest gap cannot express.
 */
function runFlags(run: UnitRun | undefined): string[] {
  if (!run) return [];
  const flags: string[] = [];
  if (run.rpoSeconds !== undefined) {
    flags.push(
      `--target ${formatDuration(run.rpoSeconds)}`,
      `--deadline ${formatDuration(deadlineSeconds(run.rpoSeconds))}`
    );
  }
  if (run.hookTimeoutSeconds !== undefined) {
    flags.push(`--hook-timeout ${formatDuration(run.hookTimeoutSeconds)}`);
  }
  if (run.hookFailure !== undefined) flags.push(`--hook-failure ${run.hookFailure}`);
  if (run.indexEverySeconds !== undefined) {
    flags.push(`--index-every ${formatDuration(run.indexEverySeconds)}`);
  }
  if (run.cellBytes !== undefined) flags.push(`--cell-bytes ${run.cellBytes}`);
  return flags;
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
  scope: UnitScope,
  cpuCount: number | undefined,
  schedule: string,
  run: UnitRun | undefined,
  accountServer: string | undefined,
  storeFlag: string | undefined
): string {
  const parts = [`${remoteRenetPath} backup snapshot`, `--datastore ${datastore}`];
  // `mode: cold` was REFUSED here until 2026-08-15, because `backup snapshot` had no way to express it and scheduling one would have run a HOT snapshot where the operator asked for cold, their stated intent silently inverted. The verb now has --cold, so the mode is emitted instead of rejected.
  //
  // ORDERING HAZARD, and it bites inside a timer at 03:00: renet must be deployed to a machine BEFORE a unit carrying --cold is written to it. An older renet dies at cobra's flag parse, and the failure surfaces as a backup that silently never ran. `backup schedule` seeds the binary first, which is what keeps this in the right order.
  if ((strategy.mode ?? BACKUP_DEFAULTS.MODE) === 'cold') parts.push('--cold');
  parts.push(...scopeFlags(scope));
  if (storeFlag !== undefined) parts.push(`${STORE_FLAG} ${storeFlag}`);
  // The cap is the tightest of the strategy's and this command's destination's (effectiveBandwidthLimit), in bytes/second. Parallelism is always pinned: a capped run fanned over renet's default workers only queues them on the one budget.
  const bwlimit = effectiveBandwidthLimit(strategy, destinations);
  if (bwlimit !== undefined) parts.push(`--bwlimit ${bwlimit}`);
  parts.push(`--parallelism ${STRATEGY_UPLOAD_PARALLELISM}`);
  // Without the cadence nothing sends `nextExpectedAt` with the commit, and the server's dead-man check (a stream whose next run is overdue) stays silent for exactly the machine that stopped running. The longest gap of the unit's own cron is used, so a weekday-only schedule does not alarm over a weekend.
  if (run?.rpoSeconds === undefined)
    parts.push(`--expected-interval ${cronMaxGapSeconds(schedule)}s`);
  parts.push(...runFlags(run));
  // The read cap is strategy level (the read is local, not tied to a destination) and is emitted ONLY when set, so every other unit gets the verb's gentle default and an older renet is not handed a flag it does not know. --hash-parallelism is never emitted: the verb default (1) stands.
  const readCap = readCapBytesPerSecond(strategy.readBandwidthLimit);
  if (readCap !== undefined) parts.push(`--read-bwlimit ${readCap}`);
  parts.push(...cpuFlags(strategy, cpuCount));
  parts.push(...accountServerFlags(accountServer));
  return parts.join(' ');
}

/**
 * The `--expect-account-server` flag of a scheduled command: the config's account-server origin, so renet refuses a
 * licence from another account universe at 03:00, where the CLI's pre-flight never runs. The origin is a URL origin
 * (scheme, host, port), which carries no space and no `%`, so it needs no quoting and no systemd specifier escape.
 */
export function accountServerFlags(accountServer: string | undefined): string[] {
  return accountServer ? [`${EXPECT_ACCOUNT_SERVER_FLAG} ${accountServer}`] : [];
}

/** The `--cpu-limit` and `--cpu-quota` flags of a scheduled command. The ceiling itself is the unit's CPUQuota= (cpuQuotaDirective); the flags only make the snapshot record say what bound it. Emitted only with a resolved core count, like the directive. */
function cpuFlags(strategy: BackupStrategyConfig, cpuCount: number | undefined): string[] {
  if (cpuCount === undefined) return [];
  const limit = cpuLimitOf(strategy);
  const quota = cpuQuotaValue(limit, cpuCount);
  return quota === undefined
    ? [`--cpu-limit ${limit}`]
    : [`--cpu-limit ${limit}`, `--cpu-quota ${quota}`];
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

/**
 * The `--store` argument of one destination's command, or undefined to omit it.
 *
 * A destination on `home` omits it, so a single-destination timer reads the same on a released renet. A destination on
 * any other store REFUSES when the machine's renet lacks the flag: dropping it would write that destination's snapshot
 * into `home`, the wrong-store write the flag exists to prevent.
 */
function storeArgument(
  dest: BackupStrategyDestination,
  renetHasStoreFlag: boolean
): string | undefined {
  const target = destinationTarget(dest);
  if (target === HOME_STORE_ID) return undefined;
  if (!renetHasStoreFlag) {
    throw new Error(
      `Backup destination "${dest.name}" targets the store "${target}", but the renet on this machine does not list ${STORE_FLAG}. Update renet on the machine, or point the destination at "${HOME_STORE_ID}".`
    );
  }
  return target;
}

/**
 * One command per enabled destination, in declaration order, each carrying its own `--store` and bandwidth cap, plus the
 * env-vars for the whole unit. Every command is its own session, lease and commit, so each destination is a separate
 * recovery point; {@link isolateCommands} keeps one failure from skipping the next. With no destination at all one
 * command is emitted, as before.
 *
 * `renetHasStoreFlag` says the machine's renet lists `--store` (see storeFlagForRenet); it defaults to false, which
 * omits the flag and refuses any destination that needs it.
 */
export function buildBackupCommands(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[],
  datastore: string,
  remoteRenetPath: string,
  scope: UnitScope = unresolvedScope(strategy),
  cpuCount?: number,
  schedule: string = strategy.schedule,
  run?: UnitRun,
  accountServer?: string,
  renetHasStoreFlag = false
): BackupBuild {
  const envVars: Record<string, string> = {};

  // A HARD ERROR, not a skip. Emitting nothing is the defect the hosted-service branch was written to fix: a timer that backed up nothing with no error anywhere. The rules live in backup-strategy-validate.ts, shared with `backup strategy bind`.
  assertStrategySchedulable(strategy, destinations);
  const perDestination: (BackupStrategyDestination | undefined)[] =
    destinations.length > 0 ? destinations : [undefined];
  const commands = perDestination.map((dest) =>
    buildChunkStoreCommand(
      strategy,
      dest ? [dest] : [],
      datastore,
      remoteRenetPath,
      scope,
      cpuCount,
      schedule,
      run,
      accountServer,
      dest ? storeArgument(dest, renetHasStoreFlag) : undefined
    )
  );
  return { commands, envVars };
}

/**
 * The ExecStart= commands of a unit, with the snapshot commands isolated from one another.
 *
 * systemd stops a oneshot at its first failing ExecStart=, which would skip every later destination, and `ExecStart=-`
 * would run them all but report success. With more than one command they run in ONE `sh -c`: each is followed by
 * `|| rc=1`, so the next still runs, and the shell exits non-zero when any failed, which is what OnFailure= and the
 * dead-man check key on. `$$` is systemd's escape for a literal dollar sign. A single command stays bare.
 */
export function isolateCommands(commands: string[]): string[] {
  if (commands.length <= 1) return commands;
  const script = `rc=0; ${commands.map((c) => `${c} || rc=1;`).join(' ')} exit $$rc`;
  return [`/bin/sh -c ${shellQuote(script)}`];
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
const LOW_PRIORITY_PROPERTIES = [
  'Nice=10',
  'IOSchedulingClass=best-effort',
  'IOSchedulingPriority=7',
] as const;
const LOW_PRIORITY_DIRECTIVES = LOW_PRIORITY_PROPERTIES.join('\n');

/** A strategy's CPU ceiling in percent of all cores: its own, validated, or the default of 50. */
function cpuLimitOf(strategy: BackupStrategyConfig): number {
  return strategy.cpuLimit === undefined
    ? DEFAULT_CPU_LIMIT_PERCENT
    : parseCpuLimitPercent(strategy.cpuLimit);
}

/**
 * The `CPUQuota=` line of a scheduled unit, or '' when no ceiling applies. systemd has no "share of all cores" syntax, only a percent of ONE core, so the quota is percent x cores and the core count has to be known when the unit is written. It is read on the machine itself (`nproc`, the count renet's own scope uses, see resolveMachineCpuCount in backup-schedule.ts), because the operator's workstation, a config field or an inventory number can each name a different machine's size. Without a count no directive is written: a guessed core count would be a wrong quota, and the deploy path refuses to render without one.
 */
function cpuQuotaDirective(strategy: BackupStrategyConfig, cpuCount: number | undefined): string {
  if (cpuCount === undefined) return '';
  const quota = cpuQuotaValue(cpuLimitOf(strategy), cpuCount);
  return quota === undefined ? '' : `CPUQuota=${quota}\n`;
}

/**
 * The transient service `backup run` starts for a strategy with no deployed unit (PLAN-detached-jobs section 21): the
 * strategy's commands (which carry its cap and parallelism) as sequential `ExecStart=` lines of a oneshot unit at the
 * same low priority a scheduled unit gets. It is written to the machine first so the backup-unit job can start it by
 * name, which a `systemd-run` line could not be. The core count comes from the machine (`resolveMachineCpuCount`),
 * as for a scheduled unit; 100 asks for no ceiling and writes no directive.
 */
export function generateAdhocServiceUnit(
  strategyName: string,
  commands: string[],
  cpuCount: number,
  cpuLimit: number = DEFAULT_CPU_LIMIT_PERCENT
): string {
  const quota = cpuQuotaValue(parseCpuLimitPercent(cpuLimit), cpuCount);
  const quotaLine = quota === undefined ? '' : `CPUQuota=${quota}\n`;
  return `[Unit]
Description=Rediacc Ad-hoc Backup (${strategyName})
After=network-online.target

[Service]
Type=oneshot
${LOW_PRIORITY_DIRECTIVES}
${quotaLine}TimeoutStartSec=infinity
TimeoutStopSec=90
${isolateCommands(commands)
  .map((cmd) => `ExecStart=${cmd}`)
  .join('\n')}
`;
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
  scope?: UnitScope,
  cpuCount?: number,
  schedule: string = strategy.schedule,
  run?: UnitRun,
  accountServer?: string,
  renetHasStoreFlag = false
): ServiceUnitBuild {
  const { commands, envVars } = buildBackupCommands(
    strategy,
    destinations,
    datastore,
    remoteRenetPath,
    scope,
    cpuCount,
    schedule,
    run,
    accountServer,
    renetHasStoreFlag
  );
  // The spot verify is a second ExecStart of a oneshot unit: systemd runs them in order and stops at the first failure, so a failed snapshot is never verified, and a failed verify fails the unit (and with it OnFailure=). It carries the snapshot's scope; `scope ?? unresolved` already threw above for a name-bearing strategy.
  const verify = verifySettings(strategy);
  const verifyLines: string[] = [];
  if (!verify.off && verify.spotAfterRun) {
    verifyLines.push(spotVerifyCommand(remoteRenetPath, datastore, scope ?? { exclude: [] }));
  }
  const execLines = [
    ...isolateCommands(commands).map((cmd) => `ExecStart=${cmd}`),
    ...verifyLines.map((cmd) => `ExecStart=${cmd}`),
  ];
  const envFileLine =
    Object.keys(envVars).length > 0 ? `EnvironmentFile=${envFilePath(strategyName)}\n` : '';
  const renewLine = `ExecStartPre=${licenseRenewCommand(remoteRenetPath)}\n`;

  // TimeoutStartSec=infinity: backups can legitimately take > 24 h for a
  // first full seed of a large repo. Any finite cap eventually bites.
  //
  // A unit with a declared target is the exception: renet ends the run at its deadline and hands a first seed to a detached unit, so the run is bounded, and a finite backstop (2 x deadline + 10 minutes) is what lets a hung run release its slot for the next tick. RuntimeMaxSec= is NOT used: systemd documents it as having no effect on Type=oneshot.
  //
  // TimeoutStopSec is what systemd allows renet AFTER a SIGTERM before it SIGKILLs, and the two modes need very different budgets:
  //
  // hot (90s): renet aborts the transfer and deletes its datastore snapshot, bounded at 60s renet-side. Without a window systemd would SIGKILL mid-cleanup and orphan the snapshot. cold (960s): a SIGTERM inside the outage window leaves containers STOPPED, and renet's handler must bring every one of them back before it exits. That restart is bounded at 15 min renet-side
  // (coldRestartTimeout), so a 90s window would SIGKILL mid-restart and leave the repositories down, converting a clean shutdown into the exact outage cold mode exists to keep brief. The budget is the renet bound plus a minute of slack.
  //
  // Reconcile repairs a machine left in that state within a tick, but a backstop measured in minutes is not a reason to hand systemd a knife.
  const startTimeout =
    run?.rpoSeconds === undefined ? 'infinity' : String(startTimeoutSeconds(run.rpoSeconds));
  const stopTimeout = (strategy.mode ?? BACKUP_DEFAULTS.MODE) === 'cold' ? 960 : 90;
  const serviceContent = `[Unit]
Description=Rediacc Scheduled Backup (${strategyName})
After=network-online.target
OnFailure=${alertUnitFileName(strategyName)}

[Service]
Type=oneshot
${LOW_PRIORITY_DIRECTIVES}
${cpuQuotaDirective(strategy, cpuCount)}TimeoutStartSec=${startTimeout}
TimeoutStopSec=${stopTimeout}
${envFileLine}${renewLine}${execLines.join('\n')}

[Install]
WantedBy=multi-user.target
`;

  return { serviceContent, envVars };
}

/**
 * Generate systemd timer unit for a backup strategy.
 *
 * A target timer adds a stable per-timer offset (`RandomizedDelaySec` with `FixedRandomDelay`), so many
 * repositories on one machine do not all mint a session in the same second, and `AccuracySec=1s` so
 * that offset is not blurred by systemd's default one-minute coalescing.
 */
export function generateTimerUnit(
  strategyName: string,
  onCalendar: string,
  targetSeconds?: number
): string {
  const jitter =
    targetSeconds === undefined
      ? ''
      : `RandomizedDelaySec=${jitterSeconds(targetSeconds)}s\nFixedRandomDelay=true\nAccuracySec=1s\n`;
  return `[Unit]
Description=Rediacc Backup Timer (${strategyName})

[Timer]
OnCalendar=${onCalendar}
${jitter}Persistent=true

[Install]
WantedBy=timers.target
`;
}

/** The unit-name keys of the verification units rendered beside a strategy unit. */
export function verifyUnitName(unitName: string): string {
  return `${unitName}${VERIFY_UNIT_SUFFIX}`;
}

export function alertUnitName(unitName: string): string {
  return `${unitName}${ALERT_UNIT_SUFFIX}`;
}

/**
 * The full-verify service the daily timer starts: one repository per run (renet's `--next-due` rotation), under one
 * core (`CPUQuota=100%`, the measured ceiling of the verb) at the same low priority as a snapshot. It reads local
 * files only and holds no credential.
 */
export function generateVerifyServiceUnit(
  unitName: string,
  strategy: BackupStrategyConfig,
  datastore: string,
  remoteRenetPath: string,
  scope: UnitScope
): string {
  const key = verifyUnitName(unitName);
  return `[Unit]
Description=Rediacc Backup Verify (${unitName})
After=network-online.target
OnFailure=${alertUnitFileName(key)}

[Service]
Type=oneshot
${LOW_PRIORITY_DIRECTIVES}
CPUQuota=100%
TimeoutStartSec=infinity
TimeoutStopSec=90
ExecStart=${fullVerifyCommand(remoteRenetPath, datastore, scope, strategy)}

[Install]
WantedBy=multi-user.target
`;
}

/** The daily timer of the verify service. */
export function generateVerifyTimerUnit(unitName: string, strategy: BackupStrategyConfig): string {
  return generateTimerUnit(
    verifyUnitName(unitName),
    verifyOnCalendar(unitName, verifySettings(strategy), cronToOnCalendar)
  );
}

/**
 * What OnFailure= starts: `renet backup report` for the failed unit's scope. A crash is the case it covers, since the
 * verbs report their own failures. The reason is fixed text naming the unit; nothing from the config, no environment
 * file and no credential reaches it. It has no [Install] section and no timer: only OnFailure= starts it.
 */
export function generateAlertServiceUnit(
  failedUnitName: string,
  datastore: string,
  remoteRenetPath: string,
  scope: UnitScope,
  kind: 'snapshot' | 'verify',
  accountServer?: string
): string {
  const failedFile = `rediacc-backup-${failedUnitName}.service`;
  // `backup report` mints a session from the licence too, so it is held to the same account server as the snapshot.
  const report = [
    failureReportCommand(remoteRenetPath, datastore, scope, failedFile, kind),
    ...accountServerFlags(accountServer),
  ].join(' ');
  return `[Unit]
Description=Rediacc Backup Failure Report (${failedUnitName})

[Service]
Type=oneshot
${LOW_PRIORITY_DIRECTIVES}
ExecStart=${report}
`;
}
