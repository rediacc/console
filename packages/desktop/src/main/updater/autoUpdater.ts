import log from 'electron-log';
import { autoUpdater, UpdateInfo, ProgressInfo } from 'electron-updater';
import { sendToAllWindows } from '../ipc/updater';

// Configure logging
autoUpdater.logger = log;
log.transports.file.level = 'info';

export function setupAutoUpdater(): void {
  // Configure update settings
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowDowngrade = false;

  // Event handlers
  autoUpdater.on('checking-for-update', () => {
    log.info('Checking for updates...');
    sendToAllWindows('updater:checking');
  });

  autoUpdater.on('update-available', (info: UpdateInfo) => {
    log.info('Update available:', info.version);
    sendToAllWindows('updater:available', {
      version: info.version,
      releaseNotes: info.releaseNotes,
      releaseDate: info.releaseDate,
    });
  });

  autoUpdater.on('update-not-available', (info: UpdateInfo) => {
    log.info('No updates available, current version:', info.version);
    sendToAllWindows('updater:not-available', {
      version: info.version,
    });
  });

  autoUpdater.on('download-progress', (progress: ProgressInfo) => {
    log.info(`Download progress: ${progress.percent.toFixed(1)}%`);
    sendToAllWindows('updater:progress', {
      percent: progress.percent,
      bytesPerSecond: progress.bytesPerSecond,
      transferred: progress.transferred,
      total: progress.total,
    });
  });

  autoUpdater.on('update-downloaded', (info: UpdateInfo) => {
    log.info('Update downloaded:', info.version);
    sendToAllWindows('updater:downloaded', {
      version: info.version,
      releaseNotes: info.releaseNotes,
    });
  });

  autoUpdater.on('error', (error) => {
    log.error('Auto-updater error:', error);
    sendToAllWindows('updater:error', error.message);
  });

  // Check for updates on startup (after 10 seconds delay)
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err: unknown) => {
      log.error('Failed to check for updates on startup:', err);
    });
  }, 10000);

  // Check for updates every 4 hours
  setInterval(
    () => {
      autoUpdater.checkForUpdates().catch((err: unknown) => {
        log.error('Failed to check for updates (scheduled):', err);
      });
    },
    4 * 60 * 60 * 1000
  );
}
