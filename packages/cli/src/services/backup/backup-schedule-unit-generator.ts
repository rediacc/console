/**
 * Pure unit-content generators for scheduled backups.
 *
 * Everything in this module is deterministic: given the same inputs it
 * produces byte-identical output. That determinism is a contract the
 * reconciler depends on — SHA-256 hashes of the rendered content drive
 * the unchanged/updated classification, so any hidden nondeterminism
 * (timestamps, iteration order) would reclassify every deploy as "updated"
 * and defeat idempotency.
 */

import { createHash } from 'node:crypto';
import { BACKUP_DEFAULTS } from '@rediacc/shared/config';
import { isSensitiveKey } from '@rediacc/shared/telemetry';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../types/index.js';
import { envFilePath } from './backup-env-file.js';

/** SHA-256 hex digest for UTF-8 content — used by the reconciler for diff. */
export function sha256Hex(content: string): string {
  return createHash('sha256').update(content, 'utf8').digest('hex');
}

/** Convert a 5-field cron expression to systemd OnCalendar format. */
export function cronToOnCalendar(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) {
    throw new Error(`Invalid cron expression: "${cron}" (expected 5 fields)`);
  }

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

// systemd's OnCalendar syntax uses `..` for ranges (cron uses `-`) and
// comma-separated lists. Support list-of-ranges like cron's "0-2,4-23".
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
 * Redact sensitive values in rendered commands — covers legacy argv form
 * (`--rclone-param key=value`) and the `systemd-run --setenv=KEY=value`
 * form used by on-demand backups. Safe to print in dry-run, debug, and
 * agent contexts.
 */
export function sanitizeBackupOutput(content: string): string {
  let out = content.replaceAll(
    /--rclone-param '([^=]+)=([^']*)'/g,
    (_match, key: string, _value: string) => {
      return isSensitiveKey(key) ? `--rclone-param '${key}=[REDACTED]'` : _match;
    }
  );
  const rcloneKey = (envName: string): string =>
    envName.startsWith('RCLONE_') ? envName.slice('RCLONE_'.length).toLowerCase() : envName;
  out = out.replaceAll(
    /--setenv=([A-Z0-9_]+)=(?:'([^']*)'|(\S+))/g,
    (_m, key: string, quoted: string | undefined, _bare: string | undefined) => {
      if (!isSensitiveKey(rcloneKey(key))) return _m;
      return quoted === undefined ? `--setenv=${key}=[REDACTED]` : `--setenv=${key}='[REDACTED]'`;
    }
  );
  return out;
}

interface BackupBuild {
  commands: string[];
  envVars: Record<string, string>;
}

/**
 * Why a destination cannot be scheduled, or undefined when it can.
 *
 * Also exported for `backup strategy set`, which warns with it at creation
 * time rather than letting the operator discover at deploy time that the
 * destination they just made can never run.
 *
 * `kind` is OPTIONAL on the parameter on purpose: a destination that came from
 * the config loader has been through the schema and always carries one, but a
 * hand-edited entry (and the operator's live config) has no `kind` field at
 * all, and this must name it correctly rather than print "undefined".
 */
export function unschedulableDestinationReason(dest: {
  name: string;
  kind?: string;
}): string | undefined {
  const kind = dest.kind ?? BACKUP_DEFAULTS.DESTINATION_KIND;
  if (kind === BACKUP_DEFAULTS.NEW_DESTINATION_KIND) return undefined;
  return (
    `Backup destination "${dest.name}" has kind "${kind}". The ` +
    'rclone/OneDrive path was removed on 2026-08-15; change it to a ' +
    '`hosted-service` destination so the schedule uses the chunk store.'
  );
}

/**
 * The scheduled command for a chunk-store (hosted-service) destination.
 *
 * Carries NO credentials, which is the whole point of the destination kind:
 * the machine authenticates with its signed repo licence blob and the server
 * hands back a short-lived grant, so nothing sensitive reaches the unit file
 * or its EnvironmentFile.
 *
 * `strategy.exclude` is REFUSED rather than dropped. `backup snapshot` filters
 * by repeated --repo and has no exclude flag, so honouring an exclude list
 * would mean silently backing up repositories the operator asked to leave out
 * — the same silent-wrong-scope failure this branch exists to fix.
 */
function buildChunkStoreCommand(
  strategy: BackupStrategyConfig,
  datastore: string,
  remoteRenetPath: string
): string {
  if (strategy.exclude?.length) {
    throw new Error(
      'This backup strategy sets exclude, which a hosted-service destination ' +
        'cannot express: `backup snapshot` selects ' +
        'repositories with --repo and has no exclude flag. List the repositories ' +
        'to back up with include instead, so the scheduled scope is explicit.'
    );
  }
  const parts = [`${remoteRenetPath} backup snapshot`, `--datastore ${datastore}`];
  // `mode: cold` was REFUSED here until 2026-08-15, because `backup snapshot`
  // had no way to express it and scheduling one would have run a HOT snapshot
  // where the operator asked for cold — their stated intent silently inverted.
  // The verb now has --cold, so the mode is emitted instead of rejected.
  //
  // ORDERING HAZARD, and it bites inside a timer at 03:00: renet must be
  // deployed to a machine BEFORE a unit carrying --cold is written to it. An
  // older renet dies at cobra's flag parse, and the failure surfaces as a
  // backup that silently never ran. `backup schedule` seeds the binary first,
  // which is what keeps this in the right order.
  if ((strategy.mode ?? BACKUP_DEFAULTS.MODE) === 'cold') parts.push('--cold');
  for (const repo of strategy.include ?? []) parts.push(`--repo ${repo}`);
  const bwlimit = bandwidthToBytesPerSecond(strategy.bandwidthLimit);
  if (bwlimit !== undefined) parts.push(`--bwlimit ${bwlimit}`);
  return parts.join(' ');
}

/**
 * `bandwidthLimit` is an RCLONE-STYLE STRING ('6M'), because that is what the
 * old rclone path took and what the schema still declares
 * (config-schema/schemas.ts:434,505). `renet backup snapshot --bwlimit` is an
 * Int64 in BYTES PER SECOND (cmd/renet/backup_snapshot.go:132), so passing the
 * string through unchanged emits `--bwlimit 6M`, which dies at cobra's flag
 * parse — at RUN time, inside a systemd timer, not at deploy time.
 *
 * Measured on the operator's live config 2026-08-15: both strategies carry
 * '6M', so every unit generated for them would have failed this way.
 *
 * Suffixes follow rclone's convention (binary: 6M = 6 MiB/s). A value that
 * cannot be parsed is REFUSED rather than dropped or passed through: dropping
 * it silently lifts a cap the operator set deliberately.
 */
function bandwidthToBytesPerSecond(limit: string | undefined): number | undefined {
  if (!limit) return undefined;
  const m = /^(\d+(?:\.\d+)?)\s*([KMGTkmgt])?i?[Bb]?$/.exec(limit.trim());
  if (!m) {
    throw new Error(
      `Backup strategy bandwidthLimit "${limit}" is not a size this can convert. ` +
        'Use a plain number of bytes/second, or a suffixed value such as "6M". ' +
        'Refusing rather than dropping it, because dropping would silently remove ' +
        'a cap you set.'
    );
  }
  const scale: Record<string, number> = { k: 1024, m: 1024 ** 2, g: 1024 ** 3, t: 1024 ** 4 };
  // .at(2) rather than m[2]: the group is OPTIONAL, and this repo does not set
  // noUncheckedIndexedAccess, so m[2] is typed as always-present and lint calls
  // the guard redundant. .at() returns string | undefined, which is the truth.
  const unit = m.at(2)?.toLowerCase() ?? '';
  return Math.round(Number(m[1]) * (unit ? scale[unit] : 1));
}

/** One command per destination + merged RCLONE_* env-vars for the whole unit. */
export function buildBackupCommands(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[],
  datastore: string,
  remoteRenetPath: string
): BackupBuild {
  const commands: string[] = [];
  const envVars: Record<string, string> = {};

  for (const dest of destinations) {
    // A HARD ERROR, not a skip. Emitting nothing is exactly the defect the
    // hosted-service branch was written to fix: an operator declared a
    // destination, deployed the schedule, and got a timer that backed up
    // nothing with no error anywhere. If this path is reached, the strategy
    // still names an rclone/storage destination and must be migrated.
    const reason = unschedulableDestinationReason(dest);
    if (reason) {
      throw new Error(`${reason} Refusing to generate a unit that would back up nothing.`);
    }
    // The CHUNK STORE is now the only destination kind. The rclone/OneDrive
    // emission was removed 2026-08-15 on an explicit operator decision.
    commands.push(buildChunkStoreCommand(strategy, datastore, remoteRenetPath));
  }
  return { commands, envVars };
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

interface ServiceUnitBuild {
  /** Full systemd .service file content. */
  serviceContent: string;
  /** RCLONE_* env vars to write to a 0600 EnvironmentFile= sidecar. */
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
  remoteRenetPath: string
): ServiceUnitBuild {
  const { commands, envVars } = buildBackupCommands(
    strategy,
    destinations,
    datastore,
    remoteRenetPath
  );
  const execLines = commands.map((cmd) => `ExecStart=${cmd}`);
  const envFileLine =
    Object.keys(envVars).length > 0 ? `EnvironmentFile=${envFilePath(strategyName)}\n` : '';
  const renewLine = `ExecStartPre=${licenseRenewCommand(remoteRenetPath)}\n`;

  // TimeoutStartSec=infinity: backups can legitimately take > 24 h for a
  // first full seed of a large repo. Any finite cap eventually bites.
  //
  // TimeoutStopSec is what systemd allows renet AFTER a SIGTERM before it
  // SIGKILLs, and the two modes need very different budgets:
  //
  //   hot  (90s): renet aborts the transfer and deletes its datastore snapshot,
  //     bounded at 60s renet-side. Without a window systemd would SIGKILL
  //     mid-cleanup and orphan the snapshot.
  //   cold (960s): a SIGTERM inside the outage window leaves containers STOPPED,
  //     and renet's handler must bring every one of them back before it exits.
  //     That restart is bounded at 15 min renet-side (coldRestartTimeout), so a
  //     90s window would SIGKILL mid-restart and leave the repositories down —
  //     converting a clean shutdown into the exact outage cold mode exists to
  //     keep brief. The budget is the renet bound plus a minute of slack.
  //
  // Reconcile repairs a machine left in that state within a tick, but a backstop
  // measured in minutes is not a reason to hand systemd a knife.
  const stopTimeout = (strategy.mode ?? BACKUP_DEFAULTS.MODE) === 'cold' ? 960 : 90;
  const serviceContent = `[Unit]
Description=Rediacc Scheduled Backup (${strategyName})
After=network-online.target

[Service]
Type=oneshot
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
