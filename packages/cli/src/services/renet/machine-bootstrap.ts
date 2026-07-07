/**
 * Machine bootstrap primitives shared by cloud-machine provisioning and cluster
 * provisioning: wait for SSH, scan host keys, and run `renet setup` over SSH.
 *
 * Lifted out of services/tofu/provision.ts so createCloudMachine (single
 * machine) and createCluster (pool members) share one bootstrap path.
 */

import { execFileSync } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '../../remote/sftp/index.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

/** ssh-keyscan the host, returning its known_hosts lines (empty on failure). */
export function scanHostKeys(ip: string, port: number): string {
  try {
    return execFileSync('ssh-keyscan', ['-p', String(port), ip], {
      encoding: 'utf-8',
      timeout: 10_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return '';
  }
}

/** Poll until SSH is reachable (host keys scannable), or throw after timeout. */
export async function waitForSSH(ip: string, port: number, timeoutMs = 120_000): Promise<void> {
  const start = Date.now();
  const interval = 5_000;

  while (Date.now() - start < timeoutMs) {
    try {
      const keys = scanHostKeys(ip, port);
      if (keys) return;
    } catch {
      // ignore
    }
    await sleep(interval);
  }

  throw new Error(`SSH not reachable at ${ip}:${port} after ${timeoutMs / 1000}s`);
}

/**
 * Bootstrap a machine via SSH: provision the renet binary, then run
 * `renet setup --auto`. The machine must already exist in config.
 */
export async function bootstrapMachine(
  machineName: string,
  options: { debug?: boolean }
): Promise<void> {
  const updatedConfig = await configService.getLocalConfig();
  const machine = updatedConfig.machines[machineName]!;
  const sshPrivateKey =
    updatedConfig.sshPrivateKey ?? (await readSSHKey(updatedConfig.ssh.privateKeyPath));

  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    updatedConfig,
    machine,
    sshPrivateKey,
    { debug: options.debug }
  );

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    const datastorePath = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
    const datastoreSize = updatedConfig.datastoreSize ?? NETWORK_DEFAULTS.DATASTORE_SIZE;
    const cmd = `sudo ${remoteRenetPath} setup --auto --datastore ${datastorePath} --datastore-size ${datastoreSize}`;
    const exitCode = await sftp.execStreaming(cmd, {
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => process.stderr.write(data),
    });
    if (exitCode !== 0) {
      outputService.warn(`Machine setup exited with code ${exitCode}`);
    }
  } finally {
    sftp.close();
  }
}
