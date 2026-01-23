import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { app } from 'electron';
import log from 'electron-log';
import { autoUpdater, ProgressInfo, UpdateInfo } from 'electron-updater';
import { UPDATE_DEFAULTS } from '@rediacc/shared/config/defaults';
import { sendToAllWindows } from '../ipc/updater';

// Configure logging
autoUpdater.logger = log;
log.transports.file.level = 'info';

/**
 * Update configuration from ~/.rediacc/updates.json
 *
 * Example configuration:
 * {
 *   "feedUrl": "https://intranet.company.com/rediacc/updates",
 *   "provider": "generic",
 *   "channel": "latest"
 * }
 */
interface UpdateConfig {
  /** URL of the update server */
  feedUrl?: string;
  /** Update provider type */
  provider?: 'github' | 'generic' | 's3';
  /** Update channel */
  channel?: 'latest' | 'beta' | 'alpha';
}

/**
 * Load update configuration from ~/.rediacc/updates.json
 * @returns The update configuration or null if not found/invalid
 */
function getUpdateConfig(): UpdateConfig | null {
  const configPath = join(app.getPath('home'), '.rediacc', 'updates.json');

  if (existsSync(configPath)) {
    try {
      const content = readFileSync(configPath, 'utf-8');
      const config = JSON.parse(content) as UpdateConfig;
      log.info('Loaded update config from:', configPath);
      return config;
    } catch (error) {
      log.error('Failed to parse updates.json:', error);
    }
  }

  return null;
}

export function setupAutoUpdater(): void {
  // Check for custom update config from ~/.rediacc/updates.json
  const updateConfig = getUpdateConfig();

  if (updateConfig?.feedUrl) {
    log.info('Using custom update server:', updateConfig.feedUrl);
    autoUpdater.setFeedURL({
      provider: updateConfig.provider ?? UPDATE_DEFAULTS.PROVIDER,
      url: updateConfig.feedUrl,
    });

    if (updateConfig.channel) {
      autoUpdater.channel = updateConfig.channel;
    }
  }

  // Set platform-specific channel for consistent yml naming
  if (process.platform === 'win32' && !updateConfig?.channel) {
    autoUpdater.channel = 'latest-win';
  }

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
