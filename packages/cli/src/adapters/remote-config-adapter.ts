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
  type EncryptedConfigPayload,
  type FieldCommitments,
  fromBase64,
  importAesKey,
  selectiveDecrypt,
} from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import { buildConfigPushPayload } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import { ConfigServerError, configServerFetch } from '../services/config/config-server-client.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import type { SecureStorage } from '../utils/secure-storage.js';
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

class RemoteVersionConflictError extends Error {
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

/**
 * The stored slot secret no longer unwraps the CEK. The most common cause is a
 * CEK rotation that bumped the store's generation while this device kept its old
 * wrapping — the AES-GCM auth tag then fails. Surfaced instead of the raw
 * OperationError so the user gets an action (re-enroll) rather than a crypto
 * stack trace. Applies to every enrollment method (passkey and password).
 */
export class RemoteStaleSlotError extends Error {
  constructor() {
    super(t('commands.config.remote.staleSlot'));
    this.name = 'RemoteStaleSlotError';
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

    // Rebuild the RdcConfig from the decrypted blob through the ONE shared
    // reconstruction. This used to be a hand-written copy that had to "mirror"
    // fullConfigToRdcConfig exactly; keeping two copies in sync is precisely how
    // the explicit-undefined trap (and later the dropped-secret bug) reached
    // production, so there is now a single implementation and both the CLI pull
    // and the CEK rotation go through it.
    const config = fullConfigToRdcConfig(decrypted);

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

    // Envelope + commitments + ciphertext are composed by the shared helper, so
    // the CLI, the web console editor, and the CEK rotation flow all emit a
    // byte-identical payload. Diverging here would fail the server precondition.
    const encrypted = await buildConfigPushPayload(config, {
      version: currentVersion + 1,
      sdkEpoch: session.sdkEpoch,
      sdkDerived: session.sdkDerived,
      cek,
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

    // A wrong slot secret (or a rotated CEK this device never re-wrapped for)
    // surfaces here as an AES-GCM auth failure. Translate it into an actionable
    // "re-enroll" message rather than leaking a raw OperationError.
    try {
      return await cekUnwrap(tokenData.wrappedCek, wrappingKey);
    } catch {
      throw new RemoteStaleSlotError();
    }
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
