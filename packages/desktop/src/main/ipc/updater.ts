import { BrowserWindow, ipcMain } from 'electron';
import { autoUpdater } from 'electron-updater';
import { isCooldownExpired } from '@rediacc/shared/update';
import { checkInstallAllowed } from '../updater/autoUpdater';
import { readDesktopUpdateState } from '../updater/update-state';

export function registerUpdaterHandlers(): void {
  ipcMain.handle('updater:checkForUpdates', async () => {
    try {
      return await autoUpdater.checkForUpdates();
    } catch (error) {
      console.error('Failed to check for updates:', error);
      throw error;
    }
  });

  ipcMain.handle('updater:downloadUpdate', async () => {
    try {
      return await autoUpdater.downloadUpdate();
    } catch (error) {
      console.error('Failed to download update:', error);
      throw error;
    }
  });

  ipcMain.handle('updater:installUpdate', async () => {
    const allowed = await checkInstallAllowed();
    if (!allowed) {
      throw new Error('Install retry cap reached. Please restart the application or download a fresh update.');
    }
    // Quit and install immediately, but allow app to restart
    autoUpdater.quitAndInstall(false, true);
  });

  ipcMain.handle('updater:getVersion', () => {
    return autoUpdater.currentVersion.version;
  });

  ipcMain.handle('updater:getStatus', async () => {
    const state = await readDesktopUpdateState();
    return {
      ...state,
      currentVersion: autoUpdater.currentVersion.version,
      cooldownExpired: isCooldownExpired(state),
    };
  });
}

// Helper to send events to all windows
export function sendToAllWindows(channel: string, ...args: unknown[]): void {
  const windows = BrowserWindow.getAllWindows();
  windows.forEach((win) => {
    if (!win.isDestroyed()) {
      win.webContents.send(channel, ...args);
    }
  });
}
