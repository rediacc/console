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
import {
  ConfigServerError,
  type ConfigServerFetchOptions,
  configServerFetch,
} from '../services/config/config-server-client.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import type { SecureStorage } from '../utils/secure-storage.js';
import type { RemoteTokenStorage, TokenLease } from './remote-token-storage.js';

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

/**
 * The server refused this device's config token (HTTP 401). `reason` is the
 * server's own code from "Config auth failed: <reason>" (config-token.ts), so
 * each cause keeps its message instead of all 401s reading as "expired".
 */
export class RemoteAuthError extends Error {
  constructor(
    public readonly reason: string,
    message: string
  ) {
    super(message);
    this.name = 'RemoteAuthError';
  }
}

/** The token is past its lifetime, or this device holds none at all. */
export class RemoteTokenExpiredError extends RemoteAuthError {
  constructor() {
    super('token_expired', t('commands.config.remote.tokenExpired'));
    this.name = 'RemoteTokenExpiredError';
  }
}

/**
 * The token is bound to another client address: a token chain binds to the
 * address that first uses it, so a token some other client already spent
 * (the enabling browser, before the device-token fix) fails here.
 */
export class RemoteTokenIpMismatchError extends RemoteAuthError {
  constructor() {
    super('ip_mismatch', t('commands.config.remote.tokenIpMismatch'));
    this.name = 'RemoteTokenIpMismatchError';
  }
}

const AUTH_REASON_RE = /Config auth failed: ([a-z_]+)/;

/** Map a 401 onto the error for the server's stated reason. */
export function remoteAuthErrorFor(serverMessage: string): RemoteAuthError {
  const reason = AUTH_REASON_RE.exec(serverMessage)?.[1];
  switch (reason) {
    case 'token_expired':
      return new RemoteTokenExpiredError();
    case 'ip_mismatch':
      return new RemoteTokenIpMismatchError();
    case 'token_exhausted':
      return new RemoteAuthError(reason, t('commands.config.remote.tokenExhausted'));
    case 'invalid_token':
    case 'decryption_failed':
      return new RemoteAuthError(reason, t('commands.config.remote.tokenInvalid'));
    default:
      return new RemoteAuthError(
        reason ?? 'unauthorized',
        t('commands.config.remote.tokenRejected', { reason: serverMessage })
      );
  }
}

/**
 * Optimistic-version conflict (HTTP 409). Carries the server's message
 * verbatim, it names the real current version (config.service.ts builds it),
 * so no client-side guess is layered on top.
 */
export class RemoteVersionConflictError extends Error {
  constructor(serverMessage: string) {
    super(serverMessage);
    this.name = 'RemoteVersionConflictError';
  }
}

/**
 * The config server could not be reached at all (DNS, refused connection,
 * timeout, or a 5xx). Distinct from auth/semantic failures: reads may fall
 * back to the offline cache on this error, writes must fail closed.
 */
export class RemoteUnreachableError extends Error {
  constructor(
    public readonly apiUrl: string,
    cause: unknown
  ) {
    super(t('commands.config.remote.unreachable', { server: apiUrl }), { cause });
    this.name = 'RemoteUnreachableError';
  }
}

/** Error codes (Node net/undici) that mean the server was never reached. */
const NETWORK_ERROR_CODES = new Set([
  'ECONNREFUSED',
  'ECONNRESET',
  'ENOTFOUND',
  'ETIMEDOUT',
  'EAI_AGAIN',
  'EPIPE',
]);

/**
 * Classify an error as network-class (server unreachable / not answering).
 * Walks the `.cause` chain, fetch wraps the socket error in a TypeError, and
 * undici nests its own codes one level deeper.
 */
export function isNetworkError(err: unknown): boolean {
  let current: unknown = err;
  const seen = new Set<unknown>();
  while (current && typeof current === 'object' && !seen.has(current)) {
    seen.add(current);
    if (current instanceof ConfigServerError) return current.status >= 500;
    if (isNetworkErrorNode(current)) return true;
    current = (current as { cause?: unknown }).cause;
  }
  return false;
}

/** One link of the cause chain: a socket/undici code, or fetch's TypeError. */
function isNetworkErrorNode(node: object): boolean {
  const code = (node as { code?: unknown }).code;
  if (typeof code === 'string' && (NETWORK_ERROR_CODES.has(code) || code.startsWith('UND_ERR'))) {
    return true;
  }
  return node instanceof TypeError && /fetch failed/i.test(node.message);
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
 * wrapping, the AES-GCM auth tag then fails. Surfaced instead of the raw
 * OperationError so the user gets an action (re-enroll) rather than a crypto
 * stack trace. Applies to every enrollment method (passkey and password).
 */
export class RemoteStaleSlotError extends Error {
  constructor() {
    super(t('commands.config.remote.staleSlot'));
    this.name = 'RemoteStaleSlotError';
  }
}

/**
 * The pulled blob will not open, even though the CEK unwrap succeeded.
 *
 * Distinct from RemoteStaleSlotError, which is an unwrap failure: here the slot
 * secret was correct and the store still handed back something this device
 * cannot read. The realistic cause is a store that already holds a config sealed
 * under a DIFFERENT CEK than the slot this device just enrolled against, i.e. a
 * second config for the same organization created from another enrollment.
 *
 * Before this existed the failure escaped as a raw WebCrypto
 * "OperationError: The operation failed for an operation-specific reason".
 */
export class RemoteConfigUndecryptableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RemoteConfigUndecryptableError';
  }
}

// ─── Adapter ────────────────────────────────────────────────────────────

export class RemoteConfigAdapter {
  constructor(
    private readonly remote: RemoteConfig,
    private readonly configName: string,
    private readonly tokenStorage: RemoteTokenStorage,
    private readonly secureStorage: SecureStorage,
    /** Test seam for the round-trip harness; production passes nothing. */
    private readonly transport?: Pick<ConfigServerFetchOptions, 'fetchImpl' | 'serverKey'>
  ) {}

  /**
   * Pull the latest config from the remote server: ONE request, under the token lease. The pull
   * response carries `server_secret`, so `/session` is not asked first (F8: every extra request
   * spends a token use).
   */
  pull(): Promise<PullResult> {
    return this.tokenStorage.withLease(this.configName, (lease) => this.pullLeased(lease));
  }

  private async pullLeased(lease: TokenLease): Promise<PullResult> {
    this.requireToken(lease);

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
        /** The epoch the blob was pushed in; the server's envelope always carries it. */
        sdkEpoch: number;
      };
      hmac: string | null;
      server_secret: string;
      sdk_derived: string;
    }>(lease, pullPath);
    const cek = await this.deriveCek(fromBase64(pullResp.data.server_secret), lease);

    // The session layer was sealed under the epoch the config was PUSHED in, and the pull
    // response carries that epoch's key (configs.ts derives it from the stored sdkEpoch).
    // The CURRENT epoch's key opened the blob only until the epoch window rolled over, then every
    // pull failed as "the server session layer would not open it" (2026-09-25, right after the
    // first remote enable).
    const pulledSdkDerived = await importAesKey(fromBase64(pullResp.data.sdk_derived));
    const pulledSdkEpoch = pullResp.data.envelope.sdkEpoch;

    // Decrypt: Layer 2 (CEK) + Layer 1 (SDK) Server-stored envelope is v2 (see Step 5). Until the server supports that,
    // fabricate empty commitments so the v2 shape is well-formed; selectiveDecrypt
    // still verifies HMAC + decrypts the blob successfully.
    const payload: EncryptedConfigPayload = {
      envelope: {
        envelopeVersion: 2,
        id: pullResp.data.envelope.configId,
        version: pullResp.data.envelope.version,
        sdkEpoch: pulledSdkEpoch,
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

    let decrypted: Awaited<ReturnType<typeof selectiveDecrypt>>;
    try {
      decrypted = await selectiveDecrypt(payload, cek, pulledSdkDerived);
    } catch (error) {
      throw this.classifyDecryptFailure(error, pullResp.data.envelope.configId);
    }

    // Rebuild the RdcConfig from the decrypted blob through the ONE shared reconstruction. This used to be a hand-written copy that had to "mirror"
    // fullConfigToRdcConfig exactly; keeping two copies in sync is precisely how
    // the explicit-undefined trap (and later the dropped-secret bug) reached production, so there is now a single implementation and both the CLI pull and the CEK rotation go through it.
    const config = fullConfigToRdcConfig(decrypted);

    return {
      config,
      version: pullResp.data.envelope.version,
      sdkEpoch: pulledSdkEpoch,
    };
  }

  /**
   * Push an updated config to the remote server: `/session` then PUT, under one token lease, the
   * PUT sending the token `/session` rotated to.
   */
  push(config: RdcConfig, currentVersion: number): Promise<PushResult> {
    return this.tokenStorage.withLease(this.configName, async (lease) => {
      this.requireToken(lease);
      const session = await this.fetchSession(lease);
      const cek = await this.deriveCek(session.serverSecret, lease);

      // Envelope + commitments + ciphertext are composed by the shared helper, so the CLI, the web console editor, and the CEK rotation flow all emit a byte-identical payload. Diverging here would fail the server precondition.
      const encrypted = await buildConfigPushPayload(config, {
        version: currentVersion + 1,
        sdkEpoch: session.sdkEpoch,
        sdkDerived: session.sdkDerived,
        cek,
      });

      // Push to server (server adds Layer 3)
      const pushPath = `/account/api/v1/configs/${this.remote.configId}`;
      const pushResp = await this.fetch<{ version: number }>(lease, pushPath, {
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
    });
  }

  /**
   * Test connectivity by calling the session endpoint.
   */
  async testConnection(): Promise<boolean> {
    try {
      await this.tokenStorage.withLease(this.configName, async (lease) => {
        this.requireToken(lease);
        await this.fetchSession(lease);
      });
      return true;
    } catch {
      return false;
    }
  }

  // ─── Private Helpers ──────────────────────────────────────────────────

  /**
   * Unwrap this device's config key (CEK) from its enrollment, without pulling
   * the config. The `--proxy` client seals it to an executor's session key so
   * the executor can open the config for that session (ProxyClient.ensureSession).
   * Rotates the config token like any other request.
   */
  unwrapCek(): Promise<CryptoKey> {
    return this.tokenStorage.withLease(this.configName, async (lease) => {
      this.requireToken(lease);
      const session = await this.fetchSession(lease);
      return this.deriveCek(session.serverSecret, lease);
    });
  }

  /** Refuse an operation whose lease holds no token, before any request. */
  private requireToken(lease: TokenLease): void {
    if (!lease.token) {
      throw new RemoteTokenExpiredError();
    }
  }

  /** Fetch session crypto material (server_secret, sdk_derived, sdkEpoch) */
  private async fetchSession(lease: TokenLease): Promise<SessionMaterial> {
    const resp = await this.fetch<{
      server_secret: string;
      sdk_derived: string;
      sdkEpoch: number;
    }>(lease, '/account/api/v1/configs/session', { method: 'POST' });

    return {
      serverSecret: fromBase64(resp.data.server_secret),
      sdkDerived: await importAesKey(fromBase64(resp.data.sdk_derived)),
      sdkEpoch: resp.data.sdkEpoch,
    };
  }

  /** Derive CEK from passkey_secret + server_secret */
  private async deriveCek(serverSecret: Uint8Array, lease: TokenLease) {
    const passkeySecretStr = await this.secureStorage.get(this.remote.storageKeyId);
    if (!passkeySecretStr) {
      throw new RemotePasskeySecretMissingError();
    }

    const passkeySecret = fromBase64(passkeySecretStr);
    const wrappingKey = await deriveWrappingKey(passkeySecret, serverSecret);

    const tokenData = lease.data;
    if (!tokenData?.wrappedCek) {
      throw new RemoteTokenExpiredError();
    }

    // A wrong slot secret (or a rotated CEK this device never re-wrapped for) surfaces here as an AES-GCM auth failure. Translate it into an actionable "re-enroll" message rather than leaking a raw OperationError.
    try {
      return await cekUnwrap(tokenData.wrappedCek, wrappingKey);
    } catch {
      throw new RemoteStaleSlotError();
    }
  }

  /**
   * Turn a selectiveDecrypt failure into something the user can act on.
   *
   * The two failure modes carry different meanings and different recoveries, and
   * the protocol does distinguish them: the HMAC is keyed by the CEK, so a verify
   * failure proves the blob was sealed under a different CEK than the slot handed
   * this device (a store holding another enrollment's config), while a failure
   * PAST the HMAC means the CEK layer opened and the server-derived session layer
   * did not.
   */
  private classifyDecryptFailure(error: unknown, configId: string): Error {
    const detail = error instanceof Error ? error.message : String(error);

    // The envelope-version guard already names its own problem.
    if (detail.includes('envelope version')) return error as Error;

    if (detail.includes('integrity check failed')) {
      return new RemoteConfigUndecryptableError(
        t('commands.config.remote.undecryptableIdentity', {
          configId,
          storeId: this.remote.storeId,
        })
      );
    }

    return new RemoteConfigUndecryptableError(
      t('commands.config.remote.undecryptableSession', { configId, detail })
    );
  }

  /**
   * One config server request under the operation's lease. The request sends the lease's current
   * token, and the token the server rotated to is persisted, and sent by the next request of the
   * operation, whether the request succeeded or failed: an error body carries the rotated token
   * too (F9), and dropping it spent one grace use of the old token per error.
   */
  private async fetch<T>(
    lease: TokenLease,
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    let resp: Awaited<ReturnType<typeof configServerFetch<T>>>;
    try {
      resp = await configServerFetch<T>(path, {
        ...options,
        ...this.transport,
        configToken: lease.token ?? '',
        serverUrl: this.remote.apiUrl,
      });
    } catch (error) {
      if (error instanceof ConfigServerError && error.newServerToken) {
        await lease.update(error.newServerToken);
      }
      throw classifyFetchError(error, this.remote.apiUrl);
    }
    if (resp.newServerToken) await lease.update(resp.newServerToken);
    return { data: resp.data };
  }
}

/**
 * Map a transport/server failure onto the adapter's typed taxonomy: 401 → the
 * RemoteAuthError for the server's stated reason, 409 → version conflict
 * (server message verbatim), and network-class failures (fetch TypeError, ECONN*, 5xx, including the
 * getServerKeyMaterial fetch inside configServerFetch) → unreachable, so read
 * paths can cache-serve and write paths fail closed. Everything else passes
 * through unchanged.
 */
function classifyFetchError(error: unknown, apiUrl: string): unknown {
  if (error instanceof ConfigServerError) {
    if (error.status === 401) return remoteAuthErrorFor(error.message);
    if (error.status === 409) return new RemoteVersionConflictError(error.message);
  }
  if (isNetworkError(error)) return new RemoteUnreachableError(apiUrl, error);
  return error;
}
