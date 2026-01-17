import {
  executeRsync,
  formatChangesSummary,
  getRsyncPreview,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from '@rediacc/shared-desktop/sync';
import { ipcMain } from 'electron';
import type { SyncProgress, SyncResult } from '@rediacc/shared-desktop';

/**
 * Active rsync operations for tracking
 */
const activeOperations = new Map<string, { abort: () => void }>();

/**
 * Generate unique operation ID
 */
let operationCounter = 0;
function generateOperationId(): string {
  return `rsync-${Date.now()}-${++operationCounter}`;
}

/**
 * Registers rsync IPC handlers
 */
export function registerRsyncHandlers(): void {
  // Execute rsync operation
  ipcMain.handle(
    'rsync:execute',
    async (event, options: RsyncExecutorOptions): Promise<SyncResult> => {
      const operationId = generateOperationId();
      // Use object to track abort status so it can be mutated from abort callback
      const state = { aborted: false };

      // Set up abort controller
      activeOperations.set(operationId, {
        abort: () => {
          state.aborted = true;
        },
      });

      // Add progress callback
      const optionsWithProgress: RsyncExecutorOptions = {
        ...options,
        onProgress: (progress: SyncProgress) => {
          if (!event.sender.isDestroyed()) {
            event.sender.send('rsync:progress', { operationId, progress });
          }
        },
      };

      try {
        const result = await executeRsync(optionsWithProgress);

        if (state.aborted) {
          return {
            success: false,
            filesTransferred: 0,
            bytesTransferred: 0,
            duration: 0,
            errors: ['Operation aborted'],
          };
        }

        return result;
      } finally {
        activeOperations.delete(operationId);
      }
    }
  );

  // Get rsync preview (dry-run)
  ipcMain.handle(
    'rsync:preview',
    (_event, options: RsyncExecutorOptions): Promise<RsyncChanges> => {
      return getRsyncPreview(options);
    }
  );

  // Format changes summary
  ipcMain.handle('rsync:formatSummary', (_event, changes: RsyncChanges): string => {
    return formatChangesSummary(changes);
  });

  // Abort an active rsync operation
  ipcMain.handle('rsync:abort', (_event, operationId: string): boolean => {
    const operation = activeOperations.get(operationId);
    if (operation) {
      operation.abort();
      activeOperations.delete(operationId);
      return true;
    }
    return false;
  });

  // Get count of active operations
  ipcMain.handle('rsync:getActiveCount', (): number => {
    return activeOperations.size;
  });
}

/**
 * Cleanup all active rsync operations (call on app quit)
 */
export function abortAllRsyncOperations(): void {
  for (const [id, operation] of activeOperations) {
    operation.abort();
    activeOperations.delete(id);
  }
}
