/**
 * SFTP-based file transfer fallback for systems without rsync.
 * Slower than rsync (no delta sync) but works anywhere SSH works.
 *
 * Parity goals with rsync:
 *  - Symlinks preserved as symlinks (not followed).
 *  - Executable bit preserved via chmod.
 *  - --chown universalUser:universalUser applied (sudo).
 *  - Exclude patterns interpreted with rsync-style globs.
 *  - --verify performs a remote sha256sum check after upload / before download.
 */

import type { Stats } from 'node:fs';
import * as fsPromises from 'node:fs/promises';
import * as path from 'node:path';
import { STATUS_DEFAULTS } from '@rediacc/shared/config/defaults';
import { SFTPClient, type SFTPClientConfig } from '../sftp/client.js';
import { isExcluded } from './sftp-patterns.js';
import {
  type ExpandedSources,
  type SftpFileEntry,
  type SftpSymlinkEntry,
  type SftpUploadSource,
  collectSubdirs,
  expandSftpSources,
} from './sftp-walk.js';
import {
  type SftpTransferResult,
  chmodRemote,
  chownRemote,
  ensureRemoteDirs,
  finishResult,
  newResult,
  sha256Hex,
  shellQuote,
  symlinkRemote,
  verifyRemoteSha256,
} from './sftp-remote-helpers.js';

export {
  isExcluded,
  type SftpFileEntry,
  type SftpSymlinkEntry,
  type SftpTransferResult,
  type SftpUploadSource,
};

export interface SftpTransferOptions {
  /**
   * Patterns to exclude (rsync-style subset). See `sftp-patterns.ts`.
   */
  exclude?: string[];
  /** Progress callback for each file. */
  onProgress?: (file: string, bytesTransferred: number, totalBytes: number) => void;
  /** Dry run — count files without transferring. */
  dryRun?: boolean;
  /** Remote user; when set, upload helpers `sudo chown -R` written paths to `${u}:${u}`. */
  universalUser?: string;
  /** Verify each transferred file with sha256sum. Mismatches surface in errors + verifyFailures. */
  verify?: boolean;
}

// ---------------------------------------------------------------------------
// Internal helpers shared by upload paths.
// ---------------------------------------------------------------------------

async function writeRemoteFile(
  sftp: SFTPClient,
  remotePath: string,
  data: Buffer
): Promise<number> {
  return await sftp.execStreaming(`base64 -d > ${shellQuote(remotePath)}`, {
    stdin: data.toString('base64'),
  });
}

async function maybeChmod(
  sftp: SFTPClient,
  remotePath: string,
  mode: number,
  errors: string[]
): Promise<void> {
  try {
    await chmodRemote(sftp, remotePath, mode);
  } catch (err) {
    errors.push(`chmod ${remotePath}: ${err instanceof Error ? err.message : String(err)}`);
  }
}

async function maybeVerify(
  sftp: SFTPClient,
  remotePath: string,
  data: Buffer,
  result: SftpTransferResult,
  label: string
): Promise<void> {
  try {
    const expected = sha256Hex(data);
    const { ok, actual } = await verifyRemoteSha256(sftp, remotePath, expected);
    if (!ok) {
      result.verifyFailures++;
      result.errors.push(
        `${label}: verify mismatch (expected ${expected}, got ${actual ?? STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER})`
      );
    }
  } catch (err) {
    result.errors.push(`verify ${label}: ${err instanceof Error ? err.message : String(err)}`);
  }
}

interface SingleFileUploadCtx {
  sftp: SFTPClient;
  data: Buffer;
  remotePath: string;
  mode: number;
  options?: SftpTransferOptions;
  result: SftpTransferResult;
  label: string;
}

async function uploadOneFile(ctx: SingleFileUploadCtx): Promise<boolean> {
  const exitCode = await writeRemoteFile(ctx.sftp, ctx.remotePath, ctx.data);
  if (exitCode !== 0) {
    ctx.result.errors.push(`${ctx.label}: remote write failed (exit code ${exitCode})`);
    return false;
  }
  await maybeChmod(ctx.sftp, ctx.remotePath, ctx.mode, ctx.result.errors);
  if (ctx.options?.verify) {
    await maybeVerify(ctx.sftp, ctx.remotePath, ctx.data, ctx.result, ctx.label);
  }
  return true;
}

// ---------------------------------------------------------------------------
// Public: upload a single file.
// ---------------------------------------------------------------------------

/**
 * Upload a single local file to a fully-specified remote file path.
 * Pre-creates `dirname(remoteFilePath)`; preserves mode bits; applies sudo chown
 * when `universalUser` is set; verifies sha256 when `verify` is set.
 */
async function statLocalFile(
  localFilePath: string,
  result: SftpTransferResult
): Promise<Stats | null> {
  try {
    return await fsPromises.stat(localFilePath);
  } catch (err) {
    result.errors.push(`${localFilePath}: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }
}

async function ensureFileParent(
  sftp: SFTPClient,
  remoteFilePath: string,
  errors: string[]
): Promise<void> {
  const remoteDir = path.posix.dirname(remoteFilePath);
  if (remoteDir && remoteDir !== '.' && remoteDir !== '/') {
    await ensureRemoteDirs(sftp, [remoteDir], errors);
  }
}

export async function sftpUploadFile(
  localFilePath: string,
  remoteFilePath: string,
  config: SFTPClientConfig,
  options?: SftpTransferOptions
): Promise<SftpTransferResult> {
  const startTime = Date.now();
  const result = newResult();

  const stat = await statLocalFile(localFilePath, result);
  if (!stat) return finishResult(result, startTime);

  if (options?.dryRun) {
    result.filesTransferred = 1;
    result.bytesTransferred = stat.size;
    return finishResult(result, startTime);
  }

  const sftp = new SFTPClient(config);
  try {
    await sftp.connect();
    await ensureFileParent(sftp, remoteFilePath, result.errors);

    const data = await fsPromises.readFile(localFilePath);
    const ok = await uploadOneFile({
      sftp,
      data,
      remotePath: remoteFilePath,
      mode: stat.mode & 0o777,
      options,
      result,
      label: remoteFilePath,
    });
    if (!ok) return finishResult(result, startTime);

    if (options?.universalUser) {
      await chownRemote(sftp, options.universalUser, [remoteFilePath], result.errors);
    }

    result.filesTransferred = result.errors.length === 0 ? 1 : 0;
    result.bytesTransferred = data.length;
    options?.onProgress?.(path.posix.basename(remoteFilePath), data.length, data.length);
  } catch (err) {
    result.errors.push(`${remoteFilePath}: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    sftp.close();
  }

  return finishResult(result, startTime);
}

// ---------------------------------------------------------------------------
// Public: upload mixed file/dir sources to a remote directory.
// ---------------------------------------------------------------------------

interface MultiUploadCtx {
  sftp: SFTPClient;
  normalizedRemote: string;
  options?: SftpTransferOptions;
  totalBytes: number;
  result: SftpTransferResult;
  writtenPaths: string[];
}

async function uploadFileEntry(file: SftpFileEntry, ctx: MultiUploadCtx): Promise<void> {
  const remoteFilePath = `${ctx.normalizedRemote}/${file.remoteRelative}`;
  try {
    const data = await fsPromises.readFile(file.absolutePath);
    const ok = await uploadOneFile({
      sftp: ctx.sftp,
      data,
      remotePath: remoteFilePath,
      mode: file.mode,
      options: ctx.options,
      result: ctx.result,
      label: file.remoteRelative,
    });
    if (!ok) return;
    ctx.writtenPaths.push(remoteFilePath);
    ctx.result.filesTransferred++;
    ctx.result.bytesTransferred += data.length;
    ctx.options?.onProgress?.(file.remoteRelative, ctx.result.bytesTransferred, ctx.totalBytes);
  } catch (err) {
    ctx.result.errors.push(
      `${file.remoteRelative}: ${err instanceof Error ? err.message : String(err)}`
    );
  }
}

async function uploadSymlinkEntry(link: SftpSymlinkEntry, ctx: MultiUploadCtx): Promise<void> {
  const remoteLinkPath = `${ctx.normalizedRemote}/${link.remoteRelative}`;
  try {
    await symlinkRemote(ctx.sftp, link.target, remoteLinkPath);
    ctx.writtenPaths.push(remoteLinkPath);
  } catch (err) {
    ctx.result.errors.push(
      `symlink ${link.remoteRelative}: ${err instanceof Error ? err.message : String(err)}`
    );
  }
}

function dirsToCreate(normalizedRemote: string, expanded: ExpandedSources): string[] {
  const allRel = collectSubdirs([
    ...expanded.files.map((f) => f.remoteRelative),
    ...expanded.symlinks.map((s) => s.remoteRelative),
  ]);
  return [normalizedRemote, ...allRel.map((d) => `${normalizedRemote}/${d}`)];
}

/**
 * Upload one or more local files/directories to a remote directory via SFTP.
 * Files (single sources) land at `<remoteDir>/<basename>`; directory contents
 * are copied preserving their hierarchy under `<remoteDir>/`. Symlinks are
 * preserved as `ln -sfn` calls; modes are reapplied via chmod; ownership is
 * chowned to `universalUser` when set; sha256 verify runs when requested.
 */
export async function sftpUploadPaths(
  sources: SftpUploadSource[],
  remoteDir: string,
  config: SFTPClientConfig,
  options?: SftpTransferOptions
): Promise<SftpTransferResult> {
  const startTime = Date.now();
  const result = newResult();
  const exclude = options?.exclude ?? [];

  const expanded = await expandSftpSources(sources, exclude);

  if (options?.dryRun) {
    result.filesTransferred = expanded.files.length;
    result.bytesTransferred = expanded.files.reduce((sum, f) => sum + f.size, 0);
    return finishResult(result, startTime);
  }

  const sftp = new SFTPClient(config);
  try {
    await sftp.connect();

    const normalizedRemote = remoteDir.replace(/\/+$/, '');
    await ensureRemoteDirs(sftp, dirsToCreate(normalizedRemote, expanded), result.errors);

    const ctx: MultiUploadCtx = {
      sftp,
      normalizedRemote,
      options,
      totalBytes: expanded.files.reduce((s, f) => s + f.size, 0),
      result,
      writtenPaths: [],
    };

    for (const file of expanded.files) {
      await uploadFileEntry(file, ctx);
    }
    for (const link of expanded.symlinks) {
      await uploadSymlinkEntry(link, ctx);
    }

    if (options?.universalUser && ctx.writtenPaths.length > 0) {
      await chownRemote(sftp, options.universalUser, ctx.writtenPaths, result.errors);
    }
  } finally {
    sftp.close();
  }

  return finishResult(result, startTime);
}

// ---------------------------------------------------------------------------
// Public: download a remote directory or file.
// ---------------------------------------------------------------------------

interface RemoteFileInfo {
  relativePath: string;
  size: number;
}

async function listRemoteFiles(
  sftp: SFTPClient,
  normalizedRemote: string
): Promise<RemoteFileInfo[]> {
  // The primary `find -printf '%P'` already emits paths relative to the
  // search root, no sed strip needed. The fallback `find -exec stat` is
  // for systems without GNU find's -printf; we strip the prefix in JS to
  // avoid shell injection (the previous sed-based strip interpolated
  // normalizedRemote unquoted into a `s|...|` expression, which broke on
  // paths containing `|` and was injection-vulnerable for callers passing
  // attacker-controlled paths). An empty normalizedRemote (e.g. root `/`)
  // would also have produced a no-op sed expression; the JS strip handles
  // that correctly.
  const findOutput = await sftp.exec(
    `find ${shellQuote(normalizedRemote)} -type f -printf '%P\\t%s\\n' 2>/dev/null || ` +
      `find ${shellQuote(normalizedRemote)} -type f -exec stat -c '%n\\t%s' {} \\; 2>/dev/null`
  );
  const prefix = normalizedRemote.endsWith('/') ? normalizedRemote : `${normalizedRemote}/`;
  return findOutput
    .trim()
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const [absOrRel, sizeStr] = line.split('\t');
      const relativePath = absOrRel.startsWith(prefix) ? absOrRel.slice(prefix.length) : absOrRel;
      return { relativePath, size: Number.parseInt(sizeStr || '0', 10) };
    });
}

interface DirDownloadCtx {
  sftp: SFTPClient;
  normalizedRemote: string;
  normalizedLocal: string;
  options?: SftpTransferOptions;
  totalBytes: number;
  result: SftpTransferResult;
}

async function downloadOneFile(file: RemoteFileInfo, ctx: DirDownloadCtx): Promise<void> {
  const localFilePath = path.join(ctx.normalizedLocal, file.relativePath);
  try {
    await fsPromises.mkdir(path.dirname(localFilePath), { recursive: true });

    const remoteFile = `${ctx.normalizedRemote}/${file.relativePath}`;
    const b64 = await ctx.sftp.exec(`base64 ${shellQuote(remoteFile)}`);
    const data = Buffer.from(b64.trim(), 'base64');
    await fsPromises.writeFile(localFilePath, data);

    if (ctx.options?.verify) {
      const expected = sha256Hex(data);
      const out = await ctx.sftp.exec(`sha256sum ${shellQuote(remoteFile)}`);
      const actual = out.trim().split(/\s+/)[0] ?? '';
      if (actual.toLowerCase() !== expected.toLowerCase()) {
        ctx.result.verifyFailures++;
        ctx.result.errors.push(
          `${file.relativePath}: verify mismatch (expected ${expected}, got ${actual || STATUS_DEFAULTS.UNKNOWN_PLACEHOLDER})`
        );
      }
    }

    ctx.result.filesTransferred++;
    ctx.result.bytesTransferred += data.length;
    ctx.options?.onProgress?.(file.relativePath, ctx.result.bytesTransferred, ctx.totalBytes);
  } catch (err) {
    ctx.result.errors.push(
      `${file.relativePath}: ${err instanceof Error ? err.message : String(err)}`
    );
  }
}

/**
 * Download a remote directory tree to a local path. No delta sync.
 */
export async function sftpDownloadDirectory(
  remotePath: string,
  localPath: string,
  config: SFTPClientConfig,
  options?: SftpTransferOptions
): Promise<SftpTransferResult> {
  const startTime = Date.now();
  const result = newResult();

  const sftp = new SFTPClient(config);
  try {
    await sftp.connect();

    const normalizedRemote = remotePath.replace(/\/+$/, '');
    const normalizedLocal = localPath.replace(/[/\\]+$/, '');

    const remoteFiles = await listRemoteFiles(sftp, normalizedRemote);

    if (options?.dryRun) {
      result.filesTransferred = remoteFiles.length;
      result.bytesTransferred = remoteFiles.reduce((sum, f) => sum + f.size, 0);
      return finishResult(result, startTime);
    }

    await fsPromises.mkdir(normalizedLocal, { recursive: true });

    const ctx: DirDownloadCtx = {
      sftp,
      normalizedRemote,
      normalizedLocal,
      options,
      totalBytes: remoteFiles.reduce((s, f) => s + f.size, 0),
      result,
    };
    for (const file of remoteFiles) {
      await downloadOneFile(file, ctx);
    }
  } finally {
    sftp.close();
  }

  return finishResult(result, startTime);
}

async function fetchRemoteSize(sftp: SFTPClient, remotePath: string): Promise<number> {
  const sizeOut = await sftp.exec(
    `stat -c '%s' ${shellQuote(remotePath)} 2>/dev/null || wc -c < ${shellQuote(remotePath)}`
  );
  return Number.parseInt(sizeOut.trim(), 10) || 0;
}

/**
 * Download a single remote file into a local directory.
 * The file lands at `<localDir>/<basename(remoteFilePath)>`.
 */
export async function sftpDownloadFile(
  remoteFilePath: string,
  localDir: string,
  config: SFTPClientConfig,
  options?: SftpTransferOptions
): Promise<SftpTransferResult> {
  const startTime = Date.now();
  const result = newResult();
  const normalizedRemote = remoteFilePath.replace(/\/+$/, '');
  const normalizedLocalDir = localDir.replace(/[/\\]+$/, '');
  const basename = path.posix.basename(normalizedRemote);
  const localFilePath = path.join(normalizedLocalDir, basename);

  if (options?.dryRun) {
    const sftp = new SFTPClient(config);
    try {
      await sftp.connect();
      result.filesTransferred = 1;
      result.bytesTransferred = await fetchRemoteSize(sftp, normalizedRemote);
      return finishResult(result, startTime);
    } finally {
      sftp.close();
    }
  }

  const sftp = new SFTPClient(config);
  try {
    await sftp.connect();
    await fsPromises.mkdir(normalizedLocalDir, { recursive: true });

    const b64 = await sftp.exec(`base64 ${shellQuote(normalizedRemote)}`);
    const data = Buffer.from(b64.trim(), 'base64');
    await fsPromises.writeFile(localFilePath, data);
    result.bytesTransferred = data.length;

    if (options?.verify) {
      await maybeVerify(sftp, normalizedRemote, data, result, basename);
    }

    options?.onProgress?.(basename, data.length, data.length);
    if (result.errors.length === 0 && result.verifyFailures === 0) {
      result.filesTransferred = 1;
    }
  } catch (err) {
    result.errors.push(`${basename}: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    sftp.close();
  }

  return finishResult(result, startTime);
}
