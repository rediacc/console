import { contextBridge, ipcRenderer } from 'electron';

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
    onAvailable: (callback: (info: unknown) => void) => () => void;
    onNotAvailable: (callback: (info: unknown) => void) => () => void;
    onDownloaded: (callback: (info: unknown) => void) => () => void;
    onProgress: (callback: (progress: unknown) => void) => () => void;
    onError: (callback: (error: string) => void) => () => void;
  };
  app: {
    getVersion: () => Promise<string>;
    getPlatform: () => Promise<string>;
    getArch: () => Promise<string>;
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
    onAvailable: (callback: (info: unknown) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: unknown): void => callback(info);
      ipcRenderer.on('updater:available', handler);
      return () => ipcRenderer.removeListener('updater:available', handler);
    },
    onNotAvailable: (callback: (info: unknown) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: unknown): void => callback(info);
      ipcRenderer.on('updater:not-available', handler);
      return () => ipcRenderer.removeListener('updater:not-available', handler);
    },
    onDownloaded: (callback: (info: unknown) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: unknown): void => callback(info);
      ipcRenderer.on('updater:downloaded', handler);
      return () => ipcRenderer.removeListener('updater:downloaded', handler);
    },
    onProgress: (callback: (progress: unknown) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, progress: unknown): void =>
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
};

// Expose to renderer via contextBridge
contextBridge.exposeInMainWorld('electronAPI', electronAPI);
