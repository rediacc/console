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

// The blob is written into the script inside double quotes, so only base64 characters are admitted.
const SAFE_KEY_BLOB = /^[A-Za-z0-9+/]+={0,2}$/;

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
  repositoryGuid: string,
  datastore: string
): string {
  if (!repositoryGuid) {
    throw new Error(`refusing to deploy a repo key for ${repoName} without a GUID`);
  }
  if (!SAFE_DATASTORE_PATH.test(datastore) || datastore.split('/').includes('..')) {
    throw new Error(
      `refusing to bind repo key ${repoName} to datastore ${JSON.stringify(datastore)}: not a plain absolute path`
    );
  }
  const guidFlag = ` --guid ${repositoryGuid}`;
  const keyLine = `command="${GATEWAY_BIN} sandbox-gateway ${repoName}${guidFlag} --datastore ${datastore}" ${sshPublicKey}`;
  // The whole key blob (the second field of the public key) identifies the key: a 50-character prefix of an ed25519 key holds only ~13 characters of key material, so two keys could delete each other's lines.
  const keyBlob = sshPublicKey.trim().split(/\s+/)[1] ?? '';
  if (!SAFE_KEY_BLOB.test(keyBlob)) {
    throw new Error(
      `refusing to deploy a repo key for ${repoName}: its public key has no base64 blob`
    );
  }

  return [
    'set -e',
    'SSH_DIR="$HOME/.ssh"',
    'AUTH_KEYS="$SSH_DIR/authorized_keys"',
    'mkdir -p "$SSH_DIR" && chmod 700 "$SSH_DIR"',
    `KEY_BLOB="${keyBlob}"`,
    // Remove the old version if present: a line is the key's when one of its whitespace fields is exactly the blob (command= options never hold it).
    // set -e does not stop an && list, so a failed rewrite exits explicitly: appending after it would leave the key on two lines.
    `if [ -f "$AUTH_KEYS" ] && awk -v b="$KEY_BLOB" '{ for (i = 1; i <= NF; i++) if ($i == b) f = 1 } END { exit !f }' "$AUTH_KEYS"; then TEMP=$(mktemp) && awk -v b="$KEY_BLOB" '{ for (i = 1; i <= NF; i++) if ($i == b) next } 1' "$AUTH_KEYS" > "$TEMP" && mv "$TEMP" "$AUTH_KEYS" || { rm -f "$TEMP"; echo "authorized_keys rewrite failed; key not appended" >&2; exit 1; }; fi`,
    // Append new key
    `echo '${keyLine}' >> "$AUTH_KEYS"`,
    'chmod 600 "$AUTH_KEYS"',
  ].join('; ');
}

/**
 * Deploy a repo's SSH public key to a machine's authorized_keys over an
 * established shared SSH session (team key, unsandboxed).
 * Idempotent, replaces the existing line holding the same key blob.
 */
export async function deployRepoKey(
  sftp: SFTPClient,
  repoName: string,
  sshPublicKey: string,
  repositoryGuid: string,
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

const SAFE_KEY_REF = /^[A-Za-z0-9._:-]+$/;

/**
 * Build the authorized_keys removal script for one repo key line, matched by the exact "<repo> --guid <guid> " unit that buildKeyDeploymentScript writes, so a sibling fork or a longer name is never touched.
 */
export function buildKeyRemovalScript(repoName: string, repositoryGuid: string): string {
  if (!SAFE_KEY_REF.test(repoName) || !SAFE_KEY_REF.test(repositoryGuid)) {
    throw new Error(
      `refusing to remove repo key for ${JSON.stringify(repoName)}: unsafe characters`
    );
  }
  const marker = `sandbox-gateway ${repoName} --guid ${repositoryGuid} `;
  return [
    'set -e',
    'AUTH_KEYS="$HOME/.ssh/authorized_keys"',
    // grep -v exits 1 when it kept no line (the key was the only one) and 2 on a read error; only 0 and 1 may replace the file, or a partial read would overwrite authorized_keys and lock the machine out (review ef6dbb53.1).
    `if [ -f "$AUTH_KEYS" ] && grep -qF '${marker}' "$AUTH_KEYS"; then TEMP=$(mktemp); RC=0; grep -vF '${marker}' "$AUTH_KEYS" > "$TEMP" || RC=$?; if [ "$RC" -gt 1 ]; then rm -f "$TEMP"; echo "authorized_keys read failed (grep rc=$RC); left unchanged" >&2; exit 1; fi; cat "$TEMP" > "$AUTH_KEYS"; rm -f "$TEMP"; fi`,
  ].join('; ');
}

/**
 * Remove a repo's key line from a machine's authorized_keys. Best-effort: a failure is reported on stderr and never thrown, so a rollback keeps the error that triggered it.
 */
export async function removeRepoKeyIfDeployed(
  repoName: string,
  machineName: string,
  repositoryGuid: string
): Promise<void> {
  try {
    const lease = await machineConnections.acquire(machineName);
    try {
      const sftp = await lease.ensure();
      await sftp.exec(buildKeyRemovalScript(repoName, repositoryGuid));
    } finally {
      lease.release();
    }
    debugLog(`Removed SSH key for ${repoName} from ${machineName}`);
  } catch (error) {
    writeStderr(
      `Warning: failed to remove SSH key for ${repoName} from ${machineName}: ${error instanceof Error ? error.message : String(error)}\n`
    );
  }
}

/** Counts the sandbox-gateway lines in authorized_keys that carry no --guid, the lines renet's prune scanner treats as orphaned. Prints a bare integer; exits 0 whatever grep finds. */
export const COUNT_UNGUIDED_KEY_LINES_SCRIPT =
  "grep 'sandbox-gateway' \"$HOME/.ssh/authorized_keys\" 2>/dev/null | grep -vc -e ' --guid ' || true";

async function warnOnUnguidedKeyLines(sftp: SFTPClient, machineName: string): Promise<void> {
  try {
    const remaining = Number.parseInt(
      (await sftp.exec(COUNT_UNGUIDED_KEY_LINES_SCRIPT)).trim(),
      10
    );
    if (remaining > 0) {
      writeStderr(
        `Warning: ${remaining} authorized_keys line(s) on ${machineName} carry no --guid; the repos they belong to have no key in the active config, so setup could not re-deploy them\n`
      );
    }
  } catch (error) {
    debugLog(`unguided key line check failed on ${machineName}: ${error}`);
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
      const datastore = () => repoKeyDatastore(name, machine.datastore);
      deployed += (await deployOneKey(sftp, name, machineName, config, datastore)) ? 1 : 0;
    }
    await warnOnUnguidedKeyLines(sftp, machineName);
  } finally {
    lease.release();
  }
  return deployed;
}

/** One repo's key during setup; a failure is a visible warning, never thrown. */
async function deployOneKey(
  sftp: SFTPClient,
  name: string,
  machineName: string,
  config: { sshPublicKey?: string; repositoryGuid: string },
  datastore: () => Promise<string>
): Promise<boolean> {
  try {
    await deployRepoKey(
      sftp,
      name,
      config.sshPublicKey as string,
      config.repositoryGuid,
      await datastore()
    );
    return true;
  } catch (error) {
    writeStderr(
      `Warning: failed to deploy SSH key for ${name} to ${machineName}: ${error instanceof Error ? error.message : String(error)}\n`
    );
    return false;
  }
}
