/**
 * Backup Sync Service
 *
 * Executes bulk backup sync (push all / pull all) on remote machines via SSH.
 * Uses direct SSH execution (like backup-schedule.ts) rather than the vault system,
 * because sync operates on ALL repos at once — not a single repo through the queue.
 */

import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { buildRcloneArgs } from '@rediacc/shared/queue-vault';
import { configService } from './config-resources.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

interface SyncOptions {
  storageName: string;
  machine?: string;
  repos?: string[];
  override?: boolean;
  debug?: boolean;
}

/**
 * Convert storage vault content + rclone args into renet backup sync CLI flags.
 *
 * buildRcloneArgs() returns:
 *   remote: ":s3:bucket/folder"
 *   params: ["--s3-access-key-id=...", "--s3-endpoint=..."]
 *
 * We need to convert to:
 *   --rclone-backend s3
 *   --rclone-bucket bucket
 *   --rclone-folder folder
 *   --rclone-param s3-access-key-id=...
 */
function buildSyncRcloneFlags(vaultContent: Record<string, unknown>): string[] {
  const { remote, params } = buildRcloneArgs(vaultContent);

  // Parse ":backend:bucket/folder" from remote
  const match = /^:([^:]+):(.*)/.exec(remote);
  if (!match) {
    throw new Error(`Invalid rclone remote format: ${remote}`);
  }
  const [, backend, remotePath] = match;

  const pathParts = remotePath.split('/').filter(Boolean);
  const bucket = pathParts[0] ?? '';
  const folder = pathParts.slice(1).join('/');

  const flags: string[] = [`--rclone-backend`, backend];

  if (bucket) {
    flags.push(`--rclone-bucket`, bucket);
  }
  if (folder) {
    flags.push(`--rclone-folder`, folder);
  }

  // Convert --s3-key=value → --rclone-param s3-key=value
  for (const param of params) {
    const stripped = param.replace(/^--/, '');
    flags.push(`--rclone-param`, stripped);
  }

  return flags;
}

/**
 * Run backup sync push — upload all repos from a machine to storage.
 */
export async function runBackupSyncPush(options: SyncOptions): Promise<void> {
  const machineName = options.machine ?? (await configService.getMachine());
  if (!machineName) {
    throw new Error('No machine specified. Use -m <machine> or set a default machine.');
  }

  // Load configs
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const storage = await configService.getStorage(options.storageName);
  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Build rclone flags
  const rcloneFlags = buildSyncRcloneFlags(storage.vaultContent);

  if (options.debug) {
    outputService.info(`Storage: ${options.storageName}`);
    outputService.info(`Machine: ${machineName} (${machine.ip})`);
    outputService.info(`Rclone flags: ${rcloneFlags.join(' ')}`);
  }

  // Provision renet binary
  outputService.info(`Provisioning renet to ${machine.ip}...`);
  await provisionRenetToRemote({ renetPath: localConfig.renetPath }, machine, sshPrivateKey, {
    debug: options.debug,
  });

  // Build SSH command
  const cmdParts = [
    'sudo',
    '/usr/bin/renet',
    'backup',
    'sync',
    'push',
    '--datastore',
    datastore,
    ...rcloneFlags,
  ];

  // Add --repo filters
  if (options.repos && options.repos.length > 0) {
    for (const guid of options.repos) {
      cmdParts.push('--repo', guid);
    }
  }

  if (options.debug) {
    cmdParts.push('--debug');
  }

  const command = cmdParts.map((p) => (p.includes(' ') ? `'${p}'` : p)).join(' ');

  if (options.debug) {
    outputService.info(`[sync] Running: ${command}`);
  }

  // Execute via SSH
  outputService.info(`Pushing all repos from ${machineName} to ${options.storageName}...`);

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    const exitCode = await sftp.execStreaming(command, {
      onStdout: (data) => process.stdout.write(data),
      onStderr: (data) => process.stderr.write(data),
    });

    if (exitCode !== 0) {
      throw new Error(`Sync push failed (exit ${exitCode})`);
    }
  } finally {
    sftp.close();
  }
}

async function loadSyncConfigs(options: SyncOptions) {
  const machineName = options.machine ?? (await configService.getMachine());
  if (!machineName) {
    throw new Error('No machine specified. Use -m <machine> or set a default machine.');
  }

  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const storage = await configService.getStorage(options.storageName);
  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const rcloneFlags = buildSyncRcloneFlags(storage.vaultContent);

  return { machineName, localConfig, machine, storage, datastore, sshPrivateKey, rcloneFlags };
}

/**
 * Run backup sync pull — download all repos from storage to a machine.
 */
export async function runBackupSyncPull(options: SyncOptions): Promise<void> {
  const { machineName, localConfig, machine, datastore, sshPrivateKey, rcloneFlags } =
    await loadSyncConfigs(options);

  if (options.debug) {
    outputService.info(`Storage: ${options.storageName}`);
    outputService.info(`Machine: ${machineName} (${machine.ip})`);
    outputService.info(`Rclone flags: ${rcloneFlags.join(' ')}`);
  }

  // Provision renet binary
  outputService.info(`Provisioning renet to ${machine.ip}...`);
  await provisionRenetToRemote({ renetPath: localConfig.renetPath }, machine, sshPrivateKey, {
    debug: options.debug,
  });

  // Build SSH command
  const cmdParts = [
    'sudo',
    '/usr/bin/renet',
    'backup',
    'sync',
    'pull',
    '--datastore',
    datastore,
    ...rcloneFlags,
  ];

  // Add --repo filters
  if (options.repos && options.repos.length > 0) {
    for (const guid of options.repos) {
      cmdParts.push('--repo', guid);
    }
  }

  if (options.override) {
    cmdParts.push('--override');
  }

  if (options.debug) {
    cmdParts.push('--debug');
  }

  const command = cmdParts.map((p) => (p.includes(' ') ? `'${p}'` : p)).join(' ');

  if (options.debug) {
    outputService.info(`[sync] Running: ${command}`);
  }

  // Execute via SSH
  outputService.info(`Pulling all repos from ${options.storageName} to ${machineName}...`);

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    const exitCode = await sftp.execStreaming(command, {
      onStdout: (data) => process.stdout.write(data),
      onStderr: (data) => process.stderr.write(data),
    });

    if (exitCode !== 0) {
      throw new Error(`Sync pull failed (exit ${exitCode})`);
    }
  } finally {
    sftp.close();
  }
}
