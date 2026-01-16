/**
 * Minimal type definitions for Electron API in E2E tests.
 *
 * These types extend the global Window interface to include the electronAPI
 * that is exposed via Electron's contextBridge. The full type definitions
 * are in packages/web/src/types/electron.ts - these are minimal versions
 * for test assertions only.
 */

interface SafeStorageAPI {
  isAvailable: () => Promise<boolean>;
  encrypt: (data: string) => Promise<string>;
  decrypt: (encryptedData: string) => Promise<string>;
}

interface TerminalAPI {
  connect: (params: unknown) => Promise<{ sessionId: string }>;
  write: (sessionId: string, data: string) => void;
  resize: (sessionId: string, cols: number, rows: number) => void;
  close: (sessionId: string) => Promise<void>;
}

interface SftpAPI {
  connect: (params: unknown) => Promise<{ sessionId: string }>;
  listDirectory: (sessionId: string, path: string) => Promise<unknown[]>;
  readFile: (sessionId: string, path: string) => Promise<ArrayBuffer>;
  close: (sessionId: string) => Promise<void>;
}

interface VscodeAPI {
  launch: (options: unknown) => Promise<{ success: boolean; error?: string }>;
  isAvailable: () => Promise<boolean>;
  hasRemoteSSH: () => Promise<boolean>;
}

interface ContainerAPI {
  exec: (params: unknown) => Promise<{ sessionId: string }>;
  logs: (params: unknown) => Promise<{ sessionId: string }>;
  stats: (params: unknown) => Promise<{ sessionId: string }>;
}

interface RsyncAPI {
  execute: (options: unknown) => Promise<unknown>;
  preview: (options: unknown) => Promise<unknown>;
  abort: (operationId: string) => Promise<boolean>;
}

interface WindowAPI {
  openPopout: (options: unknown) => Promise<{ success: boolean }>;
  closePopout: (windowId: number) => Promise<boolean>;
  getPopoutCount: () => Promise<number>;
}

interface AppAPI {
  getVersion: () => Promise<string>;
  getPlatform: () => Promise<string>;
  getArch: () => Promise<string>;
}

interface ElectronAPI {
  safeStorage: SafeStorageAPI;
  terminal: TerminalAPI;
  sftp: SftpAPI;
  vscode: VscodeAPI;
  container: ContainerAPI;
  rsync: RsyncAPI;
  window: WindowAPI;
  app: AppAPI;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

// Export empty object to make this a module
export {};
