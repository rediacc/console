/**
 * Renet Binary Transfer - staging uploads for remote provisioning
 *
 * Stages a renet binary on a remote machine, preferring an rsync delta
 * transfer seeded from an existing install slot and falling back to a
 * full SFTP upload. Used by the renet provisioner.
 */

import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient, SFTPClientConfig } from '../shared-desktop/sftp/index.js';
import { createTempSSHKeyFile, removeTempSSHKeyFile } from '../shared-desktop/ssh/index.js';
import { executeRsync, getRsyncCommand } from '../shared-desktop/sync/index.js';
import { outputService } from './output.js';

/** Remote install layout needed to locate delta-sync seed binaries */
export interface RemoteRenetPaths {
  /** Root directory holding versioned install slots */
  installRoot: string;
  /** Path of the `current` symlink pointing at the active slot */
  currentPath: string;
}

interface RemoteSeedCandidate {
  path: string;
  source: 'current' | 'slot';
}

export function shellEscape(v: string): string {
  return `'${v.replaceAll("'", `'\\''`)}'`;
}

/**
 * Stage the renet binary at `stagingPath` on the remote host.
 * Tries an rsync delta transfer first; falls back to a full SFTP upload.
 */
export async function stageRenetBinary(
  sftp: SFTPClient,
  config: SFTPClientConfig,
  stagingPath: string,
  binary: Buffer,
  localHash: string,
  paths: RemoteRenetPaths
): Promise<void> {
  const seedCandidate = await findRemoteSeedCandidate(sftp, paths);
  const remoteRsyncPath = await getRemoteRsyncPath(sftp);
  if (
    await tryDeltaSyncStage(
      sftp,
      config,
      stagingPath,
      binary,
      localHash,
      seedCandidate,
      remoteRsyncPath
    )
  ) {
    return;
  }

  // Stage and install: SFTP upload to /tmp, then atomic mv to a versioned remote path.
  // Uses mv (not cp) so the replacement works even when the binary is running
  // (e.g., during a backup sync). mv replaces the directory entry atomically;
  // the old inode stays alive until the running process exits.
  outputService.info(`Uploading renet to ${config.host}...`);
  const uploadStart = Date.now();
  await sftp.writeFile(stagingPath, binary);
  outputService.info(
    `Uploaded renet to ${config.host} in ${((Date.now() - uploadStart) / 1000).toFixed(1)}s`
  );
}

async function tryDeltaSyncStage(
  sftp: SFTPClient,
  config: SFTPClientConfig,
  stagingPath: string,
  binary: Buffer,
  localHash: string,
  seedCandidate: RemoteSeedCandidate | null,
  remoteRsyncPath: string | null
): Promise<boolean> {
  if (seedCandidate === null || remoteRsyncPath === null || !(await hasLocalRsync())) {
    return false;
  }

  try {
    outputService.info(
      `Seeding remote renet from ${seedCandidate.source === 'current' ? 'current slot' : 'existing slot'}...`
    );
    await sftp.exec(
      `cp -f ${shellEscape(seedCandidate.path)} ${shellEscape(stagingPath)} && chmod 600 ${shellEscape(stagingPath)}`
    );
    outputService.info(`Syncing renet delta to ${config.host}...`);
    await deltaSyncBinary(config, binary, stagingPath, remoteRsyncPath);
    const stagedHash = await getRemoteFileHash(sftp, stagingPath);
    if (stagedHash !== localHash) {
      throw new Error(
        `Staged renet hash mismatch after rsync: expected ${localHash}, got ${stagedHash ?? 'none'}`
      );
    }
    return true;
  } catch (error) {
    outputService.info(`Falling back to full upload to ${config.host}...`);
    await cleanupStagingPath(sftp, stagingPath);
    if (process.env.RDC_DEBUG_RENET_PROVISION === '1') {
      outputService.info(
        `Delta sync fallback reason: ${error instanceof Error ? error.message : String(error)}`
      );
    }
    return false;
  }
}

async function cleanupStagingPath(sftp: SFTPClient, stagingPath: string): Promise<void> {
  try {
    await sftp.exec(`rm -f ${shellEscape(stagingPath)}`);
  } catch {
    // Best-effort cleanup only.
  }
}

async function findRemoteSeedCandidate(
  sftp: SFTPClient,
  paths: RemoteRenetPaths
): Promise<RemoteSeedCandidate | null> {
  const currentTarget = (
    await sftp.exec(`readlink ${shellEscape(paths.currentPath)} 2>/dev/null || true`)
  ).trim();
  if (currentTarget) {
    return { path: currentTarget, source: 'current' };
  }

  const firstSlot = (
    await sftp.exec(
      `find ${shellEscape(paths.installRoot)} -mindepth 2 -maxdepth 2 -type f -name renet 2>/dev/null | head -n 1`
    )
  ).trim();
  if (firstSlot) {
    return { path: firstSlot, source: 'slot' };
  }

  return null;
}

async function getRemoteRsyncPath(sftp: SFTPClient): Promise<string | null> {
  const output = await sftp.exec(
    'if command -v rsync >/dev/null 2>&1; then command -v rsync; elif [ -x /usr/local/bin/rsync-renet ]; then echo /usr/local/bin/rsync-renet; fi'
  );
  const rsyncPath = output.trim();
  return rsyncPath || null;
}

async function hasLocalRsync(): Promise<boolean> {
  try {
    await getRsyncCommand();
    return true;
  } catch {
    return false;
  }
}

async function deltaSyncBinary(
  config: SFTPClientConfig,
  binary: Buffer,
  stagingPath: string,
  remoteRsyncPath: string
): Promise<void> {
  const keyFilePath = await createTempSSHKeyFile(config.privateKey);
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'rdc-renet-'));
  const localBinaryPath = path.join(tempDir, 'renet');

  try {
    await fs.writeFile(localBinaryPath, binary, { mode: 0o700 });
    const sshOptions = [
      '-o StrictHostKeyChecking=no',
      '-o UserKnownHostsFile=/dev/null',
      '-o IdentitiesOnly=yes',
      `-p ${config.port ?? DEFAULTS.SSH.PORT}`,
      `-i "${keyFilePath}"`,
    ].join(' ');
    const destination = `${config.username}@${config.host}:${stagingPath}`;
    const result = await executeRsync({
      sshOptions,
      source: localBinaryPath,
      destination,
      remoteRsyncPath,
    });
    if (!result.success) {
      throw new Error(result.errors.join('\n') || 'rsync transfer failed');
    }
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true });
    await removeTempSSHKeyFile(keyFilePath);
  }
}

async function getRemoteFileHash(sftp: SFTPClient, remotePath: string): Promise<string | null> {
  const output = await sftp.exec(
    `sha256sum ${shellEscape(remotePath)} 2>/dev/null | cut -d' ' -f1 || true`
  );
  const hash = output.trim();
  return hash || null;
}
