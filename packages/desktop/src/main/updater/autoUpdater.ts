import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import log from 'electron-log';
import { autoUpdater, ProgressInfo, UpdateInfo } from 'electron-updater';
import { UPDATE_DEFAULTS } from '@rediacc/shared/config/defaults';
import { getConfigDir } from '@rediacc/shared/paths';
import { isCooldownExpired, UPDATE_STATE_DEFAULTS } from '@rediacc/shared/update';
import { readDesktopUpdateState, writeDesktopUpdateState } from './update-state';
import { sendToAllWindows } from '../ipc/updater';
import { desktopTelemetryService } from '../services/telemetry';

// Configure logging
autoUpdater.logger = log;
log.transports.file.level = 'info';

/**
 * Update configuration from updates.json in config dir.
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
 * Load update configuration from updates.json in config dir.
 * @returns The update configuration or null if not found/invalid
 */
function getUpdateConfig(): UpdateConfig | null {
  const configPath = join(getConfigDir(), 'updates.json');

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

/**
 * Check for updates only if the cooldown has expired.
 * Returns true if a check was initiated.
 */
async function checkWithCooldown(): Promise<boolean> {
  try {
    const state = await readDesktopUpdateState();
    if (!isCooldownExpired(state)) {
      desktopTelemetryService.trackEvent('desktop.update.check_skipped_cooldown', {
        consecutiveFailures: state.consecutiveFailures,
      });
      return false;
    }
    await autoUpdater.checkForUpdates();
    return true;
  } catch (err) {
    log.error('Failed to check for updates:', err);
    return false;
  }
}

/**
 * Record a successful check in state (reset failures).
 */
async function recordSuccessfulCheck(): Promise<void> {
  try {
    const state = await readDesktopUpdateState();
    state.lastCheckAt = new Date().toISOString();
    state.lastAttemptAt = new Date().toISOString();
    state.consecutiveFailures = 0;
    state.lastError = null;
    await writeDesktopUpdateState(state);
  } catch {
    /* best-effort */
  }
}

export function setupAutoUpdater(): void {
  // Check for custom update config from updates.json
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
    desktopTelemetryService.trackEvent('desktop.update.check_started');
  });

  autoUpdater.on('update-available', (info: UpdateInfo) => {
    log.info('Update available:', info.version);
    sendToAllWindows('updater:available', {
      version: info.version,
      releaseNotes: info.releaseNotes,
      releaseDate: info.releaseDate,
    });
    desktopTelemetryService.trackEvent('desktop.update.available', { version: info.version });
    void recordSuccessfulCheck();
  });

  autoUpdater.on('update-not-available', (info: UpdateInfo) => {
    log.info('No updates available, current version:', info.version);
    sendToAllWindows('updater:not-available', {
      version: info.version,
    });
    desktopTelemetryService.trackEvent('desktop.update.up_to_date', { version: info.version });
    void recordSuccessfulCheck();
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
    desktopTelemetryService.trackEvent('desktop.update.downloaded', { version: info.version });

    // Record downloaded version and reset install failures
    void (async () => {
      try {
        const state = await readDesktopUpdateState();
        state.lastDownloadedVersion = info.version;
        state.consecutiveInstallFailures = 0;
        await writeDesktopUpdateState(state);
      } catch {
        /* best-effort */
      }
    })();
  });

  autoUpdater.on('error', (error) => {
    log.error('Auto-updater error:', error);
    sendToAllWindows('updater:error', error.message);

    // Record failure in state
    void (async () => {
      try {
        const state = await readDesktopUpdateState();
        state.lastAttemptAt = new Date().toISOString();
        state.consecutiveFailures += 1;
        state.lastError = error.message;
        await writeDesktopUpdateState(state);
        desktopTelemetryService.trackEvent('desktop.update.error', {
          error: error.message,
          consecutiveFailures: state.consecutiveFailures,
        });
      } catch {
        /* best-effort */
      }
    })();
  });

  // Check for updates on startup (after 10 seconds delay)
  setTimeout(() => {
    void checkWithCooldown();
  }, 10000);

  // Check for updates every 4 hours
  setInterval(
    () => {
      void checkWithCooldown();
    },
    4 * 60 * 60 * 1000
  );
}

/**
 * Check install retry cap before allowing install.
 * Returns true if install is allowed, false if retries are exhausted.
 */
export async function checkInstallAllowed(): Promise<boolean> {
  try {
    const state = await readDesktopUpdateState();
    const attempts = state.consecutiveInstallFailures + 1;

    if (attempts > UPDATE_STATE_DEFAULTS.MAX_INSTALL_ATTEMPTS) {
      log.warn(
        `Install retry cap reached (${UPDATE_STATE_DEFAULTS.MAX_INSTALL_ATTEMPTS} attempts)`
      );
      desktopTelemetryService.trackEvent('desktop.update.install_skipped_max_retries', {
        version: state.lastDownloadedVersion,
        attempts: state.consecutiveInstallFailures,
      });
      return false;
    }

    // Increment install attempts
    state.consecutiveInstallFailures = attempts;
    await writeDesktopUpdateState(state);

    desktopTelemetryService.trackEvent('desktop.update.install_triggered', {
      version: state.lastDownloadedVersion,
    });
    return true;
  } catch {
    // On state read error, allow install
    return true;
  }
}
