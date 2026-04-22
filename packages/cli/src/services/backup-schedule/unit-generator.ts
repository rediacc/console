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
import { envFilePath, mergeEnvVars, rcloneEnvName } from '../backup-env-file.js';

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

interface DestinationBuild {
  command: string;
  envVars: Record<string, string>;
}

/**
 * Credential params move to `envVars` (so they can land in a 0600
 * EnvironmentFile=) rather than onto argv where the systemd unit file would
 * expose them to any local user.
 */
export function buildDestinationCommand(
  dest: BackupStrategyDestination,
  rcloneArgs: { remote: string; params: string[] },
  strategy: BackupStrategyConfig,
  mode: string,
  datastore: string,
  remoteRenetPath: string
): DestinationBuild | undefined {
  const backendMatch = /^:([^:]+):(.*)/.exec(rcloneArgs.remote);
  if (!backendMatch) return undefined;
  const [, backend, remotePath] = backendMatch;

  const pathParts = remotePath.split('/');
  const bucket = pathParts[0] ?? '';
  const folder = pathParts.slice(1).join('/');

  const parts = [
    `${remoteRenetPath} backup sync push`,
    `--datastore ${datastore}`,
    `--rclone-backend ${backend}`,
    `--mode ${mode}`,
  ];
  if (bucket) parts.push(`--rclone-bucket ${bucket}`);
  if (folder) parts.push(`--rclone-folder ${folder}`);

  const envVars: Record<string, string> = {};
  for (const param of rcloneArgs.params) {
    const stripped = param.replace(/^--/, '');
    const eq = stripped.indexOf('=');
    if (eq <= 0) continue;
    envVars[rcloneEnvName(stripped.slice(0, eq))] = stripped.slice(eq + 1);
  }

  // bwlimit is per-destination and non-sensitive, so it stays on argv.
  // Moving it to envVars would collide in mergeEnvVars when two
  // destinations in one strategy set different rates — a legitimate config.
  const bwlimit = dest.bandwidthLimit ?? strategy.bandwidthLimit;
  if (bwlimit) parts.push(`--rclone-param bwlimit=${bwlimit}`);
  if (strategy.include?.length) parts.push(`--include-repo ${strategy.include.join(',')}`);
  if (strategy.exclude?.length) parts.push(`--exclude-repo ${strategy.exclude.join(',')}`);

  return { command: parts.join(' '), envVars };
}

interface BackupBuild {
  commands: string[];
  envVars: Record<string, string>;
}

/** One command per destination + merged RCLONE_* env-vars for the whole unit. */
export function buildBackupCommands(
  strategy: BackupStrategyConfig,
  destinations: BackupStrategyDestination[],
  rcloneArgsByDest: Map<string, { remote: string; params: string[] }>,
  datastore: string,
  remoteRenetPath: string
): BackupBuild {
  const mode = strategy.mode ?? BACKUP_DEFAULTS.MODE;
  const commands: string[] = [];
  const envVars: Record<string, string> = {};

  for (const dest of destinations) {
    const rcloneArgs = rcloneArgsByDest.get(dest.name);
    if (!rcloneArgs) continue;
    const built = buildDestinationCommand(
      dest,
      rcloneArgs,
      strategy,
      mode,
      datastore,
      remoteRenetPath
    );
    if (!built) continue;
    commands.push(built.command);
    mergeEnvVars(envVars, built.envVars);
  }
  return { commands, envVars };
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
  rcloneArgsByDest: Map<string, { remote: string; params: string[] }>,
  datastore: string,
  remoteRenetPath: string
): ServiceUnitBuild {
  const { commands, envVars } = buildBackupCommands(
    strategy,
    destinations,
    rcloneArgsByDest,
    datastore,
    remoteRenetPath
  );
  const execLines = commands.map((cmd) => `ExecStart=${cmd}`);
  const envFileLine =
    Object.keys(envVars).length > 0 ? `EnvironmentFile=${envFilePath(strategyName)}\n` : '';

  // TimeoutStartSec=infinity: backups can legitimately take > 24 h for a
  // first full seed of a large repo. Any finite cap eventually bites.
  const serviceContent = `[Unit]
Description=Rediacc Scheduled Backup (${strategyName})
After=network-online.target

[Service]
Type=oneshot
TimeoutStartSec=infinity
${envFileLine}${execLines.join('\n')}

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
