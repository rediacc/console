/**
 * Rediacc Store Adapter
 *
 * Syncs CLI config files through the Rediacc account server with
 * triple-layer encryption (SDK + CEK + org passphrase).
 *
 * See docs/DESIGN-CONFIG-STORAGE.md for full architecture.
 */

import {
  configDecrypt,
  cekUnwrap,
  deriveWrappingKey,
  fromBase64,
  hmacVerify,
  selectiveEncrypt,
} from '@rediacc/shared/config-crypto';
import type { FullConfig } from '@rediacc/shared/config-crypto';
import type { StoreEntry } from '../types/store.js';
import { getSecureStorage } from '../utils/secure-storage.js';
import { storeRegistry } from './registry.js';
import type { IStoreAdapter, PullResult, PushResult } from './types.js';

/**
 * Resolve a config name to its UUID by reading the local config file.
 * Returns null if the file doesn't exist or can't be parsed.
 */
async function resolveConfigUuid(configName: string): Promise<string | null> {
  try {
    const { configFileStorage } = await import('../adapters/config-file-storage.js');
    const config = await configFileStorage.load(configName);
    return config.id;
  } catch {
    return null;
  }
}

interface ConfigSessionResponse {
  newServerToken: string;
  server_secret: string;
  sdk_derived: string;
  sdkEpoch: number;
}

interface ConfigPullResponse extends ConfigSessionResponse {
  configData: string; // client-encrypted blob (Layer 1+2)
  envelope: {
    configId: string;
    version: number;
    teamId: string | null;
    lastModified: string;
  };
  hmac: string | null;
}

interface ConfigPushResponse extends ConfigSessionResponse {
  version: number;
}

interface ConfigListResponse {
  newServerToken: string;
  configs: {
    id: string;
    configId: string;
    version: number;
    teamId: string | null;
    lastModified: string;
  }[];
}

export class RediacStoreAdapter implements IStoreAdapter {
  private readonly apiUrl: string;
  private readonly storeId: string;
  private readonly storageKeyId: string;
  private configToken: string;
  private readonly wrappedCek: string;
  private readonly storeName: string;

  constructor(private readonly entry: StoreEntry) {
    if (!entry.rediacApiUrl) throw new Error('Rediacc store requires rediacApiUrl');
    if (!entry.rediacStoreId) throw new Error('Rediacc store requires rediacStoreId');
    if (!entry.rediacStorageKeyId) throw new Error('Rediacc store requires rediacStorageKeyId');
    if (!entry.rediacConfigToken) throw new Error('Rediacc store requires rediacConfigToken');
    if (!entry.rediacWrappedCek) throw new Error('Rediacc store requires rediacWrappedCek');

    this.apiUrl = entry.rediacApiUrl;
    this.storeId = entry.rediacStoreId;
    this.storageKeyId = entry.rediacStorageKeyId;
    this.configToken = entry.rediacConfigToken;
    this.wrappedCek = entry.rediacWrappedCek;
    this.storeName = entry.name;
  }

  async push(config: unknown, _configName: string): Promise<PushResult> {
    const rdcConfig = config as FullConfig & { id: string; version: number };
    try {
      // Get crypto keys from server
      const session = await this.fetchSession();

      // Derive CEK
      const cek = await this.deriveCek(session.server_secret);
      const sdkDerived = await this.importAesKey(fromBase64(session.sdk_derived));

      // Selective encrypt (envelope stays plaintext, values encrypted)
      const payload = await selectiveEncrypt(
        rdcConfig as FullConfig,
        sdkDerived,
        cek,
        session.sdkEpoch
      );

      // Push to server
      const response = await this.fetchJson<ConfigPushResponse>(`/configs/${rdcConfig.id}`, 'PUT', {
        teamId: undefined,
        version: rdcConfig.version,
        encryptedBlob: payload.encryptedBlob,
        sdkEpoch: session.sdkEpoch,
        hmac: payload.hmac,
      });

      // Update rotating token
      await this.updateToken(response.newServerToken);

      return { success: true, remoteVersion: response.version };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('409') || message.includes('conflict')) {
        return {
          success: false,
          error: `Version conflict. Run "rdc store pull --store ${this.storeName}" first.`,
        };
      }
      return { success: false, error: message };
    }
  }

  async pull(configName: string): Promise<PullResult> {
    try {
      // Resolve configName (human name like "rediacc") to its UUID,
      // since push() stores configs keyed by UUID (rdcConfig.id).
      const configUuid = await resolveConfigUuid(configName);

      // List configs to find by UUID
      const listResponse = await this.fetchJson<ConfigListResponse>('/configs', 'GET');
      await this.updateToken(listResponse.newServerToken);

      const entry = listResponse.configs.find(
        (c) => c.configId === configUuid || c.configId === configName
      );
      if (!entry) {
        return { success: false, error: `Config "${configName}" not found in store` };
      }

      // Pull the config
      const response = await this.fetchJson<ConfigPullResponse>(
        `/configs/${entry.configId}`,
        'GET'
      );

      // Derive CEK
      const cek = await this.deriveCek(response.server_secret);
      const sdkDerived = await this.importAesKey(fromBase64(response.sdk_derived));

      // Verify HMAC if present
      if (response.hmac) {
        const hmacValid = await hmacVerify(response.configData, cek, response.hmac);
        if (!hmacValid) {
          return {
            success: false,
            error: 'Config integrity check failed. Data may be corrupted or tampered.',
          };
        }
      }

      // Decrypt (Layer 2: CEK, Layer 1: SDK)
      const decryptedJson = await configDecrypt(response.configData, cek, sdkDerived);
      const sensitiveData = JSON.parse(decryptedJson);

      // Merge envelope + decrypted data
      const fullConfig = {
        ...response.envelope,
        ...sensitiveData,
      };

      // Update rotating token
      await this.updateToken(response.newServerToken);

      return { success: true, config: fullConfig };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  async list(): Promise<string[]> {
    try {
      const response = await this.fetchJson<ConfigListResponse>('/configs', 'GET');
      await this.updateToken(response.newServerToken);
      return response.configs.map((c) => c.configId);
    } catch {
      return [];
    }
  }

  async delete(configName: string): Promise<PushResult> {
    try {
      await this.fetchJson(`/configs/${configName}?storeId=${this.storeId}`, 'DELETE');
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  async verify(): Promise<boolean> {
    try {
      const response = await this.fetchSession();
      await this.updateToken(response.newServerToken);
      return true;
    } catch {
      return false;
    }
  }

  // ── Private Helpers ─────────────────────────────────────────────────

  private async fetchSession(): Promise<ConfigSessionResponse> {
    return this.fetchJson<ConfigSessionResponse>('/configs/session', 'POST');
  }

  private async fetchJson<T>(path: string, method: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = {
      'X-Config-Token': this.configToken,
    };
    if (body) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${this.apiUrl}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    return response.json() as Promise<T>;
  }

  private async deriveCek(serverSecretB64: string) {
    const secureStorage = getSecureStorage();
    const passkeySecretB64 = await secureStorage.get(this.storageKeyId);
    if (!passkeySecretB64) {
      throw new Error(
        `passkey_secret not found in secure storage (key: ${this.storageKeyId}). ` +
          'Run "rdc store add --type rediacc" to re-setup.'
      );
    }

    const passkeySecret = fromBase64(passkeySecretB64);
    const serverSecret = fromBase64(serverSecretB64);
    const wrappingKey = await deriveWrappingKey(passkeySecret, serverSecret);
    return cekUnwrap(this.wrappedCek, wrappingKey);
  }

  private async importAesKey(
    rawBytes: Uint8Array
  ): Promise<Awaited<ReturnType<typeof crypto.subtle.importKey>>> {
    return crypto.subtle.importKey('raw', rawBytes, { name: 'AES-GCM', length: 256 }, true, [
      'encrypt',
      'decrypt',
    ]);
  }

  private async updateToken(newToken: string): Promise<void> {
    this.configToken = newToken;
    // Persist updated token to store registry
    await storeRegistry.update(this.storeName, { rediacConfigToken: newToken });
  }
}
