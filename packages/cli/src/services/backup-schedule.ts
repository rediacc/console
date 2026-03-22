/**
 * Backup Schedule Service
 *
 * Pushes backup schedule configuration to remote machines via SSH.
 * Generates per-destination systemd service + timer units that run `renet backup sync`
 * on a schedule defined in the config's backup strategy.
 */

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { buildRcloneArgs } from '@rediacc/shared/queue-vault';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { BackupStrategyDestination } from '../types/index.js';
import { configService } from './config-resources.js';
import { refreshRepoLicensesBatch } from './license.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

interface PushScheduleOptions {
  debug?: boolean;
}

const SYSTEMD_BACKUP_UNIT_GLOB = 'rediacc-backup*';

/**
 * Convert a 5-field cron expression to systemd OnCalendar format.
 *
 * Handles common cases:
 *   "0 2 * * *"   → "*-*-* 02:00:00"      (daily at 2 AM)
 *   "0 * /6 * * *" → "*-*-* 00/6:00:00"    (every 6 hours)
 *   "0 2 * * 0"   → "Sun *-*-* 02:00:00"   (weekly Sunday 2 AM)
 *   "30 3 1 * *"  → "*-*-01 03:30:00"      (1st of month at 3:30)
 */
function cronToOnCalendar(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) {
    throw new Error(`Invalid cron expression: "${cron}" (expected 5 fields)`);
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;

  // Day of week mapping
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

  // Build date part
  const monthPart = month === '*' ? '*' : month.padStart(2, '0');
  const dayPart = dayOfMonth === '*' ? '*' : dayOfMonth.padStart(2, '0');
  const datePart = `*-${monthPart}-${dayPart}`;

  // Build time part — handle */N intervals
  const hourStr = hour.startsWith('*/') ? `00/${hour.slice(2)}` : hour.padStart(2, '0');
  const minStr = minute.startsWith('*/') ? `00/${minute.slice(2)}` : minute.padStart(2, '0');
  const timePart = `${hourStr}:${minStr}:00`;

  // Build day-of-week prefix
  let dowPrefix = '';
  if (dayOfWeek !== '*') {
    const days = dayOfWeek.split(',').map((d) => dowMap[d] ?? d);
    dowPrefix = `${days.join(',')} `;
  }

  return `${dowPrefix}${datePart} ${timePart}`;
}

/**
 * Generate systemd service unit content for renet backup sync.
 */
function generateServiceUnit(
  destinationName: string,
  rcloneRemote: string,
  rcloneParams: string[],
  datastore: string,
  remoteRenetPath: string
): string {
  // Parse backend from remote string ":backend:path"
  const backendMatch = /^:([^:]+):(.*)/.exec(rcloneRemote);
  if (!backendMatch) {
    throw new Error(`Invalid rclone remote format: ${rcloneRemote}`);
  }
  const [, backend, remotePath] = backendMatch;

  // Split remote path into bucket/folder
  const pathParts = remotePath.split('/');
  const bucket = pathParts[0] ?? '';
  const folder = pathParts.slice(1).join('/');

  // Build ExecStart command
  const execParts = [
    `${remoteRenetPath} backup sync push`,
    `--datastore ${datastore}`,
    `--rclone-backend ${backend}`,
  ];

  if (bucket) {
    execParts.push(`--rclone-bucket ${bucket}`);
  }
  if (folder) {
    execParts.push(`--rclone-folder ${folder}`);
  }

  // Convert --backend-key=value to --rclone-param backend-key=value
  for (const param of rcloneParams) {
    // param is like "--s3-access-key-id=AKIA..."
    const stripped = param.replace(/^--/, '');
    execParts.push(`--rclone-param '${stripped}'`);
  }

  return `[Unit]
Description=Rediacc Scheduled Backup (${destinationName})
After=network-online.target

[Service]
Type=oneshot
ExecStart=${execParts.join(' \\\n    ')}

[Install]
WantedBy=multi-user.target
`;
}

/**
 * Generate systemd timer unit content.
 */
function generateTimerUnit(destinationName: string, onCalendar: string): string {
  return `[Unit]
Description=Rediacc Backup Timer (${destinationName})

[Timer]
OnCalendar=${onCalendar}
Persistent=true

[Install]
WantedBy=timers.target
`;
}

/** Deploy a single destination's systemd units to a remote machine via SFTP. */
async function deployDestinationUnits(
  sftp: SFTPClient,
  dest: BackupStrategyDestination,
  globalSchedule: string | undefined,
  datastore: string,
  remoteRenetPath: string,
  options: PushScheduleOptions
): Promise<void> {
  const storageCfg = await configService.getStorage(dest.storage);
  const { remote, params: rcloneParams } = buildRcloneArgs(storageCfg.vaultContent);
  const effectiveSchedule = dest.schedule ?? globalSchedule;

  if (!effectiveSchedule) {
    outputService.warn(
      `Skipping destination "${dest.storage}": no schedule (set per-destination or global cron)`
    );
    return;
  }

  const onCalendar = cronToOnCalendar(effectiveSchedule);
  const unitName = `rediacc-backup-${dest.storage}`;

  if (options.debug) {
    outputService.info(`Destination: ${dest.storage}`);
    outputService.info(`Schedule: ${effectiveSchedule} → OnCalendar=${onCalendar}`);
    outputService.info(`Rclone remote: ${remote}`);
  }

  const serviceContent = generateServiceUnit(
    dest.storage,
    remote,
    rcloneParams,
    datastore,
    remoteRenetPath
  );
  const timerContent = generateTimerUnit(dest.storage, onCalendar);

  if (options.debug) {
    process.stderr.write(`--- ${unitName}.service ---\n${serviceContent}\n`);
    process.stderr.write(`--- ${unitName}.timer ---\n${timerContent}\n`);
  }

  // Write service unit
  const serviceCmd = `sudo tee /etc/systemd/system/${unitName}.service > /dev/null`;
  let exitCode = await sftp.execStreaming(serviceCmd, {
    stdin: serviceContent,
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });
  if (exitCode !== 0) {
    throw new Error(`Failed to write service unit for "${dest.storage}" (exit ${exitCode})`);
  }

  // Write timer unit
  const timerCmd = `sudo tee /etc/systemd/system/${unitName}.timer > /dev/null`;
  exitCode = await sftp.execStreaming(timerCmd, {
    stdin: timerContent,
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });
  if (exitCode !== 0) {
    throw new Error(`Failed to write timer unit for "${dest.storage}" (exit ${exitCode})`);
  }

  // Enable timer
  const enableCmd = `sudo systemctl enable --now ${unitName}.timer`;
  exitCode = await sftp.execStreaming(enableCmd, {
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });
  if (exitCode !== 0) {
    throw new Error(`Failed to enable timer for "${dest.storage}" (exit ${exitCode})`);
  }

  outputService.info(`Deployed ${unitName}.timer (${onCalendar})`);
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

/**
 * Push backup schedule to a remote machine as per-destination systemd service + timer units.
 *
 * Flow:
 * 1. Load backup strategy from config
 * 2. Filter to enabled destinations
 * 3. Provision renet binary to remote
 * 4. Delete all existing Rediacc backup units/symlinks on the machine
 * 5. For each destination: deploy service + timer units
 * 6. Daemon-reload after all units are written
 */
export async function pushBackupSchedule(
  machineName: string,
  options: PushScheduleOptions = {}
): Promise<void> {
  const strategy = await configService.getBackupStrategy();
  if (!strategy || strategy.destinations.length === 0) {
    throw new Error(
      'No backup destinations configured. Add one with: rdc config backup-strategy set --destination <storage> --cron "0 2 * * *"'
    );
  }

  // Filter to enabled destinations
  const enabledDests = strategy.destinations.filter(
    (d) => d.enabled !== false && strategy.enabled !== false
  );
  if (enabledDests.length === 0) {
    throw new Error(
      'All backup destinations are disabled. Enable one with: rdc config backup-strategy set --destination <storage> --enable'
    );
  }

  // Load machine config
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet binary to remote
  outputService.info(`Provisioning renet to ${machine.ip}...`);
  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    {
      debug: options.debug,
    }
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

    // Deploy units for each enabled destination
    for (const dest of enabledDests) {
      await deployDestinationUnits(
        sftp,
        dest,
        strategy.schedule,
        datastore,
        remoteRenetPath,
        options
      );
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
}
