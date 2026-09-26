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
import { outputService } from '../services/core/output.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import type { SecureStorage } from '../utils/secure-storage.js';
import type { RemoteTokenStorage, SyncRecord, TokenLease } from './remote-token-storage.js';

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
function remoteAuthErrorFor(serverMessage: string): RemoteAuthError {
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
 * The server refused a push that drops committed paths without a matching tombstone (HTTP 409
 * `precondition_failed`, T9): the push was built from a copy older than the server's, or deletes
 * a value this device never saw. Not a version conflict: replaying the same push cannot succeed,
 * so it is raised as is, naming the paths.
 */
export class RemotePreconditionError extends Error {
  constructor(
    public readonly configName: string,
    public readonly paths: string[]
  ) {
    super(
      t('commands.config.remote.preconditionFailed', {
        config: configName,
        paths: paths.length > 0 ? paths.join(', ') : '-',
      })
    );
    this.name = 'RemotePreconditionError';
  }
}

/**
 * The server answered with a config older than one this device already saw (F1): a version below
 * the device's high-water mark, or the pre-v3 envelope after the device saw v3. Nothing is changed
 * locally; the offline cache is not served in its place.
 */
export class RemoteRollbackError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RemoteRollbackError';
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

/**
 * The server refused this config because this account is not a member of the team the config
 * belongs to (HTTP 403 `team_forbidden`, PLAN-config-team-scoping section 2.4). Membership is
 * checked on every request, so this is also what a device sees after its user left the team; the
 * read path then removes the offline copy (ruling E4). The rotated token in the refusal's body is
 * persisted before this is raised, so the device's token chain survives.
 */
export class RemoteTeamForbiddenError extends Error {
  constructor(public readonly configName: string) {
    super(t('commands.config.remote.teamForbidden', { config: configName }));
    this.name = 'RemoteTeamForbiddenError';
  }
}

/**
 * The team this config's pointer names is not a team of the store's organization (HTTP 404
 * `team_not_found`): a team id from another organization, or a team that no longer exists.
 */
class RemoteTeamNotFoundError extends Error {
  constructor(
    public readonly configName: string,
    public readonly teamId: string | undefined
  ) {
    super(t('commands.config.remote.teamNotFound', { config: configName, team: teamId ?? '-' }));
    this.name = 'RemoteTeamNotFoundError';
  }
}

/**
 * A write to a remote config was refused because its server is unreachable: the edit, a state
 * record included, is NOT saved anywhere (operator ruling 2026-09-25: offline writes to a remote
 * config fail closed; a local config never contacts a server). Names the config and the server so
 * a caller that treats the write as best-effort can still say why it was lost.
 */
export class RemoteWriteFailedClosedError extends Error {
  constructor(
    public readonly configName: string,
    public readonly apiUrl: string,
    cause: unknown
  ) {
    super(t('commands.config.remote.writeFailedClosed', { config: configName, server: apiUrl }), {
      cause,
    });
    this.name = 'RemoteWriteFailedClosedError';
  }
}

/** The RemoteUnreachableError anywhere in `error`'s cause chain, or undefined. */
export function findUnreachable(error: unknown): RemoteUnreachableError | undefined {
  let current: unknown = error;
  const seen = new Set<unknown>();
  while (current && typeof current === 'object' && !seen.has(current)) {
    seen.add(current);
    if (current instanceof RemoteUnreachableError) return current;
    current = (current as { cause?: unknown }).cause;
  }
  return undefined;
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
      throw classifyFetchError(error, this.remote, this.configName);
    }
    if (resp.newServerToken) await lease.update(resp.newServerToken);
    return { data: resp.data };
  }
}

/**
 * Map a transport/server failure onto the adapter's typed taxonomy: 401 → the
 * RemoteAuthError for the server's stated reason, 403 `team_forbidden` → not a member of the
 * config's team, 404 `team_not_found` → the pointer names no team of the organization, 409
 * `precondition_failed` → a deletion without a matching tombstone, any other 409 → version
 * conflict (server message verbatim), and network-class failures (fetch TypeError, ECONN*,
 * 5xx, including the getServerKeyMaterial fetch inside configServerFetch) → unreachable, so read
 * paths can cache-serve and write paths fail closed. Everything else passes through unchanged.
 */
function classifyFetchError(error: unknown, remote: RemoteConfig, configName: string): unknown {
  if (error instanceof ConfigServerError) {
    const answered = classifyServerAnswer(error, remote, configName);
    if (answered) return answered;
  }
  if (isNetworkError(error)) return new RemoteUnreachableError(remote.apiUrl, error);
  return error;
}

/** The typed error for a refusal the server answered with, or undefined to fall through. */
function classifyServerAnswer(
  error: ConfigServerError,
  remote: RemoteConfig,
  configName: string
): Error | undefined {
  if (error.status === 401) return remoteAuthErrorFor(error.message);
  if (error.status === 403 && error.code === 'team_forbidden') {
    return new RemoteTeamForbiddenError(configName);
  }
  if (error.status === 404 && error.code === 'team_not_found') {
    return new RemoteTeamNotFoundError(configName, remote.teamId);
  }
  if (error.status === 409 && error.code === 'precondition_failed') {
    return new RemotePreconditionError(configName, error.mismatchedPaths ?? []);
  }
  if (error.status === 409) return new RemoteVersionConflictError(error.message);
  return undefined;
}
