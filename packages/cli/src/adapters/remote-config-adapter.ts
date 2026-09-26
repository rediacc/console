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
  blindPointer,
  type ConfigBinding,
  cekUnwrap,
  derivePointerBlindingKey,
  deriveWrappingKey,
  ENVELOPE_VERSION,
  type EncryptedConfigPayload,
  type FieldCommitments,
  fromBase64,
  importAesKey,
  selectiveDecrypt,
} from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import {
  buildConfigPushPayload,
  type PushPrior,
  pathsToCommit,
} from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import {
  ConfigServerError,
  type ConfigServerFetchOptions,
  configServerFetch,
} from '../services/config/config-server-client.js';
import {
  loginTokenFor,
  REFRESHABLE_AUTH_REASONS,
  RemoteTokenRefreshError,
  refreshDeviceToken,
} from '../services/config/device-token-refresh.js';
import { outputService } from '../services/core/output.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import type { SecureStorage } from '../utils/secure-storage.js';
import {
  classifyFetchError,
  isNetworkError,
  RemoteAuthError,
  RemoteConfigUndecryptableError,
  RemotePasskeySecretMissingError,
  RemotePreconditionError,
  RemoteRollbackError,
  RemoteStaleSlotError,
  RemoteTeamForbiddenError,
  RemoteTeamNotFoundError,
  RemoteTokenExpiredError,
} from './remote-config-errors.js';
import type { RemoteTokenStorage, SyncRecord, TokenLease } from './remote-token-storage.js';

export {
  findUnreachable,
  isNetworkError,
  RemoteAuthError,
  RemoteConfigUndecryptableError,
  RemotePasskeySecretMissingError,
  RemotePreconditionError,
  RemoteRollbackError,
  RemoteStaleSlotError,
  RemoteTeamForbiddenError,
  RemoteTokenExpiredError,
  RemoteTokenIpMismatchError,
  RemoteUnreachableError,
  RemoteVersionConflictError,
  RemoteWriteFailedClosedError,
} from './remote-config-errors.js';

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

/** One archived version of a config, as `GET /configs/:id/versions` lists it. */
export interface RemoteVersionInfo {
  version: number;
  /** When a newer push replaced it and the server archived it (ISO 8601). */
  archivedAt: string;
  /** The SDK epoch the version was sealed under. */
  sdkEpoch: number;
}

export interface PushOptions {
  /**
   * The document this edit was made from, as pulled at `currentVersion` (a remote config's cache
   * file). A committed path it holds that the pushed document drops is deleted with a tombstone
   * proving this device saw its value (T9); without a base, a push can only add and change.
   */
  base?: RdcConfig;
  /** A restore (T16): the version whose content this push re-publishes, for the audit trail. */
  restoredFromVersion?: number;
}

/** A pull (or version read) response: the blob with the org layer removed, and its envelope. */
interface PulledEnvelope {
  configData: string;
  envelope: {
    envelopeVersion: 2 | 3;
    configId: string;
    version: number;
    teamId: string | null;
    lastModified: string;
    commitments: FieldCommitments;
    /** The epoch the blob was pushed in; the server's envelope always carries it. */
    sdkEpoch: number;
  };
  hmac: string | null;
  server_secret: string;
  sdk_derived: string;
}

/** Session crypto material from the server */
interface SessionMaterial {
  serverSecret: Uint8Array;
  sdkDerived: Awaited<ReturnType<typeof importAesKey>>;
  sdkEpoch: number;
}

// ─── Adapter ────────────────────────────────────────────────────────────

/** Test seams for the round-trip harness; production passes nothing. */
export interface RemoteAdapterTransport
  extends Pick<ConfigServerFetchOptions, 'fetchImpl' | 'serverKey'> {
  /**
   * The login token this device holds for `remote.apiUrl`. Production reads the stored
   * `rdc subscription login` token (loginTokenFor); a harness device supplies its own.
   */
  loginToken?: () => string | undefined;
}

export class RemoteConfigAdapter {
  /** Operations (by their lease) that already renewed the config token: one renewal each (T11). */
  private readonly refreshed = new WeakSet<TokenLease>();

  constructor(
    private readonly remote: RemoteConfig,
    private readonly configName: string,
    private readonly tokenStorage: RemoteTokenStorage,
    private readonly secureStorage: SecureStorage,
    private readonly transport?: RemoteAdapterTransport
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

    const pulled = await this.fetch<PulledEnvelope>(lease, this.configPath());
    const result = await this.open(lease, pulled.data);
    const { envelope } = pulled.data;

    // The version is authentic (the AAD binds it), so it can be held against what this device saw.
    const seen = this.syncRecord(lease);
    if (seen && envelope.version < seen.highWater) {
      throw new RemoteRollbackError(
        t('commands.config.remote.rollback', {
          configId: this.remote.configId,
          version: String(envelope.version),
          highWater: String(seen.highWater),
        })
      );
    }
    if (
      seen?.envelopeVersion === ENVELOPE_VERSION &&
      envelope.envelopeVersion !== ENVELOPE_VERSION
    ) {
      throw new RemoteRollbackError(
        t('commands.config.remote.envelopeDowngrade', { configId: this.remote.configId })
      );
    }
    await lease.recordSync({
      binding: this.bindingKey(),
      highWater: Math.max(seen?.highWater ?? 0, envelope.version),
      envelopeVersion: envelope.envelopeVersion,
      fckSalt: envelope.commitments.fckSalt,
    });
    if (envelope.envelopeVersion !== ENVELOPE_VERSION) {
      outputService.warn(
        t('commands.config.remote.legacyEnvelope', { configId: this.remote.configId })
      );
    }
    return result;
  }

  /**
   * Read one archived version of the config (T16: `GET /configs/:id/versions/:v`), decrypted under
   * the same binding as a pull. An archive is old by definition, so the high-water mark neither
   * refuses it nor moves; a restore republishes it as a NEW version through `push`.
   */
  pullVersion(version: number): Promise<PullResult> {
    return this.tokenStorage.withLease(this.configName, async (lease) => {
      this.requireToken(lease);
      const path = `/account/api/v1/configs/${this.remote.configId}/versions/${version}${
        this.remote.teamId ? `?teamId=${this.remote.teamId}` : ''
      }`;
      const pulled = await this.fetch<PulledEnvelope>(lease, path);
      const result = await this.open(lease, pulled.data);
      if (result.version !== version) {
        throw new RemoteRollbackError(
          t('commands.config.remote.rollback', {
            configId: this.remote.configId,
            version: String(result.version),
            highWater: String(version),
          })
        );
      }
      return result;
    });
  }

  /**
   * The version history the server keeps of this config (`GET /configs/:id/versions`, newest
   * first): the versions a restore can bring back. The current version is not among them.
   */
  listVersions(): Promise<RemoteVersionInfo[]> {
    return this.tokenStorage.withLease(this.configName, async (lease) => {
      this.requireToken(lease);
      const path = `/account/api/v1/configs/${this.remote.configId}/versions${
        this.remote.teamId ? `?teamId=${this.remote.teamId}` : ''
      }`;
      // The server's `createdAt` is the archive row's: the moment the next push replaced that version.
      const listed = await this.fetch<{
        versions?: { version: number; createdAt: string; sdkEpoch: number }[];
      }>(lease, path);
      return (listed.data.versions ?? []).map(({ version, createdAt, sdkEpoch }) => ({
        version,
        archivedAt: createdAt,
        sdkEpoch,
      }));
    });
  }

  /** The pull path of this config (its team in the query when it has one). */
  private configPath(): string {
    return `/account/api/v1/configs/${this.remote.configId}${
      this.remote.teamId ? `?teamId=${this.remote.teamId}` : ''
    }`;
  }

  /** What this device expects every blob of its config to be sealed for: its own pointer. */
  private binding(): ConfigBinding {
    return {
      storeId: this.remote.storeId,
      configId: this.remote.configId,
      teamId: this.remote.teamId ?? null,
    };
  }

  private bindingKey(): string {
    return `${this.remote.storeId}/${this.remote.configId}/${this.remote.teamId ?? ''}`;
  }

  /** The lease's sync record when it is about this config (a re-pointed token file's is not). */
  private syncRecord(lease: TokenLease): SyncRecord | undefined {
    const record = lease.sync;
    return record?.binding === this.bindingKey() ? record : undefined;
  }

  /** Decrypt a pull-shaped response under this device's binding. */
  private async open(lease: TokenLease, data: PulledEnvelope): Promise<PullResult> {
    const cek = await this.deriveCek(fromBase64(data.server_secret), lease);

    // The session layer was sealed under the epoch the config was PUSHED in, and the pull response carries that epoch's key (configs.ts derives it from the stored sdkEpoch). The CURRENT epoch's key opened the blob only until the epoch window rolled over, then every pull failed as "the server session layer would not open it" (2026-09-25, right after the first remote enable).
    const sdkDerived = await importAesKey(fromBase64(data.sdk_derived));
    const { envelope } = data;
    const payload: EncryptedConfigPayload = {
      envelope: {
        envelopeVersion: envelope.envelopeVersion,
        id: envelope.configId,
        version: envelope.version,
        sdkEpoch: envelope.sdkEpoch,
        teamId: envelope.teamId ?? undefined,
        lastModified: envelope.lastModified,
        commitments: envelope.commitments,
      },
      encryptedBlob: data.configData,
      hmac: data.hmac,
    };

    let decrypted: Awaited<ReturnType<typeof selectiveDecrypt>>;
    try {
      decrypted = await selectiveDecrypt(payload, cek, sdkDerived, this.binding());
    } catch (error) {
      throw this.classifyDecryptFailure(error, this.remote.configId);
    }

    // Rebuild the RdcConfig from the decrypted blob through the ONE shared reconstruction. This used to be a hand-written copy that had to "mirror" fullConfigToRdcConfig exactly; keeping two copies in sync is precisely how the explicit-undefined trap (and later the dropped-secret bug) reached production, so there is now a single implementation and both the CLI pull and the CEK rotation go through it.
    return {
      config: fullConfigToRdcConfig(decrypted),
      version: envelope.version,
      sdkEpoch: envelope.sdkEpoch,
    };
  }

  /**
   * Push an updated config to the remote server: `/session` then PUT, under one token lease, the
   * PUT sending the token `/session` rotated to. The envelope is v3 (AAD-bound to this device's
   * pointer). What this device last saw of the server copy (the token file's sync record) supplies
   * the stored salt for tombstones and, on a v2 store, the upgrade; see PushOptions.
   */
  push(config: RdcConfig, currentVersion: number, options: PushOptions = {}): Promise<PushResult> {
    return this.tokenStorage.withLease(this.configName, async (lease) => {
      this.requireToken(lease);
      const session = await this.fetchSession(lease);
      const cek = await this.deriveCek(session.serverSecret, lease);
      const prior = this.pushPrior(lease, currentVersion, options.base);

      // Envelope + commitments + ciphertext are composed by the shared helper, so the CLI, the web console editor, and the CEK rotation flow all emit a byte-identical payload. Diverging here would fail the server precondition.
      const encrypted = await buildConfigPushPayload(config, {
        version: currentVersion + 1,
        sdkEpoch: session.sdkEpoch,
        sdkDerived: session.sdkDerived,
        cek,
        storeId: this.remote.storeId,
        ...(this.remote.teamId ? { teamId: this.remote.teamId } : {}),
        ...(prior ? { prior } : {}),
      });

      // Push to server (server adds Layer 3)
      const body = {
        teamId: this.remote.teamId,
        version: currentVersion + 1,
        encryptedBlob: encrypted.encryptedBlob,
        sdkEpoch: session.sdkEpoch,
        envelope: encrypted.envelope,
        ...(options.restoredFromVersion === undefined
          ? {}
          : { restoredFromVersion: options.restoredFromVersion }),
      };
      const pushed = await this.fetch<{ version: number }>(
        lease,
        `/account/api/v1/configs/${this.remote.configId}`,
        { method: 'PUT', body }
      ).catch(async (error: unknown) => {
        if (!(error instanceof RemotePreconditionError)) throw error;
        throw await this.namePaths(error, cek, [config, options.base]);
      });

      await lease.recordSync({
        binding: this.bindingKey(),
        highWater: pushed.data.version,
        envelopeVersion: ENVELOPE_VERSION,
        fckSalt: encrypted.envelope.commitments.fckSalt,
      });
      return { version: pushed.data.version };
    });
  }

  /**
   * What the server holds, as this device last saw it, when that is the version being replaced:
   * the stored envelope version and salt, plus the document the edit came from. Any other version
   * means this device has not seen the copy it overwrites; the push then goes without one (and a
   * version conflict or a precondition refusal follows).
   */
  private pushPrior(
    lease: TokenLease,
    currentVersion: number,
    base: RdcConfig | undefined
  ): PushPrior | undefined {
    const seen = this.syncRecord(lease);
    if (seen?.highWater !== currentVersion) return undefined;
    return {
      envelopeVersion: seen.envelopeVersion,
      fckSalt: seen.fckSalt,
      ...(base ? { base } : {}),
    };
  }

  /**
   * The server names refused paths by their envelope key, which in v3 is a blinded pointer. Map
   * each back to the pointer it blinds, among the paths this push and its base commit; a key that
   * matches none (a value another device added) stays as the server sent it.
   */
  private async namePaths(
    error: RemotePreconditionError,
    cek: CryptoKey,
    docs: (RdcConfig | undefined)[]
  ): Promise<RemotePreconditionError> {
    const blinding = await derivePointerBlindingKey(cek, this.remote.configId);
    const names = new Map<string, string>();
    for (const doc of docs) {
      if (!doc) continue;
      for (const pointer of pathsToCommit(JSON.parse(JSON.stringify(doc)))) {
        names.set(await blindPointer(blinding, pointer), pointer);
      }
    }
    return new RemotePreconditionError(
      error.configName,
      error.paths.map((key) => names.get(key) ?? key)
    );
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
   * the protocol does distinguish them: the CEK layer's tag (under the envelope
   * v3 AAD, or the v2 blob HMAC) fails when the blob is not the one sealed for
   * this config, version and team, or was sealed under a different CEK than the
   * slot handed this device, while a failure PAST it means the CEK layer opened
   * and the server-derived session layer did not.
   */
  private classifyDecryptFailure(error: unknown, configId: string): Error {
    const detail = error instanceof Error ? error.message : String(error);

    // The envelope-version guard already names its own problem.
    if (detail.includes('envelope version')) return error as Error;

    if (error instanceof Error && error.name === 'ConfigIntegrityError') {
      return new RemoteConfigUndecryptableError(
        t('commands.config.remote.integrityFailed', {
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
   *
   * A 401 whose reason a new token cures (REFRESHABLE_AUTH_REASONS: expired, spent, bound to
   * another address, unknown) renews the token with the login token, still under the lease, and
   * sends the refused request once more (T11, D4). One renewal per operation: a second refusal
   * after it is raised as it came.
   */
  private async fetch<T>(
    lease: TokenLease,
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    try {
      return await this.fetchOnce<T>(lease, path, options);
    } catch (error) {
      if (
        !(error instanceof RemoteAuthError) ||
        !REFRESHABLE_AUTH_REASONS.has(error.reason) ||
        this.refreshed.has(lease)
      ) {
        throw error;
      }
      this.refreshed.add(lease);
      await this.renewToken(lease, error);
      return this.fetchOnce<T>(lease, path, options);
    }
  }

  private async fetchOnce<T>(
    lease: TokenLease,
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    let resp: Awaited<ReturnType<typeof configServerFetch<T>>>;
    try {
      resp = await configServerFetch<T>(path, {
        ...options,
        fetchImpl: this.transport?.fetchImpl,
        serverKey: this.transport?.serverKey,
        configToken: lease.token ?? '',
        serverUrl: this.remote.apiUrl,
      });
    } catch (error) {
      if (error instanceof ConfigServerError && error.newServerToken) {
        await lease.update(error.newServerToken);
      }
      throw classifyFetchError(error, this.remote, this.configName);
    }
    if (resp.newServerToken) await lease.update(resp.newServerToken);
    return { data: resp.data };
  }

  /**
   * Replace the lease's dead config token with one the account server mints for this device's
   * login (POST /configs/device-token/refresh). The token file keeps its wrapped CEK and sync
   * record; only `token` changes. Without a login token for this server, or when the renewal is
   * refused, the operation fails with the refusal's remedy (the original 401 kept as the cause, or
   * its message extended with both remedies when there was nothing to renew with).
   */
  private async renewToken(lease: TokenLease, refusal: RemoteAuthError): Promise<void> {
    const loginToken = this.transport?.loginToken
      ? this.transport.loginToken()
      : loginTokenFor(this.remote.apiUrl);
    if (!loginToken) {
      refusal.message = `${refusal.message}\n${t('commands.config.remote.tokenRefresh.noLogin', {
        apiUrl: this.remote.apiUrl,
      })}`;
      throw refusal;
    }
    let token: string;
    try {
      token = await refreshDeviceToken(this.remote, loginToken, {
        fetchImpl: this.transport?.fetchImpl,
        serverKey: this.transport?.serverKey,
      });
    } catch (error) {
      throw this.renewalFailure(error, refusal);
    }
    await lease.update(token);
  }

  /** The error a failed renewal raises; see refreshDeviceToken for what it passes through. */
  private renewalFailure(error: unknown, refusal: RemoteAuthError): unknown {
    if (error instanceof RemoteTokenRefreshError) return error;
    const e = error as { status?: unknown; code?: unknown } | null;
    if (e?.status === 403 && e.code === 'team_forbidden') {
      return new RemoteTeamForbiddenError(this.configName);
    }
    if (e?.status === 404 && e.code === 'team_not_found') {
      return new RemoteTeamNotFoundError(this.configName, this.remote.teamId);
    }
    // The server answered the config request a moment ago, so a renewal that could not reach it is reported as the refusal it was meant to cure (never as unreachable: that would let a read serve the offline cache after a 401).
    if (isNetworkError(error)) return Object.assign(refusal, { cause: error });
    return error;
  }
}
