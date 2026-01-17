/**
 * Sync module - Rsync-based file synchronization
 * Ported from desktop/src/cli/commands/sync_main.py
 */

// High-level operations
export {
  type ColorFn,
  downloadFromRepository,
  type FormatDetailedChangesOptions,
  formatChangesSummary,
  formatDetailedChanges,
  getSyncPreview,
  type SyncOperationOptions,
  type SyncOperationResult,
  syncRepository,
  uploadToRepository,
} from './operations.js';
// Path conversion
export {
  convertLocalPathForRsync,
  ensureTrailingSlash,
  isRemotePath,
  joinRemotePath,
  parseRemotePath,
  prepareRsyncPaths,
  removeTrailingSlash,
} from './pathConverter.js';
// Rsync execution
export {
  buildRsyncArgs,
  executeRsync,
  getRsyncCommand,
  getRsyncPreview,
  getRsyncSSHCommand,
  parseRsyncChanges,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from './rsync.js';
