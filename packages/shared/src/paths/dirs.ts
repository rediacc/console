import { execFileSync } from 'node:child_process';
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
 * Returns the effective home directory, resolving the invoking user's home
 * when running under sudo. Without this, `sudo rdc` would look for config
 * in /root/ instead of the user's home directory.
 *
 * When SUDO_USER is set and euid is 0 (running as root via sudo),
 * resolves the original user's home via getent (Linux) or dscl (macOS).
 */
export function getEffectiveHomedir(): string {
  const sudoUser = process.env.SUDO_USER;
  if (sudoUser && process.getuid?.() === 0) {
    try {
      if (process.platform === 'darwin') {
        const output = execFileSync(
          'dscl',
          ['.', '-read', `/Users/${sudoUser}`, 'NFSHomeDirectory'],
          { encoding: 'utf-8', timeout: 5000 }
        ).trim();
        const match = output.match(/NFSHomeDirectory:\s*(.+)/);
        if (match?.[1]) return match[1];
      } else {
        const entry = execFileSync('getent', ['passwd', sudoUser], {
          encoding: 'utf-8',
          timeout: 5000,
        }).trim();
        const home = entry.split(':')[5];
        if (home) return home;
      }
    } catch {
      // getent/dscl unavailable or user not found — fall through
    }
  }
  return homedir();
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
  const home = getEffectiveHomedir();
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
  const home = getEffectiveHomedir();
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
