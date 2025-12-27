/**
 * Sync module - Rsync-based file synchronization
 * Ported from desktop/src/cli/commands/sync_main.py
 */

// Path conversion
export {
  isRemotePath,
  convertLocalPathForRsync,
  prepareRsyncPaths,
  ensureTrailingSlash,
  removeTrailingSlash,
  joinRemotePath,
  parseRemotePath,
} from './pathConverter.js';

// Rsync execution
export {
  getRsyncCommand,
  getRsyncSSHCommand,
  parseRsyncChanges,
  buildRsyncArgs,
  executeRsync,
  getRsyncPreview,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from './rsync.js';

// High-level operations
export {
  uploadToRepository,
  downloadFromRepository,
  syncRepository,
  getSyncPreview,
  formatChangesSummary,
  formatDetailedChanges,
  type ColorFn,
  type FormatDetailedChangesOptions,
  type SyncOperationOptions,
  type SyncOperationResult,
} from './operations.js';
