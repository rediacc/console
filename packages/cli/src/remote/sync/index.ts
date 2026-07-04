/**
 * Sync module - Rsync-based file synchronization
 * Ported from desktop/src/cli/commands/sync_main.py
 */

// High-level operations
export { formatChangesSummary, formatDetailedChanges } from './operations.js';
// SFTP fallback (for systems without rsync)
export {
  sftpDownloadDirectory,
  sftpDownloadFile,
  sftpUploadFile,
  sftpUploadPaths,
} from './sftp-fallback.js';
export type { SftpUploadSource } from './sftp-fallback.js';
// Rsync execution
export {
  executeRsync,
  getRsyncCommand,
  getRsyncPreview,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from './rsync.js';
