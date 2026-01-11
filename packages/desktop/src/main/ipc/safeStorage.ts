import { existsSync } from 'node:fs';
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { app, ipcMain, safeStorage } from 'electron';

const STORAGE_DIR = join(app.getPath('userData'), 'secure-storage');
const STORAGE_FILE = join(STORAGE_DIR, 'data.enc');

interface SecureData {
  [key: string]: string;
}

async function ensureStorageDir(): Promise<void> {
  if (!existsSync(STORAGE_DIR)) {
    await mkdir(STORAGE_DIR, { recursive: true });
  }
}

async function loadStorage(): Promise<SecureData> {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('SafeStorage encryption not available. Cannot load secure data.');
  }

  try {
    if (existsSync(STORAGE_FILE)) {
      const encrypted = await readFile(STORAGE_FILE);
      const decrypted = safeStorage.decryptString(encrypted);
      return JSON.parse(decrypted) as SecureData;
    }
  } catch (error) {
    console.error('Failed to load secure storage:', error);
  }
  return {};
}

async function saveStorage(data: SecureData): Promise<void> {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('SafeStorage encryption not available. Cannot save sensitive data.');
  }

  await ensureStorageDir();
  const json = JSON.stringify(data);
  const encrypted = safeStorage.encryptString(json);
  await writeFile(STORAGE_FILE, encrypted);
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
  ipcMain.handle('storage:set', async (_event, key: string, value: string) => {
    const storage = await loadStorage();
    storage[key] = value;
    await saveStorage(storage);
  });

  ipcMain.handle('storage:get', async (_event, key: string) => {
    const storage = await loadStorage();
    return storage[key] ?? null;
  });

  ipcMain.handle('storage:remove', async (_event, key: string) => {
    const storage = await loadStorage();
    delete storage[key];
    await saveStorage(storage);
  });

  ipcMain.handle('storage:clear', async () => {
    if (existsSync(STORAGE_FILE)) {
      await unlink(STORAGE_FILE);
    }
  });

  ipcMain.handle('storage:keys', async () => {
    const storage = await loadStorage();
    return Object.keys(storage);
  });
}
