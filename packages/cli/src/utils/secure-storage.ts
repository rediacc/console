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

import { execFileSync, execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { getRediaccDirs } from '@rediacc/shared/paths';

const SERVICE_NAME = 'rdc-config';

// ─── Key allowlist (defense-in-depth) ───────────────────────────────────
//
// The storage key (`storageKeyId`) is SERVER-provided over the config-remote
// handoff, so it reaches these sinks fully untrusted. Even though every
// backend below now passes it as an argv element (never interpolated into a
// shell string), we reject anything outside a conservative allowlist so a
// hostile value can never reach a native tool at all. Covers the handoff
// storageKeyId and the `rdc:pw:<uuid>` password-flow keys.
const SAFE_KEY = /^[A-Za-z0-9:_-]{1,200}$/;

function assertSafeStorageKey(key: string): void {
  if (!SAFE_KEY.test(key)) {
    throw new Error(
      `Refusing unsafe secure-storage key: only [A-Za-z0-9:_-] (max 200 chars) are allowed`
    );
  }
}

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
      const keyId = execFileSync('keyctl', ['search', '@u', 'user', key], {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      }).trim();
      if (!keyId) return Promise.resolve(null);
      return Promise.resolve(execFileSync('keyctl', ['pipe', keyId], { encoding: 'utf-8' }));
    } catch {
      return Promise.resolve(null);
    }
  }

  async set(key: string, value: string): Promise<void> {
    // Remove existing key if present
    await this.delete(key);
    execFileSync('keyctl', ['add', 'user', key, value, '@u'], { encoding: 'utf-8' });
    // No timeout — passkey_secret must persist across reboots/days.
    // The user keyring (@u) lives for the session by default; keys
    // without an explicit timeout persist until the session ends or
    // the key is explicitly revoked, which matches what deriveCek()
    // expects (a missing key is fatal and asks the user to re-setup).
  }

  delete(key: string): Promise<void> {
    try {
      const keyId = execFileSync('keyctl', ['search', '@u', 'user', key], {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      }).trim();
      if (keyId) {
        execFileSync('keyctl', ['unlink', keyId, '@u']);
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
      const result = execFileSync(
        'security',
        ['find-generic-password', '-a', key, '-s', SERVICE_NAME, '-w'],
        { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }
      );
      return Promise.resolve(result.trim() || null);
    } catch {
      return Promise.resolve(null);
    }
  }

  async set(key: string, value: string): Promise<void> {
    // Delete existing entry first (update not supported directly)
    await this.delete(key);
    execFileSync(
      'security',
      ['add-generic-password', '-a', key, '-s', SERVICE_NAME, '-w', value, '-U'],
      { encoding: 'utf-8' }
    );
  }

  delete(key: string): Promise<void> {
    try {
      execFileSync('security', ['delete-generic-password', '-a', key, '-s', SERVICE_NAME], {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
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
      // Pass the ciphertext through an env var, never interpolated into the
      // script, so a tampered cache file cannot inject PowerShell.
      const script =
        '[Text.Encoding]::UTF8.GetString([Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String($env:RDC_DPAPI_ENC), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))';
      const result = execFileSync('powershell', ['-NoProfile', '-Command', script], {
        encoding: 'utf-8',
        env: { ...process.env, RDC_DPAPI_ENC: encrypted.trim() },
      });
      return Promise.resolve(result.trim() || null);
    } catch {
      return Promise.resolve(null);
    }
  }

  set(key: string, value: string): Promise<void> {
    // Pass the secret through an env var, never interpolated into the script,
    // so a secret containing quotes/newlines cannot inject PowerShell.
    const script =
      '[Convert]::ToBase64String([Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($env:RDC_DPAPI_VALUE), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser))';
    const encrypted = execFileSync('powershell', ['-NoProfile', '-Command', script], {
      encoding: 'utf-8',
      env: { ...process.env, RDC_DPAPI_VALUE: value },
    }).trim();
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

// ─── Validating wrapper (single choke-point) ────────────────────────────

/**
 * Wraps any backend and rejects unsafe keys BEFORE they reach a native tool.
 * Every path that touches secure storage goes through `getSecureStorage()`, so
 * validating here guarantees no untrusted `storageKeyId` reaches keyctl,
 * security, or PowerShell — regardless of which backend is active.
 */
class ValidatingStorage implements SecureStorage {
  constructor(private readonly inner: SecureStorage) {}

  get type(): string {
    return this.inner.type;
  }

  get(key: string): Promise<string | null> {
    assertSafeStorageKey(key);
    return this.inner.get(key);
  }

  set(key: string, value: string): Promise<void> {
    assertSafeStorageKey(key);
    return this.inner.set(key, value);
  }

  delete(key: string): Promise<void> {
    assertSafeStorageKey(key);
    return this.inner.delete(key);
  }
}

// ─── Factory ────────────────────────────────────────────────────────────

function selectBackend(): SecureStorage {
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

/**
 * Get the platform-appropriate secure storage implementation.
 * Falls back to file-based storage if native storage is unavailable.
 * The returned storage validates every key (see ValidatingStorage).
 */
export function getSecureStorage(): SecureStorage {
  return new ValidatingStorage(selectBackend());
}
