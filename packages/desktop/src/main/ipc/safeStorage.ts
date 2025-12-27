import { ipcMain, safeStorage, app } from 'electron';
import { join } from 'path';
import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync } from 'fs';

const STORAGE_DIR = join(app.getPath('userData'), 'secure-storage');
const STORAGE_FILE = join(STORAGE_DIR, 'data.enc');

interface SecureData {
  [key: string]: string;
}

function ensureStorageDir(): void {
  if (!existsSync(STORAGE_DIR)) {
    mkdirSync(STORAGE_DIR, { recursive: true });
  }
}

function loadStorage(): SecureData {
  try {
    if (existsSync(STORAGE_FILE)) {
      const encrypted = readFileSync(STORAGE_FILE);
      if (safeStorage.isEncryptionAvailable()) {
        const decrypted = safeStorage.decryptString(encrypted);
        return JSON.parse(decrypted) as SecureData;
      }
      // Fallback: if encryption not available, treat as plain JSON
      return JSON.parse(encrypted.toString('utf-8')) as SecureData;
    }
  } catch (error) {
    console.error('Failed to load secure storage:', error);
  }
  return {};
}

function saveStorage(data: SecureData): void {
  ensureStorageDir();
  const json = JSON.stringify(data);

  if (safeStorage.isEncryptionAvailable()) {
    const encrypted = safeStorage.encryptString(json);
    writeFileSync(STORAGE_FILE, encrypted);
  } else {
    // Fallback: save as plain JSON (not recommended, but prevents data loss)
    console.warn('SafeStorage encryption not available, storing data unencrypted');
    writeFileSync(STORAGE_FILE, json);
  }
}

export function registerSafeStorageHandlers(): void {
  // Check if safeStorage is available
  ipcMain.handle('safeStorage:isAvailable', () => {
    return safeStorage.isEncryptionAvailable();
  });

  // Encrypt a string directly (returns base64)
  ipcMain.handle('safeStorage:encrypt', (_event, data: string) => {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('SafeStorage encryption not available');
    }
    const encrypted = safeStorage.encryptString(data);
    return encrypted.toString('base64');
  });

  // Decrypt a base64 encoded string
  ipcMain.handle('safeStorage:decrypt', (_event, encryptedBase64: string) => {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error('SafeStorage encryption not available');
    }
    const encrypted = Buffer.from(encryptedBase64, 'base64');
    return safeStorage.decryptString(encrypted);
  });

  // Persistent key-value storage with safeStorage encryption
  ipcMain.handle('storage:set', (_event, key: string, value: string) => {
    const storage = loadStorage();
    storage[key] = value;
    saveStorage(storage);
  });

  ipcMain.handle('storage:get', (_event, key: string) => {
    const storage = loadStorage();
    return storage[key] ?? null;
  });

  ipcMain.handle('storage:remove', (_event, key: string) => {
    const storage = loadStorage();
    delete storage[key];
    saveStorage(storage);
  });

  ipcMain.handle('storage:clear', () => {
    if (existsSync(STORAGE_FILE)) {
      unlinkSync(STORAGE_FILE);
    }
  });

  ipcMain.handle('storage:keys', () => {
    const storage = loadStorage();
    return Object.keys(storage);
  });
}
