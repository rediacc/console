import { contextBridge, type IpcRendererEvent, ipcRenderer } from 'electron';

// Type definitions matching electron-updater events
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
  isWSL?: boolean;
  wslDistro?: string;
}

export interface VSCodeInstallations {
  windows: VSCodeInfo | null;
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

// Type definitions for the exposed API
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

// Exposed API to renderer
const electronAPI: ElectronAPI = {
  // Safe Storage
  safeStorage: {
    isAvailable: (): Promise<boolean> => ipcRenderer.invoke('safeStorage:isAvailable'),
    encrypt: (data: string): Promise<string> => ipcRenderer.invoke('safeStorage:encrypt', data),
    decrypt: (encryptedData: string): Promise<string> =>
      ipcRenderer.invoke('safeStorage:decrypt', encryptedData),
  },

  // Persistent Storage (using safeStorage for encryption)
  storage: {
    set: (key: string, value: string): Promise<void> =>
      ipcRenderer.invoke('storage:set', key, value),
    get: (key: string): Promise<string | null> => ipcRenderer.invoke('storage:get', key),
    remove: (key: string): Promise<void> => ipcRenderer.invoke('storage:remove', key),
    clear: (): Promise<void> => ipcRenderer.invoke('storage:clear'),
    keys: (): Promise<string[]> => ipcRenderer.invoke('storage:keys'),
  },

  // Auto Updater
  updater: {
    checkForUpdates: (): Promise<void> => ipcRenderer.invoke('updater:checkForUpdates'),
    downloadUpdate: (): Promise<void> => ipcRenderer.invoke('updater:downloadUpdate'),
    installUpdate: (): Promise<void> => ipcRenderer.invoke('updater:installUpdate'),
    getVersion: (): Promise<string> => ipcRenderer.invoke('updater:getVersion'),
    onChecking: (callback: () => void) => {
      const handler = (): void => callback();
      ipcRenderer.on('updater:checking', handler);
      return () => ipcRenderer.removeListener('updater:checking', handler);
    },
    onAvailable: (callback: (info: UpdateInfo) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: UpdateInfo): void => callback(info);
      ipcRenderer.on('updater:available', handler);
      return () => ipcRenderer.removeListener('updater:available', handler);
    },
    onNotAvailable: (callback: (info: UpdateInfo) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: UpdateInfo): void => callback(info);
      ipcRenderer.on('updater:not-available', handler);
      return () => ipcRenderer.removeListener('updater:not-available', handler);
    },
    onDownloaded: (callback: (info: UpdateInfo) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: UpdateInfo): void => callback(info);
      ipcRenderer.on('updater:downloaded', handler);
      return () => ipcRenderer.removeListener('updater:downloaded', handler);
    },
    onProgress: (callback: (progress: UpdateProgress) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, progress: UpdateProgress): void =>
        callback(progress);
      ipcRenderer.on('updater:progress', handler);
      return () => ipcRenderer.removeListener('updater:progress', handler);
    },
    onError: (callback: (error: string) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, error: string): void => callback(error);
      ipcRenderer.on('updater:error', handler);
      return () => ipcRenderer.removeListener('updater:error', handler);
    },
  },

  // App Info
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('app:getVersion'),
    getPlatform: (): Promise<string> => ipcRenderer.invoke('app:getPlatform'),
    getArch: (): Promise<string> => ipcRenderer.invoke('app:getArch'),
  },

  // Terminal (SSH PTY)
  terminal: {
    connect: (params: TerminalConnectParams): Promise<TerminalConnectResult> =>
      ipcRenderer.invoke('terminal:connect', params),
    write: (sessionId: string, data: string): void =>
      ipcRenderer.send('terminal:write', sessionId, data),
    resize: (sessionId: string, cols: number, rows: number): void =>
      ipcRenderer.send('terminal:resize', sessionId, cols, rows),
    close: (sessionId: string): Promise<void> => ipcRenderer.invoke('terminal:close', sessionId),
    onData: (sessionId: string, callback: (data: string) => void): (() => void) => {
      const handler = (_event: IpcRendererEvent, data: string): void => callback(data);
      ipcRenderer.on(`terminal:data:${sessionId}`, handler);
      return () => ipcRenderer.removeListener(`terminal:data:${sessionId}`, handler);
    },
    onExit: (sessionId: string, callback: (code: number) => void): (() => void) => {
      const handler = (_event: IpcRendererEvent, code: number): void => callback(code);
      ipcRenderer.on(`terminal:exit:${sessionId}`, handler);
      return () => ipcRenderer.removeListener(`terminal:exit:${sessionId}`, handler);
    },
    getSessionCount: (): Promise<number> => ipcRenderer.invoke('terminal:getSessionCount'),
    transfer: (sessionId: string): Promise<{ success: boolean; error?: string }> =>
      ipcRenderer.invoke('terminal:transfer', sessionId),
  },

  // Rsync (File Sync)
  rsync: {
    execute: (options: RsyncExecutorOptions): Promise<RsyncResult> =>
      ipcRenderer.invoke('rsync:execute', options),
    preview: (options: RsyncExecutorOptions): Promise<RsyncChanges> =>
      ipcRenderer.invoke('rsync:preview', options),
    formatSummary: (changes: RsyncChanges): Promise<string> =>
      ipcRenderer.invoke('rsync:formatSummary', changes),
    abort: (operationId: string): Promise<boolean> =>
      ipcRenderer.invoke('rsync:abort', operationId),
    onProgress: (
      callback: (data: { operationId: string; progress: RsyncProgress }) => void
    ): (() => void) => {
      const handler = (
        _event: IpcRendererEvent,
        data: { operationId: string; progress: RsyncProgress }
      ): void => callback(data);
      ipcRenderer.on('rsync:progress', handler);
      return () => ipcRenderer.removeListener('rsync:progress', handler);
    },
    getActiveCount: (): Promise<number> => ipcRenderer.invoke('rsync:getActiveCount'),
  },

  // Protocol Handler
  protocol: {
    onOpen: (callback: (parsed: ParsedProtocolUrl) => void): (() => void) => {
      const handler = (_event: IpcRendererEvent, parsed: ParsedProtocolUrl): void =>
        callback(parsed);
      ipcRenderer.on('protocol:open', handler);
      return () => ipcRenderer.removeListener('protocol:open', handler);
    },
  },

  // SFTP (File Browser)
  sftp: {
    connect: (params: SFTPConnectParams): Promise<SFTPConnectResult> =>
      ipcRenderer.invoke('sftp:connect', params),
    listDirectory: (sessionId: string, path: string): Promise<SFTPFileInfo[]> =>
      ipcRenderer.invoke('sftp:listDirectory', sessionId, path),
    readFile: (sessionId: string, path: string): Promise<ArrayBuffer> =>
      ipcRenderer.invoke('sftp:readFile', sessionId, path),
    writeFile: (sessionId: string, path: string, data: ArrayBuffer): Promise<void> =>
      ipcRenderer.invoke('sftp:writeFile', sessionId, path, data),
    mkdir: (sessionId: string, path: string): Promise<void> =>
      ipcRenderer.invoke('sftp:mkdir', sessionId, path),
    delete: (sessionId: string, path: string, isDirectory: boolean): Promise<void> =>
      ipcRenderer.invoke('sftp:delete', sessionId, path, isDirectory),
    deleteRecursive: (sessionId: string, path: string): Promise<void> =>
      ipcRenderer.invoke('sftp:deleteRecursive', sessionId, path),
    rename: (sessionId: string, oldPath: string, newPath: string): Promise<void> =>
      ipcRenderer.invoke('sftp:rename', sessionId, oldPath, newPath),
    stat: (sessionId: string, path: string): Promise<SFTPFileInfo> =>
      ipcRenderer.invoke('sftp:stat', sessionId, path),
    exists: (sessionId: string, path: string): Promise<boolean> =>
      ipcRenderer.invoke('sftp:exists', sessionId, path),
    close: (sessionId: string): Promise<void> => ipcRenderer.invoke('sftp:close', sessionId),
    getSessionCount: (): Promise<number> => ipcRenderer.invoke('sftp:getSessionCount'),
    getSessionInfo: (sessionId: string): Promise<SFTPSessionInfo | null> =>
      ipcRenderer.invoke('sftp:getSessionInfo', sessionId),
  },

  // VS Code (Remote SSH)
  vscode: {
    launch: (options: VSCodeLaunchOptions): Promise<VSCodeLaunchResult> =>
      ipcRenderer.invoke('vscode:launch', options),
    isAvailable: (): Promise<boolean> => ipcRenderer.invoke('vscode:isAvailable'),
    hasRemoteSSH: (): Promise<boolean> => ipcRenderer.invoke('vscode:hasRemoteSSH'),
    getInstallations: (): Promise<VSCodeInstallations> =>
      ipcRenderer.invoke('vscode:getInstallations'),
    getPreference: (): Promise<VSCodePreference> => ipcRenderer.invoke('vscode:getPreference'),
    setPreference: (preference: VSCodePreference): Promise<void> =>
      ipcRenderer.invoke('vscode:setPreference', preference),
  },

  // Window Management (Popout)
  window: {
    openPopout: (options: PopoutWindowOptions): Promise<PopoutWindowResult> =>
      ipcRenderer.invoke('window:openPopout', options),
    closePopout: (windowId: number): Promise<boolean> =>
      ipcRenderer.invoke('window:closePopout', windowId),
    getPopoutCount: (): Promise<number> => ipcRenderer.invoke('window:getPopoutCount'),
  },

  // Container (Docker exec/logs/stats via SSH)
  container: {
    exec: (params: ContainerExecParams): Promise<ContainerSessionResult> =>
      ipcRenderer.invoke('container:exec', params),
    logs: (params: ContainerLogsParams): Promise<ContainerSessionResult> =>
      ipcRenderer.invoke('container:logs', params),
    stats: (params: ContainerStatsParams): Promise<ContainerSessionResult> =>
      ipcRenderer.invoke('container:stats', params),
    write: (sessionId: string, data: string): void =>
      ipcRenderer.send('container:write', sessionId, data),
    resize: (sessionId: string, cols: number, rows: number): void =>
      ipcRenderer.send('container:resize', sessionId, cols, rows),
    close: (sessionId: string): Promise<void> => ipcRenderer.invoke('container:close', sessionId),
    onData: (sessionId: string, callback: (data: string) => void): (() => void) => {
      const handler = (_event: IpcRendererEvent, data: string): void => callback(data);
      ipcRenderer.on(`container:data:${sessionId}`, handler);
      return () => ipcRenderer.removeListener(`container:data:${sessionId}`, handler);
    },
    onExit: (sessionId: string, callback: (code: number) => void): (() => void) => {
      const handler = (_event: IpcRendererEvent, code: number): void => callback(code);
      ipcRenderer.on(`container:exit:${sessionId}`, handler);
      return () => ipcRenderer.removeListener(`container:exit:${sessionId}`, handler);
    },
    getSessionCount: (): Promise<number> => ipcRenderer.invoke('container:getSessionCount'),
    transfer: (sessionId: string): Promise<{ success: boolean; error?: string; buffer?: string }> =>
      ipcRenderer.invoke('container:transfer', sessionId),
  },
};

// Expose to renderer via contextBridge
contextBridge.exposeInMainWorld('electronAPI', electronAPI);
