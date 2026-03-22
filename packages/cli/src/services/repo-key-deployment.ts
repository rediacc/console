/**
 * Per-repo SSH key deployment service.
 * Deploys/removes repo public keys to remote machines' authorized_keys
 * with the sandbox-gateway command= prefix for server-side isolation.
 */

import { SSH_DEFAULTS } from '@rediacc/shared/config/defaults';
import { SSHConnection, spawnSSH } from '@rediacc/shared-desktop/ssh';
import type { MachineConfig } from '../types/index.js';
import { debugLog } from '../utils/debug.js';
import { configService } from './config-resources.js';
import { readSSHKey } from './renet-execution.js';

const GATEWAY_BIN = '/usr/lib/rediacc/renet/current/renet';

/**
 * Deploy a repo's SSH public key to a machine's authorized_keys.
 * Uses the team key for SSH access (unsandboxed).
 * Idempotent — replaces existing key if prefix matches.
 */
export async function deployRepoKey(
  machine: MachineConfig,
  teamKey: string,
  knownHosts: string,
  repoName: string,
  sshPublicKey: string,
  repositoryGuid?: string
): Promise<void> {
  const guidFlag = repositoryGuid ? ` --guid ${repositoryGuid}` : '';
  const keyLine = `command="${GATEWAY_BIN} sandbox-gateway ${repoName}${guidFlag}" ${sshPublicKey}`;
  const keyPrefix = sshPublicKey.slice(0, 50);

  // Atomic deployment script: check if exists → replace or append
  const script = [
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

  await execSSHCommand(machine, teamKey, knownHosts, script);
  debugLog(`Deployed SSH key for repo ${repoName} to ${machine.ip}`);
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
    const machine = localConfig.machines[machineName];
    if (!machine) {
      debugLog(`deployRepoKey: machine ${machineName} not found`);
      return;
    }

    const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
    await deployRepoKey(
      machine,
      teamKey,
      machine.knownHosts ?? '',
      repoName,
      repo.sshPublicKey,
      repo.repositoryGuid
    );
    debugLog(`Deployed SSH key for ${repoName} to ${machineName}`);
  } catch (error) {
    // Log visibly — silent failures here cause hard-to-debug connection issues
    console.warn(
      `Warning: failed to deploy SSH key for ${repoName}: ${error instanceof Error ? error.message : error}`
    );
  }
}

/**
  try {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine) return;

    const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
    const sandboxPath = `/mnt/rediacc/.interim/sandbox/${repoName}`;
    const script = `if [ -d "${sandboxPath}" ]; then rm -rf "${sandboxPath}"; fi`;
    await execSSHCommand(machine, teamKey, machine.knownHosts ?? '', script);
    debugLog(`Removed sandbox dir for ${repoName} on ${machine.ip}`);
  } catch (error) {
    debugLog(`Warning: failed to cleanup sandbox dir for ${repoName}: ${error}`);
  }
}

/**
 * Deploy ALL repo keys to a machine. Used after setup-machine.
 */
export async function deployAllRepoKeys(machineName: string): Promise<number> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) return 0;

  const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  const repos = await configService.listRepositories();

  let deployed = 0;
  for (const { name, config } of repos) {
    if (config.sshPublicKey) {
      try {
        await deployRepoKey(
          machine,
          teamKey,
          machine.knownHosts ?? '',
          name,
          config.sshPublicKey,
          config.repositoryGuid
        );
        deployed++;
      } catch (error) {
        debugLog(`Warning: failed to deploy key for ${name}: ${error}`);
      }
    }
  }
  return deployed;
}

async function execSSHCommand(
  machine: MachineConfig,
  teamKey: string,
  knownHosts: string,
  command: string
): Promise<void> {
  const sshConnection = new SSHConnection(teamKey, knownHosts, {
    port: machine.port ?? SSH_DEFAULTS.PORT,
  });

  try {
    await sshConnection.setup();
    const destination = `${machine.user}@${machine.ip}`;

    const child = spawnSSH(destination, sshConnection.sshOptions, command, {
      env: process.env,
      stdio: 'pipe',
      agentSocketPath: sshConnection.agentSocketPath,
    });

    let stderr = '';
    child.stderr?.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    await new Promise<void>((resolve, reject) => {
      child.on('exit', (code: number | null) => {
        if (code === 0 || code === null) resolve();
        else
          reject(
            new Error(`SSH command failed with code ${code}${stderr ? `: ${stderr.trim()}` : ''}`)
          );
      });
      child.on('error', reject);
    });
  } finally {
    await sshConnection.cleanup();
  }
}
