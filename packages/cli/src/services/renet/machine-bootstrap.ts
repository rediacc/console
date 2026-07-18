/**
 * Machine bootstrap primitives shared by cloud-machine provisioning and cluster
 * provisioning: wait for SSH, scan host keys, and run `renet setup` over SSH.
 *
 * Lifted out of services/tofu/provision.ts so createCloudMachine (single
 * machine) and createCluster (pool members) share one bootstrap path.
 */

import { setTimeout as sleep } from 'node:timers/promises';
import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { scanHostKeys } from '../../utils/host-keys.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { machineConnections } from '../machine/machine-connection.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

// Re-exported so the provisioning call sites (services/tofu/provision.ts,
// services/cluster/cluster-provision.ts) keep importing it from the bootstrap
// module they already depend on. The implementation lives in utils/host-keys.ts
// because the command layer needs it too.
export { scanHostKeys };

/** Poll until SSH is reachable (host keys scannable), or throw after timeout. */
export async function waitForSSH(ip: string, port: number, timeoutMs = 120_000): Promise<void> {
  const start = Date.now();
  const interval = 5_000;

  while (Date.now() - start < timeoutMs) {
    // scanHostKeys returns '' rather than throwing on any failure, so an
    // empty result — not an exception — is the "not up yet" signal.
    if (scanHostKeys(ip, port)) return;
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

  const lease = await machineConnections.acquireFor(machine, sshPrivateKey);

  try {
    const datastorePath = machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
    const datastoreSize = updatedConfig.datastoreSize ?? NETWORK_DEFAULTS.DATASTORE_SIZE;
    const cmd = `sudo ${remoteRenetPath} setup --auto --datastore ${datastorePath} --datastore-size ${datastoreSize}`;
    const exitCode = await lease.sftp.execStreaming(cmd, {
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => process.stderr.write(data),
    });
    if (exitCode !== 0) {
      outputService.warn(`Machine setup exited with code ${exitCode}`);
    }
  } finally {
    lease.release();
  }
}
