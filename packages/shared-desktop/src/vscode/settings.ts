/**
 * VS Code Settings Management for Remote SSH
 * Manages settings.json configuration for Remote SSH support
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import {
  getPlatform,
  getSSHHome,
  getWindowsHomeInWSL,
  isWSL,
  wslPathToWindows,
} from '../utils/platform.js';
import type { VSCodeRemoteSettings } from './types.js';

/**
 * Gets WSL-aware VS Code settings paths
 * Returns array of possible paths, with Windows path first if available
 */
function getWSLVSCodeSettingsPaths(variant: 'Code' | 'Code - Insiders'): string[] {
  const paths: string[] = [];
  const home = process.env.HOME ?? '';

  // Try Windows user home first — VS Code on Windows reads from AppData
  const winHome = getWindowsHomeInWSL();
  if (winHome) {
    paths.push(join(winHome, 'AppData', 'Roaming', variant, 'User', 'settings.json'));
  }

  // Fallback to VS Code Server paths in WSL
  paths.push(join(home, '.vscode-server', 'data', 'Machine', 'settings.json'));
  paths.push(join(home, '.config', variant, 'User', 'settings.json'));

  return paths;
}

/**
 * Gets the VS Code settings.json path for the current platform
 */
export function getVSCodeSettingsPath(): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? '';
  const platform = getPlatform();

  // Handle WSL environment
  if (platform === 'linux' && isWSL()) {
    const paths = getWSLVSCodeSettingsPaths('Code');
    // Return first existing path, or first path as default
    for (const path of paths) {
      if (existsSync(path)) {
        return path;
      }
    }
    return paths[0] ?? join(home, '.config', 'Code', 'User', 'settings.json');
  }

  if (platform === 'windows') {
    const appData = process.env.APPDATA ?? join(home, 'AppData', 'Roaming');
    return join(appData, 'Code', 'User', 'settings.json');
  } else if (platform === 'macos') {
    return join(home, 'Library', 'Application Support', 'Code', 'User', 'settings.json');
  }
  // Linux
  return join(home, '.config', 'Code', 'User', 'settings.json');
}

/**
 * Gets the VS Code Insiders settings.json path for the current platform
 */
export function getVSCodeInsidersSettingsPath(): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? '';
  const platform = getPlatform();

  // Handle WSL environment
  if (platform === 'linux' && isWSL()) {
    const paths = getWSLVSCodeSettingsPaths('Code - Insiders');
    // Return first existing path, or first path as default
    for (const path of paths) {
      if (existsSync(path)) {
        return path;
      }
    }
    return paths[0] ?? join(home, '.config', 'Code - Insiders', 'User', 'settings.json');
  }

  if (platform === 'windows') {
    const appData = process.env.APPDATA ?? join(home, 'AppData', 'Roaming');
    return join(appData, 'Code - Insiders', 'User', 'settings.json');
  } else if (platform === 'macos') {
    return join(home, 'Library', 'Application Support', 'Code - Insiders', 'User', 'settings.json');
  }
  // Linux
  return join(home, '.config', 'Code - Insiders', 'User', 'settings.json');
}

/**
 * Reads and parses VS Code settings.json
 *
 * @param settingsPath - Path to settings.json
 * @returns Parsed settings object or empty object if file doesn't exist
 */
export function readVSCodeSettings(settingsPath?: string): Record<string, unknown> {
  const path = settingsPath ?? getVSCodeSettingsPath();

  if (!existsSync(path)) {
    return {};
  }

  try {
    const content = readFileSync(path, 'utf8');
    // Handle JSON with comments (JSONC) by stripping single-line comments
    const cleanContent = content.replaceAll(/^\s*\/\/.*$/gm, '');
    return JSON.parse(cleanContent);
  } catch {
    // If parsing fails, return empty object
    return {};
  }
}

/**
 * Writes settings to VS Code settings.json
 *
 * @param settings - Settings object to write
 * @param settingsPath - Path to settings.json
 */
export function writeVSCodeSettings(
  settings: Record<string, unknown>,
  settingsPath?: string
): void {
  const path = settingsPath ?? getVSCodeSettingsPath();
  const dir = dirname(path);

  // Ensure directory exists
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  // Write with pretty formatting
  writeFileSync(path, JSON.stringify(settings, null, 2), 'utf8');
}

/**
 * Default datastore path for VS Code server installation
 */
const DEFAULT_DATASTORE_PATH = '/mnt/rediacc';

/**
 * Gets the server install path from environment or default
 * Matches Python CLI's use of REDIACC_DATASTORE_USER env var
 *
 * @param datastorePath - Optional override path
 * @returns Server install path
 */
export function getServerInstallPath(datastorePath?: string): string {
  // Check environment variable first (matches Python behavior)
  const envPath = process.env.REDIACC_DATASTORE_USER ?? process.env.REDIACC_DATASTORE;

  // Use provided path, then env, then default
  const basePath = datastorePath ?? envPath ?? DEFAULT_DATASTORE_PATH;

  return `${basePath}/.vscode-server`;
}

/**
 * Gets the SSH config file path for VS Code settings.
 * In WSL, returns a Windows-format path so Windows SSH can resolve it.
 */
function getSSHConfigFileSetting(): string {
  const home = getSSHHome();
  const sshPath = join(home, '.ssh', 'config_rediacc');
  if (isWSL()) {
    return wslPathToWindows(sshPath).replaceAll('\\', '/');
  }
  return sshPath;
}

/**
 * Required Remote SSH settings for rediacc integration
 *
 * @param datastorePath - Optional datastore path override
 */
export function getRequiredRemoteSSHSettings(datastorePath?: string): VSCodeRemoteSettings {
  const serverPath = getServerInstallPath(datastorePath);

  return {
    'remote.SSH.enableRemoteCommand': true,
    'remote.SSH.configFile': getSSHConfigFileSetting(),
    'remote.SSH.serverInstallPath': {
      '*': serverPath,
    },
    'remote.SSH.useLocalServer': true,
    'remote.SSH.showLoginTerminal': true,
  };
}

/**
 * Sets server install path for a specific host
 * Allows per-connection configuration (matches Python CLI)
 *
 * @param host - SSH host name
 * @param serverPath - Server install path for this host
 * @param isInsiders - Whether to configure VS Code Insiders
 */
export function setHostServerInstallPath(
  host: string,
  serverPath: string,
  isInsiders = false
): void {
  const settingsPath = isInsiders ? getVSCodeInsidersSettingsPath() : getVSCodeSettingsPath();
  const settings = readVSCodeSettings(settingsPath);

  const existingInstallPaths = settings['remote.SSH.serverInstallPath'] as
    | Record<string, string>
    | undefined;
  const installPaths = existingInstallPaths ?? {};
  installPaths[host] = serverPath;
  settings['remote.SSH.serverInstallPath'] = installPaths;

  writeVSCodeSettings(settings, settingsPath);
}

/**
 * Checks if two values are objects that should be merged
 */
function areMergeableObjects(
  value: unknown,
  existingValue: unknown
): value is Record<string, unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof existingValue === 'object' &&
    existingValue !== null
  );
}

/**
 * Merges a single setting into existing settings
 * Returns true if a change was made
 */
function mergeSetting(
  existingSettings: Record<string, unknown>,
  key: string,
  value: unknown
): boolean {
  const existingValue = existingSettings[key];

  if (areMergeableObjects(value, existingValue)) {
    const existingObj = existingValue as Record<string, unknown>;
    const merged = { ...existingObj, ...value };
    if (JSON.stringify(merged) !== JSON.stringify(existingValue)) {
      existingSettings[key] = merged;
      return true;
    }
    return false;
  }

  if (existingValue !== value) {
    existingSettings[key] = value;
    return true;
  }
  return false;
}

/**
 * Configures VS Code settings for Remote SSH
 *
 * @param isInsiders - Whether to configure VS Code Insiders
 * @returns Object with status and any warnings
 */
export function configureVSCodeSettings(isInsiders = false): {
  success: boolean;
  settingsPath: string;
  changed: boolean;
  error?: string;
} {
  const settingsPath = isInsiders ? getVSCodeInsidersSettingsPath() : getVSCodeSettingsPath();

  try {
    const existingSettings = readVSCodeSettings(settingsPath);
    const requiredSettings = getRequiredRemoteSSHSettings();

    let changed = false;

    // Merge required settings
    for (const [key, value] of Object.entries(requiredSettings)) {
      if (mergeSetting(existingSettings, key, value)) {
        changed = true;
      }
    }

    if (changed) {
      writeVSCodeSettings(existingSettings, settingsPath);
    }

    return { success: true, settingsPath, changed };
  } catch (error) {
    return {
      success: false,
      settingsPath,
      changed: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Sets the remote platform to 'linux' for a host to avoid the platform prompt.
 *
 * @param host - SSH host name
 * @param isInsiders - Whether to configure VS Code Insiders
 */
export function setHostRemotePlatform(host: string, isInsiders = false): void {
  const settingsPath = isInsiders ? getVSCodeInsidersSettingsPath() : getVSCodeSettingsPath();
  const settings = readVSCodeSettings(settingsPath);

  const remotePlatform =
    (settings['remote.SSH.remotePlatform'] as Record<string, string> | undefined) ?? {};
  remotePlatform[host] = 'linux';
  settings['remote.SSH.remotePlatform'] = remotePlatform;
  writeVSCodeSettings(settings, settingsPath);
}

/**
 * Configures terminal profile for sudo user switching
 *
 * @param user - Universal user to switch to
 * @param isInsiders - Whether to configure VS Code Insiders
 */
export function configureTerminalProfile(user: string, isInsiders = false): void {
  const settingsPath = isInsiders ? getVSCodeInsidersSettingsPath() : getVSCodeSettingsPath();
  const settings = readVSCodeSettings(settingsPath);

  // Add terminal profile for the user
  const profileKey = 'terminal.integrated.profiles.linux';
  const existingProfiles = settings[profileKey] as Record<string, unknown> | undefined;
  const profiles = existingProfiles ?? {};

  profiles[`Rediacc (${user})`] = {
    path: '/bin/bash',
    args: ['-c', `sudo -i -u ${user} bash`],
  };

  settings[profileKey] = profiles;
  writeVSCodeSettings(settings, settingsPath);
}

/**
 * Checks if VS Code Remote SSH is configured for rediacc
 *
 * @param isInsiders - Whether to check VS Code Insiders
 * @returns Configuration status
 */
export function checkVSCodeConfiguration(isInsiders = false): {
  configured: boolean;
  settingsPath: string;
  missing: string[];
} {
  const settingsPath = isInsiders ? getVSCodeInsidersSettingsPath() : getVSCodeSettingsPath();
  const settings = readVSCodeSettings(settingsPath);
  const required = getRequiredRemoteSSHSettings();
  const missing: string[] = [];

  for (const [key, value] of Object.entries(required)) {
    if (!(key in settings)) {
      missing.push(key);
    } else if (typeof value === 'boolean' && settings[key] !== value) {
      missing.push(key);
    }
  }

  return {
    configured: missing.length === 0,
    settingsPath,
    missing,
  };
}
