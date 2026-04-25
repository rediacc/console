/**
 * Remote-shell helpers used by both SFTP upload and download paths.
 */

import { createHash } from 'node:crypto';
import type { SFTPClient } from '../sftp/client.js';

export interface SftpTransferResult {
  success: boolean;
  filesTransferred: number;
  bytesTransferred: number;
  /** Number of post-transfer verify mismatches (when options.verify is set). */
  verifyFailures: number;
  errors: string[];
  duration: number;
}

export function shellQuote(arg: string): string {
  // Single-quote escape: end quote, escape, reopen.
  return `'${arg.replaceAll("'", "'\\''")}'`;
}

export function newResult(): SftpTransferResult {
  return {
    success: true,
    filesTransferred: 0,
    bytesTransferred: 0,
    verifyFailures: 0,
    errors: [],
    duration: 0,
  };
}

export function finishResult(result: SftpTransferResult, startTime: number): SftpTransferResult {
  result.duration = Date.now() - startTime;
  result.success = result.errors.length === 0 && result.verifyFailures === 0;
  return result;
}

export function sha256Hex(data: Buffer): string {
  return createHash('sha256').update(data).digest('hex');
}

/**
 * Create remote directories one at a time, capturing per-dir failures so other
 * directories still attempt creation.
 */
export async function ensureRemoteDirs(
  sftp: SFTPClient,
  dirs: string[],
  errors: string[]
): Promise<void> {
  for (const dir of dirs) {
    try {
      await sftp.exec(`mkdir -p ${shellQuote(dir)}`);
    } catch (err) {
      errors.push(`mkdir ${dir}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function chownRemote(
  sftp: SFTPClient,
  user: string,
  paths: string[],
  errors: string[]
): Promise<void> {
  if (paths.length === 0) return;
  const ownerSpec = shellQuote(`${user}:${user}`);
  const chunkSize = 100;
  for (let i = 0; i < paths.length; i += chunkSize) {
    const chunk = paths
      .slice(i, i + chunkSize)
      .map(shellQuote)
      .join(' ');
    try {
      await sftp.exec(`sudo chown ${ownerSpec} ${chunk}`);
    } catch (err) {
      errors.push(`chown: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
}

export async function chmodRemote(
  sftp: SFTPClient,
  remotePath: string,
  mode: number
): Promise<void> {
  await sftp.exec(`chmod ${mode.toString(8)} ${shellQuote(remotePath)}`);
}

export async function symlinkRemote(
  sftp: SFTPClient,
  target: string,
  linkPath: string
): Promise<void> {
  await sftp.exec(`ln -sfn ${shellQuote(target)} ${shellQuote(linkPath)}`);
}

export async function verifyRemoteSha256(
  sftp: SFTPClient,
  remotePath: string,
  expectedHex: string
): Promise<{ ok: boolean; actual?: string }> {
  const out = await sftp.exec(`sha256sum ${shellQuote(remotePath)}`);
  const actual = out.trim().split(/\s+/)[0] ?? '';
  return { ok: actual.toLowerCase() === expectedHex.toLowerCase(), actual };
}
