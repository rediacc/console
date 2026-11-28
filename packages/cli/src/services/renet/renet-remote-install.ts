/**
 * The remote install step of a renet provision: the locked install command, its result parsing and
 * the install-root paths it names (split out of renet-provisioner.ts, which keeps the cache and the
 * provision flow).
 */

import * as path from 'node:path';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { busy } from '../../utils/cli-exit-error.js';
import { shellQuote } from '../../utils/shell-quote.js';
import type { InstallResult } from './renet-provisioner-types.js';
import { buildSlotPruneStep } from './renet-slot-prune.js';

/** Root directory for versioned renet installs on remote machines */
export const REMOTE_INSTALL_ROOT = '/usr/lib/rediacc/renet';
export const REMOTE_CURRENT_DIR = `${REMOTE_INSTALL_ROOT}/current`;
export const REMOTE_CURRENT_PATH = `${REMOTE_CURRENT_DIR}/renet`;

/** Prefix for per-attempt staging uploads (no sudo needed for /tmp) */
const STAGING_PATH_PREFIX = '/tmp/.rdc-staging-renet';

/** Remote host-scoped lock file for install/restart critical section */
export const REMOTE_LOCK_PATH = '/tmp/.rdc-renet-provision.lock';

/** Versioned renet slots kept after an install, `current` included: current plus the 2 previous. Matches renet's `daemons upgrade --keep-slots` default. */
const REMOTE_KEEP_SLOTS = 3;

/** Where systemd units that name a renet slot live. */
const REMOTE_UNIT_DIR = '/etc/systemd/system';

/** flock's `-E` exit status, chosen outside anything the install body emits. */
export const REMOTE_FLOCK_TIMEOUT_EXIT = 75;

export function buildStagingPath(): string {
  const timestamp = Date.now();
  const random = Math.random().toString(16).slice(2, 10);
  return `${STAGING_PATH_PREFIX}-${process.pid}-${timestamp}-${random}`;
}

/** The install output's status tokens as a result; anything else is not an install. */
function parseInstallOutput(output: string): InstallResult {
  const trimmed = output.trim();
  const statusTokens = new Set(trimmed.split(/\s+/).filter(Boolean));
  const binaryUpdated = statusTokens.has('UPDATED');
  const currentUpdated = statusTokens.has('CURRENT_UPDATED') || binaryUpdated;
  if (binaryUpdated || statusTokens.has('VERIFIED') || statusTokens.has('CURRENT_UPDATED')) {
    return { binaryUpdated, currentUpdated };
  }
  throw new Error(`Unexpected provisioning result: ${trimmed || '(empty output)'}`);
}

/** The error a failed install surfaces: the flock refusals are named, anything else passes through. */
function installFailure(error: unknown): unknown {
  if (error instanceof Error && error.message.includes('FLOCK_MISSING')) {
    return new Error(
      "Remote machine is missing 'flock', which is required for safe concurrent renet provisioning"
    );
  }
  if (error instanceof Error && error.message.includes('FLOCK_TIMEOUT')) {
    // The competing process may belong to a different workstation entirely, so unlike the local lock there is no pid worth naming here.
    return busy(
      `Another process on the machine held the renet install lock for over 120s, so provisioning was skipped.`,
      {
        details: [`Lock: ${REMOTE_LOCK_PATH}`],
        next: {
          summary: 'Wait for the other provisioning run to finish, then retry.',
          options: [
            {
              description: 'Find the process holding the remote lock',
              run: `rdc term connect <machine> -c "fuser -v ${REMOTE_LOCK_PATH}"`,
            },
          ],
        },
      }
    );
  }
  return error;
}

export async function installWithRemoteLock(
  sftp: SFTPClient,
  stagingPath: string,
  localHash: string,
  remoteInstallPath: string
): Promise<InstallResult> {
  try {
    const output = await sftp.exec(
      buildLockedInstallCommand(stagingPath, localHash, remoteInstallPath)
    );
    return parseInstallOutput(output);
  } catch (error) {
    try {
      await sftp.exec(`rm -f ${stagingPath}`);
    } catch {
      // Best-effort cleanup only.
    }
    throw installFailure(error);
  }
}

export function buildLockedInstallCommand(
  stagingPath: string,
  localHash: string,
  remoteInstallPath: string
): string {
  const escapedHash = shellQuote(localHash);
  const escapedStagingPath = shellQuote(stagingPath);
  const escapedInstallPath = shellQuote(remoteInstallPath);
  const escapedLockPath = shellQuote(REMOTE_LOCK_PATH);
  const escapedInstallDir = shellQuote(path.dirname(remoteInstallPath));
  const escapedCurrentDir = shellQuote(REMOTE_CURRENT_DIR);
  const escapedCurrentPath = shellQuote(REMOTE_CURRENT_PATH);
  const escapedCurrentTmpPath = shellQuote(`${REMOTE_CURRENT_PATH}.tmp`);

  const body = [
    // Execute under POSIX sh on remote hosts; do not rely on bash-only options.
    'set -eu',
    `hash_remote() { (${escapedInstallPath} hash 2>/dev/null || sha256sum ${escapedInstallPath} | cut -d' ' -f1) 2>/dev/null || true; }`,
    `current_target() { readlink ${escapedCurrentPath} 2>/dev/null || true; }`,
    'result=',
    `sudo mkdir -p ${escapedInstallDir}`,
    `sudo mkdir -p ${escapedCurrentDir}`,
    `if [ "$(hash_remote)" = ${escapedHash} ]; then rm -f ${escapedStagingPath}; else sudo chmod 755 ${escapedStagingPath}; sudo mv -f ${escapedStagingPath} ${escapedInstallPath}; result=UPDATED; fi`,
    `if [ "$(current_target)" != ${escapedInstallPath} ]; then sudo ln -sfn ${escapedInstallPath} ${escapedCurrentTmpPath}; sudo mv -Tf ${escapedCurrentTmpPath} ${escapedCurrentPath}; if [ -n "$result" ]; then result="$result CURRENT_UPDATED"; else result=CURRENT_UPDATED; fi; fi`,
    // Ensure /usr/bin/renet symlinks to current so "sudo renet" always resolves to the provisioned binary
    `if [ ! -L /usr/bin/renet ] || [ "$(readlink /usr/bin/renet)" != ${escapedCurrentPath} ]; then sudo ln -sf ${escapedCurrentPath} /usr/bin/renet; fi`,
    // Prune old slots inside the same lock, after current points at the new slot.
    `(${buildSlotPruneStep({
      root: REMOTE_INSTALL_ROOT,
      currentPath: REMOTE_CURRENT_PATH,
      installPath: remoteInstallPath,
      unitDir: REMOTE_UNIT_DIR,
      keep: REMOTE_KEEP_SLOTS,
      sudo: 'sudo',
    })}) || true`,
    'if [ -z "$result" ]; then result=VERIFIED; fi',
    'echo "$result"',
  ].join('; ');
  const quotedBody = shellQuote(body);
  // `-E ${REMOTE_FLOCK_TIMEOUT_EXIT}` gives the lock-not-acquired case its own
  // exit status. Without it flock exits 1, which the install body can also produce, so a machine busy with another operator's provision was reported as "Unexpected provisioning result: (empty output)" and looked like a
  // broken install. -E is util-linux >= 2.20 (2011); the probe above still
  // only checks for flock's presence, and an -E-less flock fails loudly rather than silently mis-reporting.
  return `command -v flock >/dev/null 2>&1 || { echo FLOCK_MISSING >&2; exit 127; }; flock -w 120 -E ${REMOTE_FLOCK_TIMEOUT_EXIT} ${escapedLockPath} sh -c ${quotedBody} || { rc=$?; [ "$rc" = ${REMOTE_FLOCK_TIMEOUT_EXIT} ] && echo FLOCK_TIMEOUT >&2; exit "$rc"; }`;
}
