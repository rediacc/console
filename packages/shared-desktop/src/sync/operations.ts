import { existsSync, mkdirSync } from 'fs';
import { ensureTrailingSlash, joinRemotePath } from './pathConverter.js';
import {
  executeRsync,
  getRsyncPreview,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from './rsync.js';
import { RepositoryConnection } from '../repository/connection.js';
import type { SyncMode, SyncResult } from '../types/index.js';

/**
 * Sync operation options
 */
export interface SyncOperationOptions {
  /** Local path */
  localPath: string;
  /** Repository connection */
  connection: RepositoryConnection;
  /** Sync mode: upload or download */
  mode: SyncMode;
  /** Delete files not in source */
  mirror?: boolean;
  /** Verify with checksums */
  verify?: boolean;
  /** Show preview before syncing */
  preview?: boolean;
  /** Callback for progress updates */
  onProgress?: (message: string) => void;
  /** Callback for rsync output */
  onOutput?: (data: string) => void;
}

/**
 * Sync operation result
 */
export interface SyncOperationResult extends SyncResult {
  /** Preview of changes (if preview was requested) */
  changes?: RsyncChanges;
  /** Whether user cancelled after preview */
  cancelled?: boolean;
}

/**
 * Performs an upload operation to a repository
 *
 * @param options - Upload options
 * @returns Sync result
 */
export async function uploadToRepository(
  options: SyncOperationOptions
): Promise<SyncOperationResult> {
  const { localPath, connection, mirror, verify, preview, onProgress, onOutput } = options;

  // Validate local path exists
  if (!existsSync(localPath)) {
    throw new Error(`Local path '${localPath}' does not exist`);
  }

  // Ensure connection is set up
  const setupResult = await connection.setupSSH();

  try {
    const sshOptions = setupResult.sshOptions.join(' ');
    const source = ensureTrailingSlash(localPath);
    const destination = joinRemotePath(
      connection.sshDestination,
      ensureTrailingSlash(connection.paths!.mountPath)
    );

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source,
      destination,
      mirror,
      verify,
      universalUser: connection.connection?.universalUser,
      onStdout: onOutput,
      onStderr: onOutput,
    };

    // Get preview if requested
    let changes: RsyncChanges | undefined;
    if (preview) {
      onProgress?.('Analyzing changes...');
      changes = await getRsyncPreview(rsyncOptions);
    }

    // Perform sync
    onProgress?.('Starting upload...');
    const result = await executeRsync(rsyncOptions);

    return {
      ...result,
      changes,
    };
  } finally {
    await connection.cleanupSSH();
  }
}

/**
 * Performs a download operation from a repository
 *
 * @param options - Download options
 * @returns Sync result
 */
export async function downloadFromRepository(
  options: SyncOperationOptions
): Promise<SyncOperationResult> {
  const { localPath, connection, mirror, verify, preview, onProgress, onOutput } = options;

  // Create local directory if it doesn't exist
  if (!existsSync(localPath)) {
    mkdirSync(localPath, { recursive: true });
  }

  // Ensure connection is set up
  const setupResult = await connection.setupSSH();

  try {
    const sshOptions = setupResult.sshOptions.join(' ');
    const source = joinRemotePath(
      connection.sshDestination,
      ensureTrailingSlash(connection.paths!.mountPath)
    );
    const destination = ensureTrailingSlash(localPath);

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source,
      destination,
      mirror,
      verify,
      universalUser: connection.connection?.universalUser,
      onStdout: onOutput,
      onStderr: onOutput,
    };

    // Get preview if requested
    let changes: RsyncChanges | undefined;
    if (preview) {
      onProgress?.('Analyzing changes...');
      changes = await getRsyncPreview(rsyncOptions);
    }

    // Perform sync
    onProgress?.('Starting download...');
    const result = await executeRsync(rsyncOptions);

    return {
      ...result,
      changes,
    };
  } finally {
    await connection.cleanupSSH();
  }
}

/**
 * High-level sync operation that handles both upload and download
 *
 * @param options - Sync options
 * @returns Sync result
 */
export async function syncRepository(options: SyncOperationOptions): Promise<SyncOperationResult> {
  if (options.mode === 'upload') {
    return uploadToRepository(options);
  }
  return downloadFromRepository(options);
}

/**
 * Gets a preview of sync changes without performing the sync
 *
 * @param options - Sync options
 * @returns Preview of changes
 */
export async function getSyncPreview(options: SyncOperationOptions): Promise<RsyncChanges> {
  const { localPath, connection, mode, mirror, verify } = options;

  // Validate paths
  if (mode === 'upload' && !existsSync(localPath)) {
    throw new Error(`Local path '${localPath}' does not exist`);
  }

  // Ensure connection is set up
  const setupResult = await connection.setupSSH();

  try {
    const sshOptions = setupResult.sshOptions.join(' ');
    const remotePath = ensureTrailingSlash(connection.paths!.mountPath);

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source:
        mode === 'upload'
          ? ensureTrailingSlash(localPath)
          : joinRemotePath(connection.sshDestination, remotePath),
      destination:
        mode === 'upload'
          ? joinRemotePath(connection.sshDestination, remotePath)
          : ensureTrailingSlash(localPath),
      mirror,
      verify,
      universalUser: connection.connection?.universalUser,
    };

    return await getRsyncPreview(rsyncOptions);
  } finally {
    await connection.cleanupSSH();
  }
}

/**
 * Formats changes summary for display
 *
 * @param changes - Rsync changes
 * @returns Formatted summary string
 */
export function formatChangesSummary(changes: RsyncChanges): string {
  const lines: string[] = [];

  if (changes.newFiles.length > 0) {
    lines.push(`New files: ${changes.newFiles.length}`);
  }
  if (changes.modifiedFiles.length > 0) {
    lines.push(`Modified files: ${changes.modifiedFiles.length}`);
  }
  if (changes.deletedFiles.length > 0) {
    lines.push(`Deleted files: ${changes.deletedFiles.length}`);
  }
  if (changes.newDirs.length > 0) {
    lines.push(`New directories: ${changes.newDirs.length}`);
  }

  const total =
    changes.newFiles.length +
    changes.modifiedFiles.length +
    changes.deletedFiles.length +
    changes.newDirs.length;

  if (total === 0) {
    return 'No changes - everything is in sync!';
  }

  lines.push(`Total changes: ${total}`);
  return lines.join('\n');
}

/**
 * Color function type for formatting output
 */
export type ColorFn = (text: string) => string;

/**
 * Options for formatting detailed changes
 */
export interface FormatDetailedChangesOptions {
  /** Maximum items to show per category (default: 10) */
  maxItems?: number;
  /** Color function for new files/dirs (green) */
  colorNew?: ColorFn;
  /** Color function for modified files (yellow) */
  colorModified?: ColorFn;
  /** Color function for deleted files (red) */
  colorDeleted?: ColorFn;
  /** Color function for "... and X more" text (dim/gray) */
  colorDim?: ColorFn;
}

/**
 * Formats detailed changes for display (matching Python CLI behavior)
 * Shows first 10 items of each category with "... and X more" if truncated
 *
 * @param changes - Rsync changes
 * @param options - Formatting options including color functions
 * @returns Detailed formatted string
 */
export function formatDetailedChanges(
  changes: RsyncChanges,
  options: FormatDetailedChangesOptions = {}
): string {
  const {
    maxItems = 10,
    colorNew = (t: string) => t,
    colorModified = (t: string) => t,
    colorDeleted = (t: string) => t,
    colorDim = (t: string) => t,
  } = options;

  const sections: string[] = [];

  const formatSection = (
    title: string,
    items: string[],
    prefix: string,
    colorFn: ColorFn
  ): void => {
    if (items.length === 0) return;

    const lines: string[] = [`\n${title}:`];
    const displayItems = items.slice(0, maxItems);

    for (const item of displayItems) {
      lines.push(`  ${colorFn(prefix)} ${item}`);
    }

    if (items.length > maxItems) {
      lines.push(colorDim(`  ... and ${items.length - maxItems} more`));
    }

    sections.push(lines.join('\n'));
  };

  formatSection('New files', changes.newFiles, '+', colorNew);
  formatSection('Modified files', changes.modifiedFiles, '~', colorModified);
  formatSection('Deleted files', changes.deletedFiles, '-', colorDeleted);
  formatSection('New directories', changes.newDirs, '/', colorNew);

  if (sections.length === 0) {
    return 'No changes to display.';
  }

  return sections.join('\n');
}
