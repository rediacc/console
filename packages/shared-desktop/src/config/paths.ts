import { existsSync } from 'fs';
import { mkdir, readFile, writeFile } from 'fs/promises';
import { join } from 'path';
import { getConfigPath, getPlatform } from '../utils/platform.js';

/**
 * Rediacc configuration directory structure
 */
export interface ConfigPaths {
  /** Main config directory: ~/.rediacc */
  root: string;
  /** Cache directory: ~/.rediacc/cache */
  cache: string;
  /** Logs directory: ~/.rediacc/logs */
  logs: string;
  /** SSH keys directory: ~/.rediacc/keys */
  keys: string;
  /** Main config file: ~/.rediacc/config.json */
  configFile: string;
  /** Terminal cache file: ~/.rediacc/cache/terminal.json */
  terminalCache: string;
  /** Known hosts file: ~/.rediacc/known_hosts */
  knownHosts: string;
}

/**
 * Gets all configuration paths
 */
export function getConfigPaths(): ConfigPaths {
  const root = getConfigPath();
  const cache = join(root, 'cache');

  return {
    root,
    cache,
    logs: join(root, 'logs'),
    keys: join(root, 'keys'),
    configFile: join(root, 'config.json'),
    terminalCache: join(cache, 'terminal.json'),
    knownHosts: join(root, 'known_hosts'),
  };
}

/**
 * Ensures the config directory structure exists
 */
export async function ensureConfigDirs(): Promise<ConfigPaths> {
  const paths = getConfigPaths();

  // Create directories with secure permissions
  const dirs = [paths.root, paths.cache, paths.logs, paths.keys];

  for (const dir of dirs) {
    if (!existsSync(dir)) {
      await mkdir(dir, { recursive: true, mode: 0o700 });
    }
  }

  return paths;
}

/**
 * Configuration file structure
 */
export interface RediaccConfig {
  /** Current authentication token */
  token?: string;
  /** Next request token for rotation */
  nextToken?: string;
  /** API base URL */
  apiUrl?: string;
  /** Default team name */
  defaultTeam?: string;
  /** Development mode flag */
  devMode?: boolean;
  /** Last updated timestamp */
  updatedAt?: number;
}

/**
 * Reads the main configuration file
 */
export async function readConfig(): Promise<RediaccConfig> {
  const paths = getConfigPaths();

  if (!existsSync(paths.configFile)) {
    return {};
  }

  try {
    const content = await readFile(paths.configFile, 'utf8');
    return JSON.parse(content) as RediaccConfig;
  } catch {
    return {};
  }
}

/**
 * Writes to the main configuration file
 */
export async function writeConfig(config: RediaccConfig): Promise<void> {
  await ensureConfigDirs();
  const paths = getConfigPaths();

  const content = JSON.stringify(
    {
      ...config,
      updatedAt: Date.now(),
    },
    null,
    2
  );

  await writeFile(paths.configFile, content, { mode: 0o600 });
}

/**
 * Updates specific fields in the configuration
 */
export async function updateConfig(updates: Partial<RediaccConfig>): Promise<RediaccConfig> {
  const current = await readConfig();
  const updated = { ...current, ...updates };
  await writeConfig(updated);
  return updated;
}

/**
 * Gets platform-specific application data path
 */
export function getAppDataPath(): string {
  const platform = getPlatform();

  switch (platform) {
    case 'windows':
      return process.env.APPDATA ?? join(process.env.USERPROFILE ?? '', 'AppData', 'Roaming');
    case 'macos':
      return join(process.env.HOME ?? '', 'Library', 'Application Support');
    case 'linux':
    default:
      return process.env.XDG_CONFIG_HOME ?? join(process.env.HOME ?? '', '.config');
  }
}

/**
 * Gets the Electron app data directory
 */
export function getElectronAppDataPath(): string {
  return join(getAppDataPath(), 'Rediacc Console');
}

/**
 * Gets the logs directory for the current platform
 */
export function getLogsPath(): string {
  const platform = getPlatform();

  switch (platform) {
    case 'windows':
      return join(process.env.APPDATA ?? '', 'Rediacc Console', 'logs');
    case 'macos':
      return join(process.env.HOME ?? '', 'Library', 'Logs', 'Rediacc Console');
    case 'linux':
    default:
      return join(process.env.HOME ?? '', '.local', 'share', 'rediacc-console', 'logs');
  }
}
