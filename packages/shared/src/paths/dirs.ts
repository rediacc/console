import { homedir } from 'node:os';
import { join } from 'node:path';

export interface RediaccDirs {
  /** Config: rediacc.json, production.json, .credentials.json */
  config: string;
  /** State: update-state.json, update.lock */
  state: string;
  /** Cache: staged-update/ */
  cache: string;
}

/**
 * Returns platform-native directories for Rediacc data.
 *
 * Linux:   XDG spec ($XDG_CONFIG_HOME, $XDG_STATE_HOME, $XDG_CACHE_HOME)
 * macOS:   ~/Library/Application Support/rediacc  (config + state)
 *          ~/Library/Caches/rediacc               (cache)
 * Windows: %APPDATA%\rediacc                      (config)
 *          %LOCALAPPDATA%\rediacc                  (state)
 *          %LOCALAPPDATA%\rediacc\cache            (cache)
 */
export function getRediaccDirs(): RediaccDirs {
  switch (process.platform) {
    case 'darwin':
      return getDarwinDirs();
    case 'win32':
      return getWindowsDirs();
    default:
      return getLinuxDirs();
  }
}

function getLinuxDirs(): RediaccDirs {
  const home = homedir();
  return {
    config: process.env.XDG_CONFIG_HOME
      ? join(process.env.XDG_CONFIG_HOME, 'rediacc')
      : join(home, '.config', 'rediacc'),
    state: process.env.XDG_STATE_HOME
      ? join(process.env.XDG_STATE_HOME, 'rediacc')
      : join(home, '.local', 'state', 'rediacc'),
    cache: process.env.XDG_CACHE_HOME
      ? join(process.env.XDG_CACHE_HOME, 'rediacc')
      : join(home, '.cache', 'rediacc'),
  };
}

function getDarwinDirs(): RediaccDirs {
  const home = homedir();
  const appSupport = join(home, 'Library', 'Application Support', 'rediacc');
  return {
    config: appSupport,
    state: appSupport,
    cache: join(home, 'Library', 'Caches', 'rediacc'),
  };
}

function getWindowsDirs(): RediaccDirs {
  const appData = process.env.APPDATA ?? join(homedir(), 'AppData', 'Roaming');
  const localAppData = process.env.LOCALAPPDATA ?? join(homedir(), 'AppData', 'Local');
  return {
    config: join(appData, 'rediacc'),
    state: join(localAppData, 'rediacc'),
    cache: join(localAppData, 'rediacc', 'cache'),
  };
}

export function getConfigDir(): string {
  return getRediaccDirs().config;
}

export function getStateDir(): string {
  return getRediaccDirs().state;
}

export function getCacheDir(): string {
  return getRediaccDirs().cache;
}
