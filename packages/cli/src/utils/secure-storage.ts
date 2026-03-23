/**
 * Platform-Native Secure Storage
 *
 * Stores secrets (passkey_secret) in OS-native secure storage:
 * - Linux:   Kernel keyring (keyctl)
 * - macOS:   Keychain (security command)
 * - Windows: DPAPI (encrypted files)
 * - Fallback: JSON file with 0o600 permissions (warning logged)
 *
 * Each secret is indexed by a server-provided storageKeyId.
 */

import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { getRediaccDirs } from '@rediacc/shared/paths';

const SERVICE_NAME = 'rdc-config';

// ─── Interface ──────────────────────────────────────────────────────────

export interface SecureStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  readonly type: string;
}

// ─── Linux: Kernel Keyring (keyctl) ─────────────────────────────────────

class KeyctlStorage implements SecureStorage {
  readonly type = 'keyctl';

  get(key: string): Promise<string | null> {
    try {
      const keyId = execSync(`keyctl search @u user "${key}" 2>/dev/null`, {
        encoding: 'utf-8',
      }).trim();
      if (!keyId) return Promise.resolve(null);
      return Promise.resolve(execSync(`keyctl pipe ${keyId}`, { encoding: 'utf-8' }));
    } catch {
      return Promise.resolve(null);
    }
  }

  async set(key: string, value: string): Promise<void> {
    // Remove existing key if present
    await this.delete(key);
    execSync(`keyctl add user "${key}" "${value}" @u`, { encoding: 'utf-8' });
    // Set 24h timeout
    try {
      const keyId = execSync(`keyctl search @u user "${key}"`, { encoding: 'utf-8' }).trim();
      execSync(`keyctl timeout ${keyId} 86400`);
    } catch {
      // Timeout is best-effort
    }
  }

  delete(key: string): Promise<void> {
    try {
      const keyId = execSync(`keyctl search @u user "${key}" 2>/dev/null`, {
        encoding: 'utf-8',
      }).trim();
      if (keyId) {
        execSync(`keyctl unlink ${keyId} @u`);
      }
    } catch {
      // Key doesn't exist — ok
    }
    return Promise.resolve();
  }
}

// ─── macOS: Keychain ────────────────────────────────────────────────────

class KeychainStorage implements SecureStorage {
  readonly type = 'keychain';

  get(key: string): Promise<string | null> {
    try {
      const result = execSync(
        `security find-generic-password -a "${key}" -s "${SERVICE_NAME}" -w 2>/dev/null`,
        { encoding: 'utf-8' }
      );
      return Promise.resolve(result.trim() || null);
    } catch {
      return Promise.resolve(null);
    }
  }

  async set(key: string, value: string): Promise<void> {
    // Delete existing entry first (update not supported directly)
    await this.delete(key);
    execSync(`security add-generic-password -a "${key}" -s "${SERVICE_NAME}" -w "${value}" -U`, {
      encoding: 'utf-8',
    });
  }

  delete(key: string): Promise<void> {
    try {
      execSync(`security delete-generic-password -a "${key}" -s "${SERVICE_NAME}" 2>/dev/null`, {
        encoding: 'utf-8',
      });
    } catch {
      // Entry doesn't exist — ok
    }
    return Promise.resolve();
  }
}

// ─── Windows: DPAPI ─────────────────────────────────────────────────────

class DpapiStorage implements SecureStorage {
  readonly type = 'dpapi';
  private readonly keysDir: string;

  constructor() {
    const { state } = getRediaccDirs();
    this.keysDir = join(state, 'keys');
    mkdirSync(this.keysDir, { recursive: true });
  }

  private keyPath(key: string): string {
    // Sanitize key for filesystem
    const safeKey = key.replaceAll(/[^a-zA-Z0-9_.-]/g, '_');
    return join(this.keysDir, `${safeKey}.dpapi`);
  }

  get(key: string): Promise<string | null> {
    const path = this.keyPath(key);
    if (!existsSync(path)) return Promise.resolve(null);
    try {
      const encrypted = readFileSync(path, 'utf-8');
      const result = execSync(
        `powershell -NoProfile -Command "[Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String('${encrypted}'), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))"`,
        { encoding: 'utf-8' }
      );
      return Promise.resolve(result.trim() || null);
    } catch {
      return Promise.resolve(null);
    }
  }

  set(key: string, value: string): Promise<void> {
    const encrypted = execSync(
      `powershell -NoProfile -Command "[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes('${value}'), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))"`,
      { encoding: 'utf-8' }
    ).trim();
    writeFileSync(this.keyPath(key), encrypted, { mode: 0o600 });
    return Promise.resolve();
  }

  delete(key: string): Promise<void> {
    const path = this.keyPath(key);
    if (existsSync(path)) {
      unlinkSync(path);
    }
    return Promise.resolve();
  }
}

// ─── Fallback: File (0o600) ─────────────────────────────────────────────

class FileStorage implements SecureStorage {
  readonly type = 'file';
  private readonly storePath: string;

  constructor() {
    const { state } = getRediaccDirs();
    this.storePath = join(state, 'secure-keys.json');
  }

  private load(): Record<string, string> {
    if (!existsSync(this.storePath)) return {};
    try {
      return JSON.parse(readFileSync(this.storePath, 'utf-8'));
    } catch {
      return {};
    }
  }

  private save(data: Record<string, string>): void {
    mkdirSync(join(this.storePath, '..'), { recursive: true });
    writeFileSync(this.storePath, JSON.stringify(data, null, 2), { mode: 0o600 });
  }

  get(key: string): Promise<string | null> {
    return Promise.resolve(this.load()[key] ?? null);
  }

  set(key: string, value: string): Promise<void> {
    const data = this.load();
    data[key] = value;
    this.save(data);
    return Promise.resolve();
  }

  delete(key: string): Promise<void> {
    const data = this.load();
    delete data[key];
    this.save(data);
    return Promise.resolve();
  }
}

// ─── Factory ────────────────────────────────────────────────────────────

/**
 * Get the platform-appropriate secure storage implementation.
 * Falls back to file-based storage if native storage is unavailable.
 */
export function getSecureStorage(): SecureStorage {
  switch (process.platform) {
    case 'linux':
      try {
        // Test if keyctl is available
        execSync('keyctl show @u 2>/dev/null', { encoding: 'utf-8' });
        return new KeyctlStorage();
      } catch {
        return new FileStorage();
      }
    case 'darwin':
      try {
        // Test if security command is available
        execSync('security help 2>/dev/null', { encoding: 'utf-8' });
        return new KeychainStorage();
      } catch {
        return new FileStorage();
      }
    case 'win32':
      return new DpapiStorage();
    default:
      return new FileStorage();
  }
}
