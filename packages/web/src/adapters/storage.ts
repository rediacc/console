import type { IStorageProvider } from '@/platform/types';

class WebStorageAdapter implements IStorageProvider {
  private readonly storage: Storage | null;
  private readonly memoryFallback = new Map<string, string>();

  constructor(storage?: Storage) {
    this.storage = typeof window !== 'undefined' ? (storage ?? window.localStorage) : null;
  }

  async getItem(key: string): Promise<string | null> {
    try {
      if (this.storage) {
        return this.storage.getItem(key);
      }
    } catch {
      // Fallback to memory map
    }
    return this.memoryFallback.get(key) ?? null;
  }

  async setItem(key: string, value: string): Promise<void> {
    try {
      if (this.storage) {
        this.storage.setItem(key, value);
        return;
      }
    } catch {
      // Ignore and fallback
    }
    this.memoryFallback.set(key, value);
  }

  async removeItem(key: string): Promise<void> {
    try {
      if (this.storage) {
        this.storage.removeItem(key);
        return;
      }
    } catch {
      // Ignore and fallback
    }
    this.memoryFallback.delete(key);
  }

  async clear(): Promise<void> {
    try {
      if (this.storage) {
        this.storage.clear();
        return;
      }
    } catch {
      // Ignore and fallback
    }
    this.memoryFallback.clear();
  }
}

export const webStorageAdapter = new WebStorageAdapter();
export default webStorageAdapter;
