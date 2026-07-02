/**
 * VS Code Remote SSH Integration Types
 */

/**
 * VS Code executable information
 */
export interface VSCodeInfo {
  path: string;
  version?: string;
  isInsiders: boolean;
  /** Whether this VS Code installation is inside WSL */
  isWSL?: boolean;
  /** WSL distribution name (only set if isWSL is true) */
  wslDistro?: string;
}

/**
 * Result of scanning for all VS Code installations
 */
export interface VSCodeInstallations {
  /** VS Code installed on Windows (native) */
  windows: VSCodeInfo | null;
  /** VS Code installed inside WSL */
  wsl: VSCodeInfo | null;
}

/**
 * User preference for which VS Code to use when both are available
 */
export type VSCodePreference = 'windows' | 'wsl' | null;

/**
 * SSH config entry for VS Code
 */
export interface SSHConfigEntry {
  host: string;
  hostname: string;
  user: string;
  port: number;
  identityFile: string;
  userKnownHostsFile: string;
  remoteCommand?: string;
  requestTTY?: 'yes' | 'no' | 'force';
  /** Environment variables to set on the remote (SetEnv directives) */
  setEnv?: Record<string, string>;
  /** Seconds between keepalive messages (default: 60) */
  serverAliveInterval?: number;
  /** Number of missed keepalives before disconnect (default: 3) */
  serverAliveCountMax?: number;
}

/**
 * VS Code launch options
 */
export interface VSCodeLaunchOptions {
  folderPath?: string;
  newWindow?: boolean;
  waitForClose?: boolean;
}

/**
 * VS Code settings to configure
 */
export interface VSCodeRemoteSettings {
  'remote.SSH.enableRemoteCommand': boolean;
  'remote.SSH.configFile': string;
  'remote.SSH.serverInstallPath'?: Record<string, string>;
  'remote.SSH.useLocalServer'?: boolean;
  'remote.SSH.showLoginTerminal'?: boolean;
}

/**
 * Key persistence paths
 */
export interface KeyPersistencePaths {
  keyPath: string;
  knownHostsPath: string;
}
