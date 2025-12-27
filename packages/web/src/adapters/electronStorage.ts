/**
 * Electron Storage Adapter
 * Provides persistent encrypted storage using Electron's safeStorage API
 * Falls back gracefully when not running in Electron
 */

import { isElectron } from '@/utils/environment';

/**
 * Secure storage provider interface
 */
export interface ISecureStorageProvider {
  isAvailable(): boolean;
  setItem(key: string, value: string): Promise<void>;
  getItem(key: string): Promise<string | null>;
  removeItem(key: string): Promise<void>;
  clear(): Promise<void>;
  keys(): Promise<string[]>;
}

/**
 * Electron Storage Adapter
 * Uses Electron's IPC bridge to access safeStorage-backed persistent storage
 */
class ElectronStorageAdapter implements ISecureStorageProvider {
  /**
   * Check if Electron storage is available
   */
  isAvailable(): boolean {
    return isElectron() && window.electronAPI?.storage !== undefined;
  }

  /**
   * Store a value with the given key
   */
  async setItem(key: string, value: string): Promise<void> {
    if (!this.isAvailable()) {
      throw new Error('Electron storage not available');
    }
    return window.electronAPI!.storage.set(key, value);
  }

  /**
   * Retrieve a value by key
   */
  async getItem(key: string): Promise<string | null> {
    if (!this.isAvailable()) {
      throw new Error('Electron storage not available');
    }
    return window.electronAPI!.storage.get(key);
  }

  /**
   * Remove a value by key
   */
  async removeItem(key: string): Promise<void> {
    if (!this.isAvailable()) {
      throw new Error('Electron storage not available');
    }
    return window.electronAPI!.storage.remove(key);
  }

  /**
   * Clear all stored values
   */
  async clear(): Promise<void> {
    if (!this.isAvailable()) {
      throw new Error('Electron storage not available');
    }
    return window.electronAPI!.storage.clear();
  }

  /**
   * Get all stored keys
   */
  async keys(): Promise<string[]> {
    if (!this.isAvailable()) {
      throw new Error('Electron storage not available');
    }
    return window.electronAPI!.storage.keys();
  }
}

/**
 * Singleton instance of the Electron storage adapter
 */
export const electronStorageAdapter = new ElectronStorageAdapter();

/**
 * Check if we should use Electron storage
 * Returns true if running in Electron and safeStorage is available
 */
export async function shouldUseElectronStorage(): Promise<boolean> {
  if (!isElectron() || !window.electronAPI?.safeStorage) {
    return false;
  }
  try {
    return await window.electronAPI.safeStorage.isAvailable();
  } catch {
    return false;
  }
}
