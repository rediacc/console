import { app, ipcMain } from 'electron';
import { cleanupAllContainerSessions, registerContainerHandlers } from './container';
import { abortAllRsyncOperations, registerRsyncHandlers } from './rsync';
import { registerSafeStorageHandlers } from './safeStorage';
import { cleanupAllSftpSessions, registerSftpHandlers } from './sftp';
import { cleanupAllTerminalSessions, registerTerminalHandlers } from './terminal';
import { registerUpdaterHandlers } from './updater';
import { registerVSCodeHandlers } from './vscode';
import { cleanupPopoutWindows, registerWindowHandlers } from './window';

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

  // Register VS Code handlers (remote SSH)
  registerVSCodeHandlers();

  // Register window handlers (popout windows)
  registerWindowHandlers();

  // Register container handlers (docker exec/logs/stats)
  registerContainerHandlers();

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
  await cleanupAllContainerSessions();
  cleanupAllSftpSessions();
  abortAllRsyncOperations();
  cleanupPopoutWindows();
}
