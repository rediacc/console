/**
 * Per-repo SSH key deployment service.
 * Deploys/removes repo public keys to remote machines' authorized_keys
 * with the sandbox-gateway command= prefix for server-side isolation.
 */

import type { SFTPClient } from '../shared-desktop/sftp/index.js';
import { debugLog } from '../utils/debug.js';
import { configService } from './config-resources.js';
import { machineConnections } from './machine-connection.js';
import { REMOTE_RENET_PATH } from './renet-provisioner.js';

const GATEWAY_BIN = REMOTE_RENET_PATH;

/**
 * Build the atomic authorized_keys deployment script for a repo key:
 * check if exists → replace or append. Exported for snapshot testing —
 * the script must stay byte-identical across transport changes.
 */
export function buildKeyDeploymentScript(
  repoName: string,
  sshPublicKey: string,
  repositoryGuid?: string
): string {
  const guidFlag = repositoryGuid ? ` --guid ${repositoryGuid}` : '';
  const keyLine = `command="${GATEWAY_BIN} sandbox-gateway ${repoName}${guidFlag}" ${sshPublicKey}`;
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
 * Idempotent — replaces existing key if prefix matches.
 */
export async function deployRepoKey(
  sftp: SFTPClient,
  repoName: string,
  sshPublicKey: string,
  repositoryGuid?: string
): Promise<void> {
  await sftp.exec(buildKeyDeploymentScript(repoName, sshPublicKey, repositoryGuid));
  debugLog(`Deployed SSH key for repo ${repoName}`);
}

/**
 * Deploy a repo's key if it has one. Resolves machine config and team key automatically.
 * Non-fatal — logs warning on failure.
 */
export async function deployRepoKeyIfNeeded(repoName: string, machineName: string): Promise<void> {
  try {
    const repo = await configService.getRepository(repoName);
    if (!repo?.sshPublicKey) {
      debugLog(`deployRepoKey: no sshPublicKey for ${repoName} (repo found: ${!!repo})`);
      return;
    }

    const localConfig = await configService.getLocalConfig();
    if (!localConfig.machines[machineName]) {
      debugLog(`deployRepoKey: machine ${machineName} not found`);
      return;
    }

    const lease = await machineConnections.acquire(machineName);
    try {
      const sftp = await lease.ensure();
      await deployRepoKey(sftp, repoName, repo.sshPublicKey, repo.repositoryGuid);
    } finally {
      lease.release();
    }
    debugLog(`Deployed SSH key for ${repoName} to ${machineName}`);
  } catch (error) {
    // Log visibly — silent failures here cause hard-to-debug connection issues
    console.warn(
      `Warning: failed to deploy SSH key for ${repoName}: ${error instanceof Error ? error.message : error}`
    );
  }
}

/**
 * Deploy ALL repo keys to a machine over a single shared SSH session.
 * Used after setup-machine.
 */
export async function deployAllRepoKeys(machineName: string): Promise<number> {
  const localConfig = await configService.getLocalConfig();
  if (!localConfig.machines[machineName]) return 0;

  const repos = await configService.listRepositories();
  if (!repos.some(({ config }) => config.sshPublicKey)) return 0;

  const lease = await machineConnections.acquire(machineName);
  let deployed = 0;
  try {
    const sftp = await lease.ensure();
    for (const { name, config } of repos) {
      if (!config.sshPublicKey) continue;
      try {
        await deployRepoKey(sftp, name, config.sshPublicKey, config.repositoryGuid);
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
