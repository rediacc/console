import { ipcMain, app } from 'electron';
import { registerRsyncHandlers, abortAllRsyncOperations } from './rsync';
import { registerSafeStorageHandlers } from './safeStorage';
import { registerSftpHandlers, cleanupAllSftpSessions } from './sftp';
import { registerTerminalHandlers, cleanupAllTerminalSessions } from './terminal';
import { registerUpdaterHandlers } from './updater';

export function registerIpcHandlers(): void {
  // Register safe storage handlers
  registerSafeStorageHandlers();

  // Register auto-updater handlers
  registerUpdaterHandlers();

  // Register terminal handlers (SSH PTY)
  registerTerminalHandlers();

  // Register rsync handlers (file sync)
  registerRsyncHandlers();

  // Register SFTP handlers (file browser)
  registerSftpHandlers();

  // App info handlers
  ipcMain.handle('app:getVersion', () => app.getVersion());
  ipcMain.handle('app:getPlatform', () => process.platform);
  ipcMain.handle('app:getArch', () => process.arch);
  ipcMain.handle('app:getUserDataPath', () => app.getPath('userData'));
}

/**
 * Cleanup all IPC resources (call on app quit)
 */
export async function cleanupIpcHandlers(): Promise<void> {
  await cleanupAllTerminalSessions();
  cleanupAllSftpSessions();
  abortAllRsyncOperations();
}
