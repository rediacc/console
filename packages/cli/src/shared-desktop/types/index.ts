/**
 * Shared types for desktop-specific functionality
 * Used by CLI and Electron main process
 */

// SSH Types
export interface SSHCredentials {
  host: string;
  port: number;
  username: string;
  privateKey: string;
  passphrase?: string;
}

export interface SSHConnectionOptions {
  credentials: SSHCredentials;
  knownHostsPath?: string;
  strictHostKeyChecking?: boolean;
  connectTimeout?: number;
}

export interface SSHKeyInfo {
  privateKey: string;
  publicKey?: string;
  fingerprint?: string;
}

// Repository Types
export interface RepositoryConnectionOptions extends SSHConnectionOptions {
  repositoryName: string;
  containerName?: string;
  workingDirectory?: string;
  environmentVariables?: Record<string, string>;
}

// Sync Types
export type SyncMode = 'upload' | 'download';
export type SyncStrategy = 'incremental' | 'mirror' | 'verify';

export interface SyncOptions {
  mode: SyncMode;
  strategy: SyncStrategy;
  localPath: string;
  remotePath: string;
  exclude?: string[];
  include?: string[];
  dryRun?: boolean;
  delete?: boolean;
  verbose?: boolean;
}

export interface SyncProgress {
  currentFile: string;
  bytesTransferred: number;
  totalBytes: number;
  percentage: number;
  speed: string;
  eta: string;
}

export interface SyncResult {
  success: boolean;
  filesTransferred: number;
  bytesTransferred: number;
  errors: string[];
  duration: number;
}

// Terminal Types
export type TerminalType =
  | 'gnome-terminal'
  | 'konsole'
  | 'xfce4-terminal'
  | 'xterm'
  | 'mate-terminal'
  | 'terminator'
  | 'terminal-app' // macOS
  | 'iterm2'
  | 'windows-terminal'
  | 'powershell'
  | 'cmd'
  | 'mintty'
  | 'wsl';

export interface TerminalInfo {
  type: TerminalType;
  path: string;
  version?: string;
  detectedAt: number;
}

export interface TerminalLaunchOptions {
  command: string;
  title?: string;
  workingDirectory?: string;
  environmentVariables?: Record<string, string>;
  keepOpen?: boolean;
}

// Protocol Types
export type ProtocolAction = 'terminal' | 'sync' | 'browser' | 'desktop' | 'vscode' | 'plugin';

export interface ProtocolUrl {
  token: string;
  teamName: string;
  machineName: string;
  repositoryName?: string;
  action: ProtocolAction;
  params?: Record<string, string>;
}

// Platform Types
export type Platform = 'windows' | 'macos' | 'linux';
export type WindowsSubsystem = 'native' | 'wsl' | 'msys2' | 'cygwin';

export interface PlatformInfo {
  platform: Platform;
  isWSL: boolean;
  isMSYS2: boolean;
  windowsSubsystem?: WindowsSubsystem;
  homePath: string;
  tempPath: string;
  configPath: string;
}

// PTY Types
export interface PTYOptions {
  name?: string;
  cols?: number;
  rows?: number;
  cwd?: string;
  env?: Record<string, string>;
}

export interface PTYSession {
  sessionId: string;
  pid: number;
  write: (data: string) => void;
  resize: (cols: number, rows: number) => void;
  kill: (signal?: string) => void;
  onData: (callback: (data: string) => void) => () => void;
  onExit: (callback: (exitCode: number, signal?: number) => void) => () => void;
}

// SFTP Types
export interface FileInfo {
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

export interface SFTPSession {
  sessionId: string;
  listDirectory: (path: string) => Promise<FileInfo[]>;
  readFile: (path: string) => Promise<Buffer>;
  writeFile: (path: string, data: Buffer) => Promise<void>;
  mkdir: (path: string) => Promise<void>;
  delete: (path: string) => Promise<void>;
  rename: (oldPath: string, newPath: string) => Promise<void>;
  stat: (path: string) => Promise<FileInfo>;
  close: () => Promise<void>;
}

// MSYS2 Types
export interface MSYS2Paths {
  root: string;
  bin: string;
  rsync: string;
  ssh: string;
}

export interface MSYS2BundleInfo {
  version: string;
  binaries: string[];
  totalSize: number;
}
