/**
 * Type definitions for Electron API exposed via contextBridge
 * These types mirror the implementation in packages/desktop/src/preload/index.ts
 */

// Terminal types
export interface TerminalConnectParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  cols?: number;
  rows?: number;
  env?: Record<string, string>;
}

export interface TerminalConnectResult {
  sessionId: string;
}

// Rsync types
export interface RsyncExecutorOptions {
  sshOptions: string;
  source: string;
  destination: string;
  mirror?: boolean;
  verify?: boolean;
  exclude?: string[];
  universalUser?: string;
}

export interface RsyncProgress {
  percentage?: number;
  currentFile?: string;
  speed?: string;
  bytesTransferred?: number;
  totalBytes?: number;
}

export interface RsyncResult {
  success: boolean;
  filesTransferred: number;
  bytesTransferred: number;
  duration: number;
  errors: string[];
}

export interface RsyncChanges {
  newFiles: string[];
  modifiedFiles: string[];
  deletedFiles: string[];
}

// Protocol types
export interface ParsedProtocolUrl {
  token: string;
  teamName: string;
  machineName: string;
  repositoryName?: string;
  action: string;
  params: Record<string, string>;
}

// SFTP types
export interface SFTPConnectParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  passphrase?: string;
}

export interface SFTPConnectResult {
  sessionId: string;
}

export interface SFTPFileInfo {
  name: string;
  path: string;
  isDirectory: boolean;
  isFile: boolean;
  isSymlink: boolean;
  size: number;
  modifiedAt: Date;
  permissions: string;
  owner?: string;
  group?: string;
}

export interface SFTPSessionInfo {
  host: string;
  user: string;
  createdAt: number;
}

// Update types
export interface UpdateInfo {
  version: string;
  releaseNotes?: string | null;
  releaseDate?: string;
}

export interface UpdateProgress {
  percent: number;
  bytesPerSecond: number;
  transferred: number;
  total: number;
}

// VSCode types
export interface VSCodeLaunchOptions {
  teamName: string;
  machineName: string;
  repositoryName?: string;
  host: string;
  port?: number;
  user: string;
  privateKey: string;
  known_hosts?: string;
  remotePath: string;
  datastore?: string;
  newWindow?: boolean;
  /** Preferred VS Code type when both Windows and WSL are available */
  preferredType?: 'windows' | 'wsl';
}

export interface VSCodeLaunchResult {
  success: boolean;
  error?: string;
  connectionName?: string;
}

export interface VSCodeInfo {
  path: string;
  version?: string;
  isInsiders: boolean;
  /** Whether this VS Code installation is inside WSL */
  isWSL?: boolean;
  /** WSL distribution name (only set if isWSL is true) */
  wslDistro?: string;
}

export interface VSCodeInstallations {
  /** VS Code installed on Windows (native) */
  windows: VSCodeInfo | null;
  /** VS Code installed inside WSL */
  wsl: VSCodeInfo | null;
}

export type VSCodePreference = 'windows' | 'wsl' | null;

// Container types
export interface ContainerExecParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  containerId: string;
  containerName?: string;
  command?: string;
  cols?: number;
  rows?: number;
}

export interface ContainerLogsParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  containerId: string;
  follow?: boolean;
  tail?: number;
  cols?: number;
  rows?: number;
}

export interface ContainerStatsParams {
  host: string;
  user: string;
  port?: number;
  privateKey: string;
  known_hosts?: string;
  containerId: string;
  cols?: number;
  rows?: number;
}

export interface ContainerSessionResult {
  sessionId: string;
}

// Window types
export interface PopoutWindowOptions {
  type: 'terminal' | 'container';
  sessionId: string;
  title?: string;
  width?: number;
  height?: number;
  machineName?: string;
  repositoryName?: string;
  containerId?: string;
  containerName?: string;
  containerSessionType?: 'exec' | 'logs' | 'stats';
}

export interface PopoutWindowResult {
  success: boolean;
  windowId?: number;
  error?: string;
}

// Full Electron API interface
export interface ElectronAPI {
  safeStorage: {
    isAvailable: () => Promise<boolean>;
    encrypt: (data: string) => Promise<string>;
    decrypt: (encryptedData: string) => Promise<string>;
  };
  storage: {
    set: (key: string, value: string) => Promise<void>;
    get: (key: string) => Promise<string | null>;
    remove: (key: string) => Promise<void>;
    clear: () => Promise<void>;
    keys: () => Promise<string[]>;
  };
  updater: {
    checkForUpdates: () => Promise<void>;
    downloadUpdate: () => Promise<void>;
    installUpdate: () => Promise<void>;
    getVersion: () => Promise<string>;
    onChecking: (callback: () => void) => () => void;
    onAvailable: (callback: (info: UpdateInfo) => void) => () => void;
    onNotAvailable: (callback: (info: UpdateInfo) => void) => () => void;
    onDownloaded: (callback: (info: UpdateInfo) => void) => () => void;
    onProgress: (callback: (progress: UpdateProgress) => void) => () => void;
    onError: (callback: (error: string) => void) => () => void;
  };
  app: {
    getVersion: () => Promise<string>;
    getPlatform: () => Promise<string>;
    getArch: () => Promise<string>;
  };
  terminal: {
    connect: (params: TerminalConnectParams) => Promise<TerminalConnectResult>;
    write: (sessionId: string, data: string) => void;
    resize: (sessionId: string, cols: number, rows: number) => void;
    close: (sessionId: string) => Promise<void>;
    onData: (sessionId: string, callback: (data: string) => void) => () => void;
    onExit: (sessionId: string, callback: (code: number) => void) => () => void;
    getSessionCount: () => Promise<number>;
    transfer: (sessionId: string) => Promise<{ success: boolean; error?: string; buffer?: string }>;
  };
  rsync: {
    execute: (options: RsyncExecutorOptions) => Promise<RsyncResult>;
    preview: (options: RsyncExecutorOptions) => Promise<RsyncChanges>;
    formatSummary: (changes: RsyncChanges) => Promise<string>;
    abort: (operationId: string) => Promise<boolean>;
    onProgress: (
      callback: (data: { operationId: string; progress: RsyncProgress }) => void
    ) => () => void;
    getActiveCount: () => Promise<number>;
  };
  protocol: {
    onOpen: (callback: (parsed: ParsedProtocolUrl) => void) => () => void;
  };
  sftp: {
    connect: (params: SFTPConnectParams) => Promise<SFTPConnectResult>;
    listDirectory: (sessionId: string, path: string) => Promise<SFTPFileInfo[]>;
    readFile: (sessionId: string, path: string) => Promise<ArrayBuffer>;
    writeFile: (sessionId: string, path: string, data: ArrayBuffer) => Promise<void>;
    mkdir: (sessionId: string, path: string) => Promise<void>;
    delete: (sessionId: string, path: string, isDirectory: boolean) => Promise<void>;
    deleteRecursive: (sessionId: string, path: string) => Promise<void>;
    rename: (sessionId: string, oldPath: string, newPath: string) => Promise<void>;
    stat: (sessionId: string, path: string) => Promise<SFTPFileInfo>;
    exists: (sessionId: string, path: string) => Promise<boolean>;
    close: (sessionId: string) => Promise<void>;
    getSessionCount: () => Promise<number>;
    getSessionInfo: (sessionId: string) => Promise<SFTPSessionInfo | null>;
  };
  vscode: {
    launch: (options: VSCodeLaunchOptions) => Promise<VSCodeLaunchResult>;
    isAvailable: () => Promise<boolean>;
    hasRemoteSSH: () => Promise<boolean>;
    getInstallations: () => Promise<VSCodeInstallations>;
    getPreference: () => Promise<VSCodePreference>;
    setPreference: (preference: VSCodePreference) => Promise<void>;
  };
  window: {
    openPopout: (options: PopoutWindowOptions) => Promise<PopoutWindowResult>;
    closePopout: (windowId: number) => Promise<boolean>;
    getPopoutCount: () => Promise<number>;
  };
  container: {
    exec: (params: ContainerExecParams) => Promise<ContainerSessionResult>;
    logs: (params: ContainerLogsParams) => Promise<ContainerSessionResult>;
    stats: (params: ContainerStatsParams) => Promise<ContainerSessionResult>;
    write: (sessionId: string, data: string) => void;
    resize: (sessionId: string, cols: number, rows: number) => void;
    close: (sessionId: string) => Promise<void>;
    onData: (sessionId: string, callback: (data: string) => void) => () => void;
    onExit: (sessionId: string, callback: (code: number) => void) => () => void;
    getSessionCount: () => Promise<number>;
    transfer: (sessionId: string) => Promise<{ success: boolean; error?: string; buffer?: string }>;
  };
}

// Extend Window interface
declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

/**
 * Check if running in Electron environment
 */
export function isElectron(): boolean {
  return typeof window !== 'undefined' && typeof window.electronAPI !== 'undefined';
}

/**
 * Get the Electron API (throws if not available)
 */
export function getElectronAPI(): ElectronAPI {
  if (!window.electronAPI) {
    throw new Error('Electron API is not available. Are you running in the Electron app?');
  }
  return window.electronAPI;
}
