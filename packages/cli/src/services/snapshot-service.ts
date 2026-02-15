/**
 * Snapshot Service
 *
 * Executes snapshot commands on remote machines via SSH.
 * Calls `sudo renet snapshot create|list|delete` directly.
 */

import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { contextService } from './context.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

interface SnapshotCommandOptions {
  debug?: boolean;
}

/**
 * Run a renet snapshot subcommand on a remote machine via SSH.
 *
 * Provisions renet binary, then executes
 * `sudo renet snapshot <subcommand> <flags>` with JSON output.
 */
export async function runSnapshotCommand(
  subcommand: 'create' | 'list' | 'delete',
  machineName: string,
  flags: string[],
  options: SnapshotCommandOptions = {}
): Promise<{ success: boolean; output: string }> {
  const localConfig = await contextService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  // Provision renet binary to remote
  if (options.debug) {
    outputService.info(`Provisioning renet to ${machine.ip}...`);
  }
  await provisionRenetToRemote({ renetPath: localConfig.renetPath }, machine, sshPrivateKey, {
    debug: options.debug,
  });

  // Build command
  const datastore = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
  const cmdParts = [
    'sudo',
    'renet',
    'snapshot',
    subcommand,
    '--datastore',
    datastore,
    '--output',
    'json',
    ...flags,
  ];
  const cmd = cmdParts.join(' ');

  if (options.debug) {
    outputService.info(`[snapshot] Running: ${cmd}`);
  }

  // Connect and execute
  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  let stdout = '';
  let stderr = '';

  try {
    const exitCode = await sftp.execStreaming(cmd, {
      onStdout: (data) => {
        stdout += data.toString();
      },
      onStderr: (data) => {
        stderr += data.toString();
        if (options.debug) {
          process.stderr.write(data);
        }
      },
    });

    if (exitCode !== 0) {
      throw new Error(`renet snapshot ${subcommand} failed (exit ${exitCode}): ${stderr}`);
    }

    return { success: true, output: stdout };
  } finally {
    sftp.close();
  }
}
