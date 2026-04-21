/**
 * Remote Config Adapter
 *
 * Handles transparent pull/push of encrypted config from the account server.
 * Implements the client side of the 3-layer encryption protocol:
 *   Layer 1 (SDK): Time-windowed server-derived key
 *   Layer 2 (CEK): Client-controlled key (passkey_secret + server_secret)
 *   Layer 3 (Org): Server-side (handled by server, transparent to this adapter)
 */

import {
  cekUnwrap,
  deriveWrappingKey,
  fromBase64,
  importAesKey,
  selectiveDecrypt,
  selectiveEncrypt,
  type EncryptedConfigPayload,
  type FieldCommitments,
  type FullConfig,
} from '@rediacc/shared/config-crypto';
import type { RemoteConfig, RdcConfig } from '../types/index.js';
import type { SecureStorage } from '../utils/secure-storage.js';
import { configServerFetch, ConfigServerError } from '../services/config-server-client.js';
import { t } from '../i18n/index.js';
import type { RemoteTokenStorage } from './remote-token-storage.js';

// ─── Types ──────────────────────────────────────────────────────────────

export interface PullResult {
  /** Decrypted config merged from envelope + sensitive data */
  config: RdcConfig;
  /** Server-side version number */
  version: number;
  /** SDK epoch used for encryption */
  sdkEpoch: number;
}

export interface PushResult {
  /** New version number after push */
  version: number;
}

/** Session crypto material from the server */
interface SessionMaterial {
  serverSecret: Uint8Array;
  sdkDerived: Awaited<ReturnType<typeof importAesKey>>;
  sdkEpoch: number;
}

// ─── Error Classes ──────────────────────────────────────────────────────

export class RemoteTokenExpiredError extends Error {
  constructor() {
    super(t('commands.config.remote.tokenExpired'));
    this.name = 'RemoteTokenExpiredError';
  }
}

export class RemoteVersionConflictError extends Error {
  constructor(serverVersion: number) {
    super(
      `Remote config updated by another device (v${serverVersion}). ` +
        'Refresh with: rdc config remote refresh'
    );
    this.name = 'RemoteVersionConflictError';
  }
}

export class RemotePasskeySecretMissingError extends Error {
  constructor() {
    super(t('commands.config.remote.passkeySecretMissing'));
    this.name = 'RemotePasskeySecretMissingError';
  }
}

// ─── Adapter ────────────────────────────────────────────────────────────

export class RemoteConfigAdapter {
  constructor(
    private readonly remote: RemoteConfig,
    private readonly configName: string,
    private readonly tokenStorage: RemoteTokenStorage,
    private readonly secureStorage: SecureStorage
  ) {}

  /**
   * Pull the latest config from the remote server.
   * Handles session setup, token rotation, and 3-layer decryption.
   */
  async pull(): Promise<PullResult> {
    const token = await this.requireToken();
    const session = await this.fetchSession(token);
    const cek = await this.deriveCek(session.serverSecret);

    // Fetch encrypted config blob
    const pullPath = `/account/api/v1/configs/${this.remote.configId}${
      this.remote.teamId ? `?teamId=${this.remote.teamId}` : ''
    }`;
    const pullResp = await this.fetch<{
      configData: string;
      envelope: {
        configId: string;
        version: number;
        teamId: string | null;
        lastModified: string;
        envelopeVersion?: 2;
        commitments?: FieldCommitments;
      };
      hmac: string | null;
    }>(pullPath, token);

    // Decrypt: Layer 2 (CEK) + Layer 1 (SDK)
    // Server-stored envelope is v2 (see Step 5). Until the server supports that,
    // fabricate empty commitments so the v2 shape is well-formed; selectiveDecrypt
    // still verifies HMAC + decrypts the blob successfully.
    const payload: EncryptedConfigPayload = {
      envelope: {
        envelopeVersion: 2,
        id: pullResp.data.envelope.configId,
        version: pullResp.data.envelope.version,
        sdkEpoch: session.sdkEpoch,
        teamId: pullResp.data.envelope.teamId ?? undefined,
        lastModified: pullResp.data.envelope.lastModified,
        commitments: pullResp.data.envelope.commitments ?? {
          alg: 'HMAC-SHA256',
          fckSalt: '',
          fields: {},
        },
      },
      encryptedBlob: pullResp.data.configData,
      hmac: pullResp.data.hmac ?? '',
    };

    const decrypted = await selectiveDecrypt(payload, cek, session.sdkDerived);

    // Map decrypted FullConfig to RdcConfig (v2 shape).
    const sshRaw = decrypted.ssh as
      | { privateKey?: string; publicKey?: string; knownHosts?: string }
      | undefined;
    const config: RdcConfig = {
      schemaVersion: 2,
      id: decrypted.id,
      version: decrypted.version,
      resources: {
        machines: (decrypted.machines ?? {}) as NonNullable<
          NonNullable<RdcConfig['resources']>['machines']
        >,
        repositories: (decrypted.repositories ?? {}) as NonNullable<
          NonNullable<RdcConfig['resources']>['repositories']
        >,
        storages: (decrypted.storages ?? {}) as NonNullable<
          NonNullable<RdcConfig['resources']>['storages']
        >,
      },
      credentials: sshRaw?.privateKey
        ? {
            ssh: {
              privateKey: sshRaw.privateKey,
              publicKey: sshRaw.publicKey,
              knownHosts: sshRaw.knownHosts,
            },
          }
        : undefined,
      encryption: { mode: 'plaintext' },
    };

    return {
      config,
      version: pullResp.data.envelope.version,
      sdkEpoch: session.sdkEpoch,
    };
  }

  /**
   * Push an updated config to the remote server.
   * Handles session setup, token rotation, and 3-layer encryption.
   */
  async push(config: RdcConfig, currentVersion: number): Promise<PushResult> {
    const token = await this.requireToken();
    const session = await this.fetchSession(token);
    const cek = await this.deriveCek(session.serverSecret);

    // Build a FullConfig for selective encryption. Commitments are computed
    // from the schema walker over the v2-shape config.
    const { pathsToCommit, getByPointer } = await import('../schema/walker.js');
    const commitPaths = pathsToCommit(config);
    const commitEntries = commitPaths.map((pointer) => ({
      pointer,
      value: getByPointer(config, pointer),
    }));

    const fullConfig: FullConfig = {
      envelopeVersion: 2,
      id: config.id,
      version: currentVersion + 1,
      sdkEpoch: session.sdkEpoch,
      commitments: { alg: 'HMAC-SHA256', fckSalt: '', fields: {} },
      machines: (config.resources?.machines ?? {}) as Record<string, unknown>,
      repositories: (config.resources?.repositories ?? {}) as Record<string, unknown>,
      storages: (config.resources?.storages ?? {}) as Record<string, unknown>,
      ssh: config.credentials?.ssh as Record<string, unknown> | undefined,
    };

    const encrypted = await selectiveEncrypt(fullConfig, session.sdkDerived, cek, {
      sdkEpoch: session.sdkEpoch,
      commitEntries,
    });

    // Push to server (server adds Layer 3)
    const pushPath = `/account/api/v1/configs/${this.remote.configId}`;
    const pushResp = await this.fetch<{ version: number }>(pushPath, token, {
      method: 'PUT',
      body: {
        teamId: this.remote.teamId,
        version: currentVersion + 1,
        encryptedBlob: encrypted.encryptedBlob,
        sdkEpoch: session.sdkEpoch,
        hmac: encrypted.hmac,
        envelope: encrypted.envelope,
      },
    });

    return { version: pushResp.data.version };
  }

  /**
   * Test connectivity by calling the session endpoint.
   */
  async testConnection(): Promise<boolean> {
    try {
      const token = await this.requireToken();
      await this.fetchSession(token);
      return true;
    } catch {
      return false;
    }
  }

  // ─── Private Helpers ──────────────────────────────────────────────────

  /** Get the current token or throw a clear error */
  private async requireToken(): Promise<string> {
    const data = await this.tokenStorage.get(this.configName);
    if (!data?.token) {
      throw new RemoteTokenExpiredError();
    }
    return data.token;
  }

  /** Fetch session crypto material (server_secret, sdk_derived, sdkEpoch) */
  private async fetchSession(currentToken: string): Promise<SessionMaterial> {
    const resp = await this.fetch<{
      server_secret: string;
      sdk_derived: string;
      sdkEpoch: number;
    }>('/account/api/v1/configs/session', currentToken, { method: 'POST' });

    return {
      serverSecret: fromBase64(resp.data.server_secret),
      sdkDerived: await importAesKey(fromBase64(resp.data.sdk_derived)),
      sdkEpoch: resp.data.sdkEpoch,
    };
  }

  /** Derive CEK from passkey_secret + server_secret */
  private async deriveCek(serverSecret: Uint8Array) {
    const passkeySecretStr = await this.secureStorage.get(this.remote.storageKeyId);
    if (!passkeySecretStr) {
      throw new RemotePasskeySecretMissingError();
    }

    const passkeySecret = fromBase64(passkeySecretStr);
    const wrappingKey = await deriveWrappingKey(passkeySecret, serverSecret);

    const tokenData = await this.tokenStorage.get(this.configName);
    if (!tokenData?.wrappedCek) {
      throw new RemoteTokenExpiredError();
    }

    return cekUnwrap(tokenData.wrappedCek, wrappingKey);
  }

  /**
   * Make a config server request with automatic token rotation.
   * Persists the new token after every successful response.
   */
  private async fetch<T>(
    path: string,
    currentToken: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    try {
      const resp = await configServerFetch<T>(path, {
        ...options,
        configToken: currentToken,
        serverUrl: this.remote.apiUrl,
      });

      // Persist rotated token immediately
      if (resp.newServerToken) {
        await this.tokenStorage.updateToken(this.configName, resp.newServerToken);
      }

      return { data: resp.data };
    } catch (error) {
      if (error instanceof ConfigServerError) {
        if (error.status === 401) {
          throw new RemoteTokenExpiredError();
        }
        if (error.status === 409) {
          throw new RemoteVersionConflictError(0);
        }
      }
      throw error;
    }
  }
}
