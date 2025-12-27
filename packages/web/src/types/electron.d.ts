/**
 * Type declarations for Electron API exposed via preload script
 * These types match the API exposed in packages/desktop/src/preload/index.ts
 */

export interface ElectronSafeStorageAPI {
  isAvailable(): Promise<boolean>;
  encrypt(data: string): Promise<string>;
  decrypt(encryptedData: string): Promise<string>;
}

export interface ElectronStorageAPI {
  set(key: string, value: string): Promise<void>;
  get(key: string): Promise<string | null>;
  remove(key: string): Promise<void>;
  clear(): Promise<void>;
  keys(): Promise<string[]>;
}

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

export interface ElectronUpdaterAPI {
  checkForUpdates(): Promise<void>;
  downloadUpdate(): Promise<void>;
  installUpdate(): Promise<void>;
  getVersion(): Promise<string>;
  onChecking(callback: () => void): () => void;
  onAvailable(callback: (info: UpdateInfo) => void): () => void;
  onNotAvailable(callback: (info: UpdateInfo) => void): () => void;
  onDownloaded(callback: (info: UpdateInfo) => void): () => void;
  onProgress(callback: (progress: UpdateProgress) => void): () => void;
  onError(callback: (error: string) => void): () => void;
}

export interface ElectronAppAPI {
  getVersion(): Promise<string>;
  getPlatform(): Promise<string>;
  getArch(): Promise<string>;
}

export interface ElectronAPI {
  safeStorage: ElectronSafeStorageAPI;
  storage: ElectronStorageAPI;
  updater: ElectronUpdaterAPI;
  app: ElectronAppAPI;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};
