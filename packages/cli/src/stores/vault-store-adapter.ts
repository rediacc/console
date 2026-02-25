import { DEFAULTS } from '@rediacc/shared/config';
import type { IStoreAdapter, PullResult, PushResult } from './types.js';
import type { RdcConfig } from '../types/index.js';
import type { StoreEntry } from '../types/store.js';

/**
 * Vault store adapter. Stores config files as secrets in HashiCorp Vault KV v2.
 * Config "production" is stored at secret path "rdc/configs/production" by default.
 */
export class VaultStoreAdapter implements IStoreAdapter {
  private readonly addr: string;
  private readonly token: string;
  private readonly mount: string;
  private readonly prefix: string;
  private readonly namespace: string | null;

  constructor(entry: StoreEntry) {
    if (!entry.vaultAddr || !entry.vaultToken) {
      throw new Error('Vault store requires vaultAddr and vaultToken');
    }
    this.addr = entry.vaultAddr.replace(/\/+$/, '');
    this.token = entry.vaultToken;
    this.mount = entry.vaultMount ?? DEFAULTS.STORE.VAULT_MOUNT;
    this.prefix = entry.vaultPrefix ?? DEFAULTS.STORE.VAULT_PREFIX;
    this.namespace = entry.vaultNamespace ?? null;
  }

  private secretPath(configName: string): string {
    return `${this.prefix}/${configName}`;
  }

  private dataUrl(configName: string): string {
    return `${this.addr}/v1/${this.mount}/data/${this.secretPath(configName)}`;
  }

  private metadataUrl(path?: string): string {
    const p = path ?? this.prefix;
    return `${this.addr}/v1/${this.mount}/metadata/${p}`;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = {
      'X-Vault-Token': this.token,
      'Content-Type': 'application/json',
    };
    if (this.namespace) {
      h['X-Vault-Namespace'] = this.namespace;
    }
    return h;
  }

  private async vaultFetch(url: string, options?: RequestInit): Promise<Response> {
    return fetch(url, {
      ...options,
      headers: { ...this.headers(), ...(options?.headers as Record<string, string>) },
    });
  }

  private parseRemoteConfig(raw: string): RdcConfig | null {
    try {
      return JSON.parse(raw) as RdcConfig;
    } catch {
      return null;
    }
  }

  /**
   * Check the remote Vault secret for GUID or version conflicts before pushing.
   * Returns a PushResult if there's a conflict, or null if OK to proceed.
   */
  private async checkConflict(config: RdcConfig, configName: string): Promise<PushResult | null> {
    const res = await this.vaultFetch(this.dataUrl(configName)).catch(() => null);
    if (!res?.ok) return null; // 404, network error, etc. — no conflict

    const body = (await res.json()) as { data?: { data?: { config?: string } } };
    const raw = body.data?.data?.config;
    if (!raw) return null;

    const remote = this.parseRemoteConfig(raw);
    if (!remote) return null; // corrupt JSON — will be overwritten

    if (remote.id !== config.id) {
      return {
        success: false,
        error: `GUID mismatch: local config id "${config.id}" does not match remote "${remote.id}". Configs with different IDs cannot be synced.`,
      };
    }
    if (remote.version > config.version) {
      return {
        success: false,
        error: `Version conflict: remote version ${remote.version} is newer than local version ${config.version}. Run "rdc store pull" first.`,
      };
    }
    return null;
  }

  async push(config: RdcConfig, configName: string): Promise<PushResult> {
    // Check remote for conflict
    const conflict = await this.checkConflict(config, configName);
    if (conflict) return conflict;

    // Write the secret
    const res = await this.vaultFetch(this.dataUrl(configName), {
      method: 'POST',
      body: JSON.stringify({ data: { config: JSON.stringify(config) } }),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => 'unknown error');
      return { success: false, error: `Vault write failed (${res.status}): ${text}` };
    }

    return { success: true, remoteVersion: config.version };
  }

  async pull(configName: string): Promise<PullResult> {
    const res = await this.vaultFetch(this.dataUrl(configName));

    if (res.status === 404) {
      return { success: false, error: `Config "${configName}" not found in store` };
    }

    if (!res.ok) {
      const text = await res.text().catch(() => 'unknown error');
      return { success: false, error: `Vault read failed (${res.status}): ${text}` };
    }

    const body = (await res.json()) as { data?: { data?: { config?: string } } };
    const raw = body.data?.data?.config;
    if (!raw) {
      return { success: false, error: `Config "${configName}" has no data in Vault` };
    }

    try {
      const config = JSON.parse(raw) as RdcConfig;
      return { success: true, config };
    } catch {
      return { success: false, error: `Config "${configName}" contains invalid JSON` };
    }
  }

  async list(): Promise<string[]> {
    // Vault LIST is GET with ?list=true on the metadata path
    const url = `${this.metadataUrl()}?list=true`;
    const res = await this.vaultFetch(url);

    if (res.status === 404) {
      return []; // No secrets at this path yet
    }

    if (!res.ok) {
      return [];
    }

    const body = (await res.json()) as { data?: { keys?: string[] } };
    const keys = body.data?.keys ?? [];
    // Filter out directory entries (ending with /) and return clean names
    return keys.filter((k) => !k.endsWith('/')).sort();
  }

  async delete(configName: string): Promise<PushResult> {
    // DELETE on metadata path permanently removes all versions + metadata
    const res = await this.vaultFetch(this.metadataUrl(this.secretPath(configName)), {
      method: 'DELETE',
    });

    if (res.status === 404) {
      return { success: false, error: `Config "${configName}" not found` };
    }

    if (!res.ok) {
      const text = await res.text().catch(() => 'unknown error');
      return { success: false, error: `Vault delete failed (${res.status}): ${text}` };
    }

    return { success: true };
  }

  async verify(): Promise<boolean> {
    try {
      // Check Vault health (unauthenticated)
      const healthRes = await fetch(`${this.addr}/v1/sys/health`);
      if (!healthRes.ok) return false;
      const health = (await healthRes.json()) as { initialized?: boolean; sealed?: boolean };
      if (!health.initialized || health.sealed) return false;

      // Verify token is valid
      const tokenRes = await this.vaultFetch(`${this.addr}/v1/auth/token/lookup-self`);
      return tokenRes.ok;
    } catch {
      return false;
    }
  }
}
