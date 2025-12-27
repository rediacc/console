import { ipcMain, app } from 'electron';
import { registerSafeStorageHandlers } from './safeStorage';
import { registerUpdaterHandlers } from './updater';

export function registerIpcHandlers(): void {
  // Register safe storage handlers
  registerSafeStorageHandlers();

  // Register auto-updater handlers
  registerUpdaterHandlers();

  // App info handlers
  ipcMain.handle('app:getVersion', () => app.getVersion());
  ipcMain.handle('app:getPlatform', () => process.platform);
  ipcMain.handle('app:getArch', () => process.arch);
  ipcMain.handle('app:getUserDataPath', () => app.getPath('userData'));
}
