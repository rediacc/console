/**
 * Backup Schedule Service
 *
 * Pushes backup schedule configuration to remote machines via SSH.
 * Generates systemd service + timer units that run `renet backup sync`
 * on a schedule defined in the context's backup config.
 */

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { buildRcloneArgs } from '@rediacc/shared/queue-vault';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { contextService } from './context.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

interface PushScheduleOptions {
  debug?: boolean;
}

/**
 * Convert a 5-field cron expression to systemd OnCalendar format.
 *
 * Handles common cases:
 *   "0 2 * * *"   → "*-*-* 02:00:00"      (daily at 2 AM)
 *   "0 * /6 * * *" → "*-*-* 00/6:00:00"    (every 6 hours)
 *   "0 2 * * 0"   → "Sun *-*-* 02:00:00"   (weekly Sunday 2 AM)
 *   "30 3 1 * *"  → "*-*-01 03:30:00"      (1st of month at 3:30)
 */
export function cronToOnCalendar(cron: string): string {
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
    dowPrefix = days.join(',') + ' ';
  }

  return `${dowPrefix}${datePart} ${timePart}`;
}

/**
 * Generate systemd service unit content for renet backup sync.
 */
function generateServiceUnit(
  rcloneRemote: string,
  rcloneParams: string[],
  datastore: string
): string {
  // Parse backend from remote string ":backend:path"
  const backendMatch = rcloneRemote.match(/^:([^:]+):(.*)/);
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
    '/usr/bin/renet backup sync push',
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
Description=Rediacc Scheduled Backup
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
function generateTimerUnit(onCalendar: string): string {
  return `[Unit]
Description=Rediacc Backup Timer

[Timer]
OnCalendar=${onCalendar}
Persistent=true

[Install]
WantedBy=timers.target
`;
}

/**
 * Push backup schedule to a remote machine as systemd service + timer.
 *
 * Flow:
 * 1. Load backup config + storage vaultContent from context
 * 2. Convert storage credentials to rclone args
 * 3. Provision renet binary to remote
 * 4. SSH: write systemd service + timer units
 * 5. SSH: daemon-reload + enable + start timer
 */
export async function pushBackupSchedule(
  machineName: string,
  options: PushScheduleOptions = {}
): Promise<void> {
  // Load backup config
  const backupConfig = await contextService.getBackupConfig();
  if (!backupConfig?.defaultDestination) {
    throw new Error(
      'No backup configuration found. Set it with: rdc backup schedule set --destination <storage>'
    );
  }
  if (!backupConfig.schedule) {
    throw new Error(
      'No backup schedule set. Set it with: rdc backup schedule set --cron "0 2 * * *"'
    );
  }

  // Load storage config
  const storage = await contextService.getLocalStorage(backupConfig.defaultDestination);

  // Load machine config
  const localConfig = await contextService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Convert vault to rclone args
  const { remote, params: rcloneParams } = buildRcloneArgs(storage.vaultContent);

  // Convert cron to OnCalendar
  const onCalendar = cronToOnCalendar(backupConfig.schedule);

  if (options.debug) {
    outputService.info(`Storage: ${backupConfig.defaultDestination}`);
    outputService.info(`Schedule: ${backupConfig.schedule} → OnCalendar=${onCalendar}`);
    outputService.info(`Rclone remote: ${remote}`);
  }

  // Provision renet binary to remote
  outputService.info(`Provisioning renet to ${machine.ip}...`);
  await provisionRenetToRemote({ renetPath: localConfig.renetPath }, machine, sshPrivateKey, {
    debug: options.debug,
  });

  // Generate systemd units
  const serviceContent = generateServiceUnit(remote, rcloneParams, datastore);
  const timerContent = generateTimerUnit(onCalendar);

  if (options.debug) {
    outputService.info('--- rediacc-backup.service ---');
    outputService.info(serviceContent);
    outputService.info('--- rediacc-backup.timer ---');
    outputService.info(timerContent);
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
    // Write service unit
    const serviceCmd = `sudo tee /etc/systemd/system/rediacc-backup.service > /dev/null`;
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
      throw new Error(`Failed to write service unit (exit ${exitCode})`);
    }

    // Write timer unit
    const timerCmd = `sudo tee /etc/systemd/system/rediacc-backup.timer > /dev/null`;
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
      throw new Error(`Failed to write timer unit (exit ${exitCode})`);
    }

    // Reload systemd and enable timer
    const enableCmd =
      'sudo systemctl daemon-reload && sudo systemctl enable --now rediacc-backup.timer';
    exitCode = await sftp.execStreaming(enableCmd, {
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => {
        process.stderr.write(data);
      },
    });
    if (exitCode !== 0) {
      throw new Error(`Failed to enable timer (exit ${exitCode})`);
    }
  } finally {
    sftp.close();
  }
}
