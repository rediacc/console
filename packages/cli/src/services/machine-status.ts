/**
 * Machine Status Service
 *
 * Fetches full machine status by SSHing in and running `renet list all --json`.
 * Returns the parsed ListResult for display by the command layer.
 */

import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { ListResult } from '@rediacc/shared/queue-vault/data/list-types.generated';
import { isListResult } from '@rediacc/shared/queue-vault/data/list-types.generated';
import { contextService } from './context.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

interface FetchStatusOptions {
  debug?: boolean;
}

/**
 * Fetch full machine status via SSH.
 *
 * Flow:
 * 1. Load machine config from local context
 * 2. Provision renet binary to remote
 * 3. SSH: run `sudo renet list all --datastore <path> --json`
 * 4. Parse JSON output as ListResult
 */
export async function fetchMachineStatus(
  machineName: string,
  options: FetchStatusOptions = {}
): Promise<ListResult> {
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
  const cmd = `sudo renet list all --datastore ${datastore} --json`;

  if (options.debug) {
    outputService.info(`[status] Running: ${cmd}`);
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
      throw new Error(`renet list all failed (exit ${exitCode}): ${stderr}`);
    }

    const parsed: unknown = JSON.parse(stdout);
    if (!isListResult(parsed)) {
      throw new Error('Failed to parse renet output: unexpected format');
    }

    return parsed;
  } finally {
    sftp.close();
  }
}
