/**
 * Shared types for desktop-specific functionality
 * Used by CLI and Electron main process
 */

// Sync Types
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

export interface TerminalLaunchOptions {
  command: string;
  title?: string;
  workingDirectory?: string;
  environmentVariables?: Record<string, string>;
  keepOpen?: boolean;
}

// Platform Types
export type Platform = 'windows' | 'macos' | 'linux';

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
