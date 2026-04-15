/**
 * Backup Schedule Service
 *
 * Pushes backup schedule configuration to remote machines via SSH.
 * Generates per-strategy systemd service + timer units that run `renet backup sync push`.
 *
 * Architecture:
 * - One systemd timer per strategy (not per destination)
 * - A strategy may have multiple destinations (upload to all from the same snapshot)
 * - Cold mode: stop services, snapshot, restart, then upload
 * - Hot mode: snapshot while running (default)
 */

import { BACKUP_DEFAULTS, DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { buildRcloneArgs } from '@rediacc/shared/queue-vault';
import { isSensitiveKey } from '@rediacc/shared/telemetry';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../types/index.js';
import {
  envFilePath,
  generateEnvFile,
  mergeEnvVars,
  rcloneEnvName,
  writeEnvFile,
} from './backup-env-file.js';
import { configService } from './config-resources.js';
import { refreshRepoLicensesBatch } from './license.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';
import { REMOTE_RENET_PATH } from './renet-provisioner.js';

interface PushScheduleOptions {
  debug?: boolean;
  dryRun?: boolean;
}

const SYSTEMD_BACKUP_UNIT_GLOB = 'rediacc-backup*';

/**
 * Convert a 5-field cron expression to systemd OnCalendar format.
 */
function cronToOnCalendar(cron: string): string {
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

  function toTimerField(value: string): string {
    if (value === '*') return '*';
    if (value.startsWith('*/')) return `00/${value.slice(2)}`;
    return value.padStart(2, '0');
  }
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

/**
 * Sanitize a systemd unit or shell command by redacting sensitive values.
 * Covers both legacy `--rclone-param key=value` argv form AND the hardened
 * `--setenv=RCLONE_KEY=value` form used by `systemd-run` for ad-hoc backups.
 * Keys matched against SENSITIVE_KEYS (token, secret, key, password, etc.)
 * are replaced with [REDACTED]. Safe for dry-run output, debug logging,
 * and agent context.
 */
function sanitizeBackupOutput(content: string): string {
  let out = content.replaceAll(
    /--rclone-param '([^=]+)=([^']*)'/g,
    (_match, key: string, _value: string) => {
      if (isSensitiveKey(key)) {
        return `--rclone-param '${key}=[REDACTED]'`;
      }
      return _match;
    }
  );
  // systemd-run --setenv=RCLONE_<KEY>='<value>' (quoted) and --setenv=KEY=value (bare).
  // Check the rclone-stripped key against the sensitivity list so RCLONE_ONEDRIVE_TOKEN
  // is redacted but RCLONE_BWLIMIT is not. Preserve the original quoting.
  const rcloneKey = (envName: string): string =>
    envName.startsWith('RCLONE_') ? envName.slice('RCLONE_'.length).toLowerCase() : envName;
  out = out.replaceAll(
    /--setenv=([A-Z0-9_]+)=(?:'([^']*)'|(\S+))/g,
    (_m, key: string, quoted: string | undefined, bare: string | undefined) => {
      if (!isSensitiveKey(rcloneKey(key))) return _m;
      return quoted !== undefined ? `--setenv=${key}='[REDACTED]'` : `--setenv=${key}=[REDACTED]`;
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
function buildDestinationCommand(
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
    const key = stripped.slice(0, eq);
    const value = stripped.slice(eq + 1);
    envVars[rcloneEnvName(key)] = value;
  }

  // bwlimit is per-destination and non-sensitive, so it stays on argv.
  // Putting it in shared envVars would collide in mergeEnvVars when two
  // destinations in the same strategy set different rates — a legitimate
  // config that backup-schedule must support.
  const bwlimit = dest.bandwidthLimit ?? strategy.bandwidthLimit;
  if (bwlimit) {
    parts.push(`--rclone-param bwlimit=${bwlimit}`);
  }

  if (strategy.include?.length) {
    parts.push(`--include-repo ${strategy.include.join(',')}`);
  }
  if (strategy.exclude?.length) {
    parts.push(`--exclude-repo ${strategy.exclude.join(',')}`);
  }

  return { command: parts.join(' '), envVars };
}

interface BackupBuild {
  commands: string[];
  envVars: Record<string, string>;
}

/** One command per destination + merged RCLONE_* env-vars for the whole unit. */
function buildBackupCommands(
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
function generateServiceUnit(
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
  // first full seed of a large repo. Any finite cap eventually bites. Rely
  // on operators / external monitoring to spot a truly hung rclone, since
  // systemd won't kill it automatically here.
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

/**
 * Generate systemd timer unit for a backup strategy.
 */
function generateTimerUnit(strategyName: string, onCalendar: string): string {
  return `[Unit]
Description=Rediacc Backup Timer (${strategyName})

[Timer]
OnCalendar=${onCalendar}
Persistent=true

[Install]
WantedBy=timers.target
`;
}

async function runRemoteCommand(
  sftp: SFTPClient,
  command: string,
  options: PushScheduleOptions,
  errorMessage: string
): Promise<void> {
  const exitCode = await sftp.execStreaming(command, {
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });

  if (exitCode !== 0) {
    throw new Error(`${errorMessage} (exit ${exitCode})`);
  }
}

async function cleanupExistingBackupUnits(
  sftp: SFTPClient,
  options: PushScheduleOptions
): Promise<void> {
  const cleanupCmd = [
    'sudo rm -f',
    `/etc/systemd/system/${SYSTEMD_BACKUP_UNIT_GLOB}.service`,
    `/etc/systemd/system/${SYSTEMD_BACKUP_UNIT_GLOB}.timer`,
    `/etc/systemd/system/timers.target.wants/${SYSTEMD_BACKUP_UNIT_GLOB}.timer`,
    '/etc/rediacc/backup-*.env',
  ].join(' ');

  await runRemoteCommand(sftp, cleanupCmd, options, 'Failed to remove existing backup units');
  await runRemoteCommand(
    sftp,
    'sudo systemctl daemon-reload',
    options,
    'Failed to reload systemd daemon after cleanup'
  );
  await runRemoteCommand(
    sftp,
    'sudo systemctl reset-failed',
    options,
    'Failed to reset systemd failed state after cleanup'
  );
}

/** Deploy systemd units for a single strategy. */
async function deployStrategyUnits(
  sftp: SFTPClient,
  strategyName: string,
  strategy: BackupStrategyConfig,
  datastore: string,
  remoteRenetPath: string,
  options: PushScheduleOptions
): Promise<void> {
  const enabledDests = strategy.destinations.filter((d) => d.enabled !== false);
  if (enabledDests.length === 0) {
    outputService.warn(`Skipping strategy "${strategyName}": no enabled destinations`);
    return;
  }

  // Resolve rclone args for each destination
  const rcloneArgsByDest = new Map<string, { remote: string; params: string[] }>();
  for (const dest of enabledDests) {
    const storageCfg = await configService.getStorage(dest.storage);
    const args = buildRcloneArgs(storageCfg.vaultContent);
    rcloneArgsByDest.set(dest.name, args);
  }

  const onCalendar = cronToOnCalendar(strategy.schedule);
  const unitName = `rediacc-backup-${strategyName}`;

  if (options.debug) {
    outputService.info(`Strategy: ${strategyName}`);
    outputService.info(`Schedule: ${strategy.schedule} -> OnCalendar=${onCalendar}`);
    outputService.info(`Mode: ${strategy.mode ?? BACKUP_DEFAULTS.MODE}`);
    outputService.info(`Destinations: ${enabledDests.map((d) => d.name).join(', ')}`);
  }

  const { serviceContent, envVars } = generateServiceUnit(
    strategyName,
    strategy,
    enabledDests,
    rcloneArgsByDest,
    datastore,
    remoteRenetPath
  );
  const timerContent = generateTimerUnit(strategyName, onCalendar);
  const envFileContent = generateEnvFile(envVars);

  if (options.debug) {
    process.stderr.write(`--- ${unitName}.service ---\n${sanitizeBackupOutput(serviceContent)}\n`);
    if (envFileContent) {
      process.stderr.write(
        `--- ${envFilePath(strategyName)} ---\n<0600 env-file; values redacted>\n`
      );
    }
    process.stderr.write(`--- ${unitName}.timer ---\n${timerContent}\n`);
  }

  // Credentials env-file must land before the .service file so the unit is
  // never on-disk referencing a missing EnvironmentFile=.
  if (envFileContent) {
    await writeEnvFile(sftp, strategyName, envFileContent, options);
  }

  // Write service unit
  let exitCode = await sftp.execStreaming(
    `sudo tee /etc/systemd/system/${unitName}.service > /dev/null`,
    {
      stdin: serviceContent,
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => {
        process.stderr.write(data);
      },
    }
  );
  if (exitCode !== 0) {
    throw new Error(
      `Failed to write service unit for strategy "${strategyName}" (exit ${exitCode})`
    );
  }

  // Write timer unit
  exitCode = await sftp.execStreaming(
    `sudo tee /etc/systemd/system/${unitName}.timer > /dev/null`,
    {
      stdin: timerContent,
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => {
        process.stderr.write(data);
      },
    }
  );
  if (exitCode !== 0) {
    throw new Error(`Failed to write timer unit for strategy "${strategyName}" (exit ${exitCode})`);
  }

  // Enable timer
  exitCode = await sftp.execStreaming(`sudo systemctl enable --now ${unitName}.timer`, {
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });
  if (exitCode !== 0) {
    throw new Error(`Failed to enable timer for strategy "${strategyName}" (exit ${exitCode})`);
  }

  outputService.info(`Deployed ${unitName}.timer (${onCalendar})`);
}

/** Validate no duplicate destination names across strategies. */
function assertNoDuplicateDestinations(strategies: { config: BackupStrategyConfig }[]): void {
  const destNames = new Set<string>();
  for (const { config } of strategies) {
    for (const dest of config.destinations) {
      if (destNames.has(dest.name)) {
        throw new Error(
          `Duplicate destination name "${dest.name}" across strategies. Each destination name must be unique.`
        );
      }
      destNames.add(dest.name);
    }
  }
}

/** Load enabled strategies from config and validate them. */
async function loadAndValidateStrategies(
  strategyNames: string[]
): Promise<{ name: string; config: BackupStrategyConfig }[]> {
  const strategies: { name: string; config: BackupStrategyConfig }[] = [];
  for (const stratName of strategyNames) {
    const config = await configService.getBackupStrategy(stratName);
    if (!config) {
      throw new Error(`Backup strategy "${stratName}" not found in config`);
    }
    if (config.enabled === false) continue;
    strategies.push({ name: stratName, config });
  }

  if (strategies.length === 0) {
    throw new Error('All bound backup strategies are disabled');
  }

  assertNoDuplicateDestinations(strategies);
  return strategies;
}

/** Preview generated systemd units without deploying. */
async function previewDryRun(
  strategies: { name: string; config: BackupStrategyConfig }[],
  datastore: string,
  machineName: string
): Promise<void> {
  outputService.info(
    `Dry-run: would deploy ${strategies.length} strategy timer(s) to ${machineName}`
  );
  for (const { name, config } of strategies) {
    const enabledDests = config.destinations.filter((d) => d.enabled !== false);
    const rcloneArgsByDest = new Map<string, { remote: string; params: string[] }>();
    for (const dest of enabledDests) {
      const storageCfg = await configService.getStorage(dest.storage);
      const args = buildRcloneArgs(storageCfg.vaultContent);
      rcloneArgsByDest.set(dest.name, args);
    }
    const onCalendar = cronToOnCalendar(config.schedule);
    const { serviceContent, envVars } = generateServiceUnit(
      name,
      config,
      enabledDests,
      rcloneArgsByDest,
      datastore,
      REMOTE_RENET_PATH
    );
    const timerContent = generateTimerUnit(name, onCalendar);
    outputService.info(`\n--- rediacc-backup-${name}.service ---`);
    outputService.info(sanitizeBackupOutput(serviceContent));
    if (Object.keys(envVars).length > 0) {
      outputService.info(`--- ${envFilePath(name)} (mode 0600, values redacted) ---`);
      outputService.info(
        Object.keys(envVars)
          .sort()
          .map((k) => `${k}=[REDACTED]`)
          .join('\n')
      );
    }
    outputService.info(`--- rediacc-backup-${name}.timer ---`);
    outputService.info(timerContent);
  }
}

/**
 * Push backup schedule to a remote machine.
 *
 * Reads machine.backupStrategies[] to determine which strategies to deploy.
 * Each strategy becomes one systemd service + timer pair.
 */
export async function pushBackupSchedule(
  machineName: string,
  options: PushScheduleOptions = {}
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const strategyNames = machine.backupStrategies ?? [];
  if (strategyNames.length === 0) {
    throw new Error(
      `No backup strategies bound to machine "${machineName}". Bind with: rdc config machine set --name ${machineName} --backup-strategy <name>`
    );
  }

  const strategies = await loadAndValidateStrategies(strategyNames);
  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;

  if (options.dryRun) {
    await previewDryRun(strategies, datastore, machineName);
    return;
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet binary to remote
  outputService.info(`Provisioning renet to ${machine.ip}...`);
  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug: options.debug }
  );

  const repoRefresh = await refreshRepoLicensesBatch(machine, sshPrivateKey, remoteRenetPath);
  if (repoRefresh.scanned > 0 && repoRefresh.valid === 0) {
    throw new Error(
      'Backup deployment aborted: no valid repo licenses are available on target machine'
    );
  }
  if (repoRefresh.scanned > 0) {
    outputService.info(
      `Repo licenses refreshed: scanned ${repoRefresh.scanned}, issued ${repoRefresh.issued}, refreshed ${repoRefresh.refreshed}, unchanged ${repoRefresh.unchanged}, failed ${repoRefresh.failed}`
    );
  }

  // Connect via SSH
  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    await cleanupExistingBackupUnits(sftp, options);

    for (const { name, config } of strategies) {
      await deployStrategyUnits(sftp, name, config, datastore, remoteRenetPath, options);
    }

    await runRemoteCommand(
      sftp,
      'sudo systemctl daemon-reload',
      options,
      'Failed to reload systemd daemon after deploy'
    );
  } finally {
    sftp.close();
  }

  outputService.info(`Backup schedule deployed to ${machineName}`);
}

/** @internal Exported for unit tests and ad-hoc backup execution. */
export const _testing = {
  generateServiceUnit,
  cronToOnCalendar,
  buildBackupCommands,
  buildDestinationCommand,
  generateEnvFile,
  envFilePath,
};
export { sanitizeBackupOutput };
