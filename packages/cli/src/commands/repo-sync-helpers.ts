import { existsSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  formatChangesSummary,
  formatDetailedChanges,
  getRsyncPreview,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from '@rediacc/shared-desktop/sync';
import chalk from 'chalk';
import { t } from '../i18n/index.js';

export interface SyncUploadOptions {
  team?: string;
  machine?: string;
  repository?: string;
  local?: string[];
  remote?: string;
  remoteFile?: string;
  mirror?: boolean;
  verify?: boolean;
  confirm?: boolean;
  exclude?: string[];
  dryRun?: boolean;
  [key: string]: unknown;
}

export interface SyncDownloadOptions {
  team?: string;
  machine?: string;
  repository?: string;
  local?: string;
  remote?: string;
  remoteFile?: string;
  mirror?: boolean;
  verify?: boolean;
  confirm?: boolean;
  exclude?: string[];
  dryRun?: boolean;
  [key: string]: unknown;
}

export interface ResolvedLocalSource {
  /** Absolute path; directories carry a trailing slash (rsync "contents-of" semantics). */
  path: string;
  /** Absolute path without any trailing slash (for SFTP / stat / basename use). */
  rawPath: string;
  /** True if the path points at a file (not a directory). */
  isFile: boolean;
}

export function withTrailingSlash(p: string): string {
  return p.endsWith('/') ? p : `${p}/`;
}

export interface SyncRemotePaths {
  /** rsync destination path. File mode: no trailing slash. Dir mode: trailing slash. */
  remotePath: string;
  /** SFTP-relative path. File mode: subpath as given (no slash). Dir mode: subpath with trailing slash, or '.' when undefined. */
  sftpRemotePath: string;
}

export function buildSyncRemotePaths(
  baseRemotePath: string,
  remoteSubPath: string | undefined,
  isFile: boolean
): SyncRemotePaths {
  if (isFile) {
    const sub = remoteSubPath ?? '';
    return {
      remotePath: `${baseRemotePath}/${sub}`,
      sftpRemotePath: sub,
    };
  }
  return {
    remotePath: remoteSubPath ? `${baseRemotePath}/${remoteSubPath}/` : `${baseRemotePath}/`,
    sftpRemotePath: remoteSubPath ? `${remoteSubPath}/` : '.',
  };
}

export function resolveUploadLocalPaths(local: string[] | undefined): ResolvedLocalSource[] {
  const inputs = local && local.length > 0 ? local : [process.cwd()];
  return inputs.map((p) => {
    const rawPath = resolve(p);
    if (!existsSync(rawPath)) {
      throw new Error(t('errors.sync.localPathNotFound', { path: rawPath }));
    }
    const isFile = statSync(rawPath).isFile();
    const path = isFile ? rawPath : withTrailingSlash(rawPath);
    return { path, rawPath, isFile };
  });
}

/**
 * Validate download options: remote/remote-file exclusivity, mirror+file guard,
 * and local-is-directory check when pulling a single file.
 */
export function validateDownloadOptions(options: SyncDownloadOptions): {
  localPath: string;
  isFileMode: boolean;
} {
  if (options.remote && options.remoteFile) {
    throw new Error(t('errors.sync.remoteAndRemoteFile'));
  }
  if (options.remoteFile && options.mirror) {
    throw new Error(t('errors.sync.mirrorWithFile'));
  }
  const localPath = resolve(options.local ?? process.cwd());
  if (options.remoteFile) {
    if (!existsSync(localPath) || !statSync(localPath).isDirectory()) {
      throw new Error(t('errors.sync.remoteFileLocalNotDir', { path: localPath }));
    }
  }
  return { localPath, isFileMode: Boolean(options.remoteFile) };
}

/**
 * Validate upload options: remote/remote-file exclusivity, mirror+file guards,
 * and require a single-file local source when --remote-file is set.
 *
 * Returns the resolved local sources alongside `isFileMode` so callers can
 * thread both into rsync source construction and the SFTP dispatcher.
 */
export function validateUploadOptions(options: SyncUploadOptions): {
  isFileMode: boolean;
  sources: ResolvedLocalSource[];
} {
  if (options.remote && options.remoteFile) {
    throw new Error(t('errors.sync.remoteAndRemoteFile'));
  }
  if (options.remoteFile && options.mirror) {
    throw new Error(t('errors.sync.mirrorWithFile'));
  }
  const sources = resolveUploadLocalPaths(options.local);
  if (options.mirror && sources.some((s) => s.isFile)) {
    throw new Error(t('errors.sync.mirrorWithFile'));
  }
  if (options.remoteFile) {
    if (sources.length !== 1 || !sources[0].isFile) {
      throw new Error(t('errors.sync.remoteFileRequiresSingleFile'));
    }
  }
  return { isFileMode: Boolean(options.remoteFile), sources };
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
}

export function hasNoChanges(changes: RsyncChanges): boolean {
  return (
    changes.newFiles.length === 0 &&
    changes.modifiedFiles.length === 0 &&
    changes.deletedFiles.length === 0
  );
}

export async function interactiveConfirmation(changes: RsyncChanges): Promise<boolean> {
  const readline = await import('node:readline');
  process.stdout.write(`${formatChangesSummary(changes)}\n`);

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const ask = (): Promise<string> =>
    new Promise((resolveAnswer) => {
      rl.question(t('prompts.syncConfirm'), resolveAnswer);
    });

  let answered = false;
  let proceed = false;

  while (!answered) {
    const answer = (await ask()).toLowerCase().trim();
    switch (answer) {
      case 'y':
      case 'yes':
        proceed = true;
        answered = true;
        break;
      case 'n':
      case 'no':
      case '':
        proceed = false;
        answered = true;
        break;
      case 'd':
      case 'details':
        process.stdout.write(
          `${formatDetailedChanges(changes, {
            colorNew: chalk.green,
            colorModified: chalk.yellow,
            colorDeleted: chalk.red,
            colorDim: chalk.dim,
          })}\n`
        );
        process.stdout.write(`\n${formatChangesSummary(changes)}\n`);
        break;
      default:
        process.stdout.write(`${t('prompts.syncConfirmHelp')}\n`);
    }
  }

  rl.close();
  return proceed;
}

export async function handleConfirmMode(
  rsyncOptions: RsyncExecutorOptions,
  options: { confirm?: boolean; dryRun?: boolean }
): Promise<boolean> {
  if (!options.confirm || options.dryRun) return true;

  process.stdout.write(`${t('commands.sync.previewingChanges')}\n`);

  const changes = await getRsyncPreview(rsyncOptions);

  if (hasNoChanges(changes)) {
    process.stdout.write(`${t('commands.sync.noChanges')}\n`);
    return false;
  }

  const proceed = await interactiveConfirmation(changes);
  if (!proceed) {
    process.stdout.write(`${t('commands.sync.cancelled')}\n`);
    return false;
  }

  return true;
}

export async function handleDryRun(rsyncOptions: RsyncExecutorOptions): Promise<void> {
  process.stdout.write(`${t('commands.sync.dryRunHeader')}\n`);
  const changes = await getRsyncPreview(rsyncOptions);
  process.stdout.write(`${formatChangesSummary(changes)}\n`);
}
