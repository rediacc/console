/**
 * Per-repo SSH key deployment service.
 * Deploys/removes repo public keys to remote machines' authorized_keys
 * with the sandbox-gateway command= prefix for server-side isolation.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { debugLog } from '../../utils/debug.js';
import { recordedDatastoreMount } from '../../utils/repo-executor.js';
import { configService } from '../config/config-resources.js';
import { writeStderr } from '../core/request-context.js';
import { machineConnections } from '../machine/machine-connection.js';
import { REMOTE_RENET_PATH } from '../renet/renet-provisioner.js';

const GATEWAY_BIN = REMOTE_RENET_PATH;

// The datastore is written into the command= entry, which sshd hands to a shell and which sits inside a single-quoted echo below, so only plain absolute path characters are admitted.
const SAFE_DATASTORE_PATH = /^\/[A-Za-z0-9._/-]+$/;

/**
 * The datastore a repo key is bound to: the datastore the repo is recorded on, else the machine's implicit default datastore.
 * renet sandbox-gateway treats the --datastore of the key line as authoritative and refuses a session whose client value disagrees, so a wrong binding locks the repo's sessions out.
 */
async function repoKeyDatastore(
  repoKey: string,
  machineDatastore: string | undefined
): Promise<string> {
  return (
    (await recordedDatastoreMount(repoKey)) ?? machineDatastore ?? NETWORK_DEFAULTS.DATASTORE_PATH
  );
}

/**
 * Build the atomic authorized_keys deployment script for a repo key:
 * check if exists → replace or append. Exported for snapshot testing ,
 * the script must stay byte-identical across transport changes.
 *
 * --datastore follows --guid: renet's prune scanner (pkg/prune sandboxGatewayLineRegex) reads "<repo> --guid <uuid>" as one unit and treats a line with anything between the repo name and --guid as orphaned.
 */
export function buildKeyDeploymentScript(
  repoName: string,
  sshPublicKey: string,
  repositoryGuid: string | undefined,
  datastore: string
): string {
  if (!SAFE_DATASTORE_PATH.test(datastore) || datastore.split('/').includes('..')) {
    throw new Error(
      `refusing to bind repo key ${repoName} to datastore ${JSON.stringify(datastore)}: not a plain absolute path`
    );
  }
  const guidFlag = repositoryGuid ? ` --guid ${repositoryGuid}` : '';
  const keyLine = `command="${GATEWAY_BIN} sandbox-gateway ${repoName}${guidFlag} --datastore ${datastore}" ${sshPublicKey}`;
  const keyPrefix = sshPublicKey.slice(0, 50);

  return [
    'set -e',
    'SSH_DIR="$HOME/.ssh"',
    'AUTH_KEYS="$SSH_DIR/authorized_keys"',
    'mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"',
    `KEY_PREFIX="${keyPrefix}"`,
    // Remove old version if exists (by key prefix match)
    `if [ -f "$AUTH_KEYS" ] && grep -qF "$KEY_PREFIX" "$AUTH_KEYS"; then TEMP=$(mktemp) && grep -vF "$KEY_PREFIX" "$AUTH_KEYS" > "$TEMP" 2>/dev/null || true && mv "$TEMP" "$AUTH_KEYS"; fi`,
    // Append new key
    `echo '${keyLine}' >> "$AUTH_KEYS"`,
    'chmod 600 "$AUTH_KEYS"',
  ].join('; ');
}

/**
 * Deploy a repo's SSH public key to a machine's authorized_keys over an
 * established shared SSH session (team key, unsandboxed).
 * Idempotent, replaces existing key if prefix matches.
 */
export async function deployRepoKey(
  sftp: SFTPClient,
  repoName: string,
  sshPublicKey: string,
  repositoryGuid: string | undefined,
  datastore: string
): Promise<void> {
  await sftp.exec(buildKeyDeploymentScript(repoName, sshPublicKey, repositoryGuid, datastore));
  debugLog(`Deployed SSH key for repo ${repoName}`);
}

/**
 * Deploy a repo's key if it has one. Resolves machine config and team key automatically.
 * Non-fatal, logs warning on failure.
 */
export async function deployRepoKeyIfNeeded(repoName: string, machineName: string): Promise<void> {
  try {
    const repo = await configService.getRepository(repoName);
    if (!repo?.sshPublicKey) {
      debugLog(`deployRepoKey: no sshPublicKey for ${repoName} (repo found: ${!!repo})`);
      return;
    }

    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine) {
      debugLog(`deployRepoKey: machine ${machineName} not found`);
      return;
    }
    const datastore = await repoKeyDatastore(repoName, machine.datastore);

    const lease = await machineConnections.acquire(machineName);
    try {
      const sftp = await lease.ensure();
      await deployRepoKey(sftp, repoName, repo.sshPublicKey, repo.repositoryGuid, datastore);
    } finally {
      lease.release();
    }
    debugLog(`Deployed SSH key for ${repoName} to ${machineName}`);
  } catch (error) {
    // Log visibly, silent failures here cause hard-to-debug connection issues
    writeStderr(
      `Warning: failed to deploy SSH key for ${repoName}: ${error instanceof Error ? error.message : String(error)}\n`
    );
  }
}

/**
 * Deploy ALL repo keys to a machine over a single shared SSH session.
 * Used after setup-machine.
 */
export async function deployAllRepoKeys(machineName: string): Promise<number> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) return 0;

  const repos = await configService.listRepositories();
  if (!repos.some(({ config }) => config.sshPublicKey)) return 0;

  const lease = await machineConnections.acquire(machineName);
  let deployed = 0;
  try {
    const sftp = await lease.ensure();
    for (const { name, config } of repos) {
      if (!config.sshPublicKey) continue;
      try {
        const datastore = await repoKeyDatastore(name, machine.datastore);
        await deployRepoKey(sftp, name, config.sshPublicKey, config.repositoryGuid, datastore);
        deployed++;
      } catch (error) {
        debugLog(`Warning: failed to deploy key for ${name}: ${error}`);
      }
    }
  } finally {
    lease.release();
  }
  return deployed;
}
