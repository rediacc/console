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
  derivePointerBlindingKey,
  ENVELOPE_VERSION,
  type EncryptedConfigPayload,
  fromBase64,
  importAesKey,
  selectiveDecrypt,
  unwrapEnvelopeConfigKey,
} from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import {
  buildConfigPushPayload,
  ConfigPolicyFieldError,
  envelopeConfigKeyWrap,
  type PushPrior,
  pathsToCommit,
} from '@rediacc/shared/config-schema';
import { ORG_ROLES, type PolicyOrgRole } from '@rediacc/shared/policy';
import { t } from '../i18n/index.js';
import { ConfigServerError } from '../services/config/config-server-client.js';
import {
  loadEffectivePolicy,
  type PolicyHighWater,
  parsePolicyRecordField,
} from '../services/config/policy-record.js';
import { outputService } from '../services/core/output.js';
import type { RdcConfig, RemoteConfig } from '../types/index.js';
import type { SecureStorage, SyncReadableSecureStorage } from '../utils/secure-storage.js';
import { clearSealKeyCache, readCachedSecret } from './config-seal-key.js';
import {
  findUnreachable,
  RemotePreconditionError,
  RemoteRollbackError,
  RemoteStaleSlotError,
  RemoteTokenExpiredError,
} from './remote-config-errors.js';
import { LeasedConfigFetch, type RemoteAdapterTransport } from './remote-config-fetch.js';
import {
  buildSyncRecord,
  classifyDecryptFailure,
  firstLegacyEnvelopeWarning,
  optionalFields,
  refuseRollback,
  unwrapDeviceCek,
} from './remote-config-support.js';
import type {
  PulledEnvelope,
  PullResult,
  PushOptions,
  PushResult,
  RemoteConfigEntry,
  RemotePolicyContext,
  RemoteVersionInfo,
  SessionMaterial,
  SessionPrincipal,
} from './remote-config-types.js';
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
export type { RemoteAdapterTransport } from './remote-config-fetch.js';
export type {
  PullResult,
  PushOptions,
  PushResult,
  RemoteConfigEntry,
  RemotePolicyContext,
  RemoteVersionInfo,
  SessionPrincipal,
} from './remote-config-types.js';

/**
 * The session's `orgRole` and `userEmail` as a principal, or undefined when the role is not one of
 * the policy's org roles (an older server, or a malformed answer). Never defaults to a role.
 */
export function sessionPrincipalOf(
  orgRole: unknown,
  userEmail: unknown
): SessionPrincipal | undefined {
  if (!(ORG_ROLES as readonly unknown[]).includes(orgRole)) return undefined;
  return {
    orgRole: orgRole as PolicyOrgRole,
    userEmail: typeof userEmail === 'string' ? userEmail : '',
  };
}

/** True for the storage `getSecureStorage()` hands out (the only one that also reads synchronously); false for an injected one. */
function isProcessStorage(storage: SecureStorage): storage is SyncReadableSecureStorage {
  return typeof (storage as Partial<SyncReadableSecureStorage>).getSync === 'function';
}

// ─── Adapter ────────────────────────────────────────────────────────────

export class RemoteConfigAdapter {
  private readonly http: LeasedConfigFetch;

  constructor(
    private readonly remote: RemoteConfig,
    private readonly configName: string,
    private readonly tokenStorage: RemoteTokenStorage,
    private readonly secureStorage: SecureStorage,
    private readonly transport?: RemoteAdapterTransport
  ) {
    this.http = new LeasedConfigFetch(remote, configName, transport);
  }

  /** A token lease whose writes seal the token file under this config's slot secret (D9). */
  private leased<T>(fn: (lease: TokenLease) => Promise<T>): Promise<T> {
    return this.tokenStorage.withLease(this.configName, fn, {
      slotKeyId: this.remote.storageKeyId,
    });
  }

  /**
   * Pull the latest config from the remote server: ONE request, under the token lease. The pull
   * response carries `server_secret`, so `/session` is not asked first (F8: every extra request
   * spends a token use).
   */
  pull(): Promise<PullResult> {
    return this.leased((lease) => this.pullLeased(lease));
  }

  private async pullLeased(lease: TokenLease): Promise<PullResult> {
    this.requireToken(lease);

    const pulled = await this.fetch<PulledEnvelope>(lease, this.configPath());
    const result = await this.open(lease, pulled.data);
    if ('policy' in pulled.data) result.policy = parsePolicyRecordField(pulled.data.policy);
    const { envelope } = pulled.data;

    const seen = this.syncRecord(lease);
    refuseRollback(this.remote.configId, this.configName, seen, envelope);
    // The blob opened under this device's CEK, so the store's generation is the one that CEK belongs to.
    await lease.recordSync(
      buildSyncRecord(
        this.bindingKey(),
        envelope,
        Math.max(seen?.highWater ?? 0, envelope.version),
        pulled.data.cekGeneration ?? seen?.cekGeneration,
        seen
      )
    );
    if (
      envelope.envelopeVersion !== ENVELOPE_VERSION &&
      firstLegacyEnvelopeWarning(this.configName)
    ) {
      outputService.warn(t('commands.config.remote.legacyEnvelope', { config: this.configName }));
    }
    return result;
  }

  /**
   * The generation this device's CEK belongs to: recorded when a blob opened under it, else the
   * store's from `/session`. The content key is wrapped under it, and the server refuses the push
   * when the store has rotated past it (409 `stale_cek_generation`, raised as RemoteStaleSlotError).
   * Neither known is refused here, never guessed.
   */
  private sealedGeneration(lease: TokenLease, session: SessionMaterial): number {
    const generation = this.syncRecord(lease)?.cekGeneration ?? session.cekGeneration;
    if (generation === undefined) {
      throw new Error(
        `Config "${this.configName}" cannot be pushed: neither this device nor the server named the CEK generation its key belongs to. Pull the config, then push again.`
      );
    }
    return generation;
  }

  /**
   * Read one archived version of the config (T16: `GET /configs/:id/versions/:v`), decrypted under
   * the same binding as a pull. An archive is old by definition, so the high-water mark neither
   * refuses it nor moves; a restore republishes it as a NEW version through `push`.
   */
  pullVersion(version: number): Promise<PullResult> {
    return this.leased(async (lease) => {
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
    return this.leased(async (lease) => {
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

  /**
   * The configs of this store visible to this device (GET /configs): what `config remote enable`
   * offers to attach to. Needs no configId, so a pointer that has not chosen one can call it.
   */
  listConfigs(): Promise<RemoteConfigEntry[]> {
    return this.leased(async (lease) => {
      this.requireToken(lease);
      const listed = await this.fetch<{ configs?: RemoteConfigEntry[] }>(
        lease,
        '/account/api/v1/configs'
      );
      return listed.data.configs ?? [];
    });
  }

  /**
   * What a local run of this config is judged with (agent/plans/PLAN-rmcp-decide.md D2), under one
   * token lease: `/session` names the token's member (org role and email) and yields the CEK, then
   * the effective policy (PLAN-rmcp-policy-record.md Design 5) is read through
   * `GET /configs/:id/policy`, the config's own record and the org-level config's record when this
   * config belongs to a team, both opened under that CEK and held against the policy high-water
   * marks in the token file. Never reads a `policy` field of the config document.
   *
   * Each context opened is kept in the token file's sync record. When the server is unreachable
   * (RemoteUnreachableError anywhere in the cause chain) the kept one is returned, so a read the
   * offline cache serves is judged as the same member it was online; with none kept, the
   * unreachable error propagates and the run is refused.
   *
   * @throws Error when the session names no valid org role: the caller is never guessed to be an owner
   */
  policyContext(): Promise<RemotePolicyContext> {
    return this.leased(async (lease) => {
      this.requireToken(lease);
      let context: RemotePolicyContext;
      try {
        context = await this.openPolicyContext(lease);
      } catch (error) {
        const kept = findUnreachable(error) ? this.syncRecord(lease)?.policyContext : undefined;
        if (!kept) throw error;
        return kept;
      }
      const seen = this.syncRecord(lease);
      if (seen) await lease.recordSync({ ...seen, policyContext: context });
      return context;
    });
  }

  /**
   * The principal and effective policy the last opened session recorded in the token file's sync
   * record, read with no request and no token renewal; undefined when this device never opened a
   * session for this binding. The judge reads it for a workstation command whose session could not
   * be opened (command-policy.ts SESSION_OPTIONAL_COMMANDS).
   */
  cachedPolicyContext(): Promise<RemotePolicyContext | undefined> {
    return this.leased((lease) => Promise.resolve(this.syncRecord(lease)?.policyContext));
  }

  /** The online half of `policyContext`: the session's principal and the effective policy. */
  private async openPolicyContext(lease: TokenLease): Promise<RemotePolicyContext> {
    // The high-water marks live in the sync record a pull writes, so a device that never pulled pulls first.
    if (!this.syncRecord(lease)) await this.pullLeased(lease);
    const session = await this.fetchSession(lease);
    if (!session.principal) {
      throw new Error(
        `The config server named no org role for config "${this.configName}", so its policy cannot be judged.`
      );
    }
    const cek = await this.deriveCek(session.serverSecret, lease);
    const orgConfigId = this.remote.teamId
      ? ((
          await this.fetch<{ configs?: RemoteConfigEntry[] }>(lease, '/account/api/v1/configs')
        ).data.configs?.find((entry) => !entry.teamId)?.configId ?? null)
      : this.remote.configId;
    const policy = await loadEffectivePolicy({
      storeId: this.remote.storeId,
      config: { configId: this.remote.configId, teamId: this.remote.teamId ?? null },
      orgConfigId,
      fetchRecord: (configId, teamId) => this.fetchPolicyRecord(lease, configId, teamId),
      key: cek,
      highWater: this.policyHighWater(lease),
    });
    return { principal: session.principal, policy };
  }

  /** `GET /configs/:id/policy`: the record, or null when the server holds none for that config. */
  private async fetchPolicyRecord(lease: TokenLease, configId: string, teamId: string | null) {
    const path = `/account/api/v1/configs/${configId}/policy${teamId ? `?teamId=${teamId}` : ''}`;
    try {
      const answer = await this.fetch<Record<string, unknown>>(lease, path);
      const { version, cekGeneration, blob } = answer.data;
      return parsePolicyRecordField({ version, cekGeneration, blob });
    } catch (error) {
      if (
        error instanceof ConfigServerError &&
        error.status === 404 &&
        error.code === 'policy_not_found'
      ) {
        return null;
      }
      throw error;
    }
  }

  /** The policy high-water marks of this config's token file, raised under the lease. */
  private policyHighWater(lease: TokenLease): PolicyHighWater {
    return {
      get: (key) => this.syncRecord(lease)?.policyHighWater?.[key],
      raise: async (key, version) => {
        const seen = this.syncRecord(lease);
        if (!seen) {
          throw new Error(
            `No sync record for config "${this.configName}": a policy is read only after a pull.`
          );
        }
        const marks = seen.policyHighWater ?? {};
        if (version <= (marks[key] ?? 0)) return;
        await lease.recordSync({ ...seen, policyHighWater: { ...marks, [key]: version } });
      },
    };
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
        ...(envelopeConfigKeyWrap(envelope) ?? {}),
      },
      encryptedBlob: data.configData,
      hmac: data.hmac,
    };

    let decrypted: Awaited<ReturnType<typeof selectiveDecrypt>>;
    try {
      decrypted = await selectiveDecrypt(payload, cek, sdkDerived, this.binding());
    } catch (error) {
      const failure = classifyDecryptFailure(
        this.remote.storeId,
        error,
        this.remote.configId,
        this.configName
      );
      throw await this.staleOr(lease, failure, data.cekGeneration);
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
   * PUT sending the token `/session` rotated to. The envelope is v4 (sealed under the config's
   * content key, AAD-bound to this device's pointer). What this device last saw of the server copy
   * (the token file's sync record) supplies the stored salt for tombstones, the stored content-key
   * wrap and, on a v3 or v2 store, the upgrade; see PushOptions.
   */
  push(config: RdcConfig, currentVersion: number, options: PushOptions = {}): Promise<PushResult> {
    // Before the lease and the first request: a remote config's policy is its own record, and a push that carries one is refused without spending a token.
    if (config.policy !== undefined) return Promise.reject(new ConfigPolicyFieldError());
    return this.leased(async (lease) => {
      this.requireToken(lease);
      const session = await this.fetchSession(lease);
      const cek = await this.deriveCek(session.serverSecret, lease);
      const prior = this.pushPrior(lease, currentVersion, options.base);
      const sealedGeneration = this.sealedGeneration(lease, session);

      // Envelope + commitments + ciphertext are composed by the shared helper, so the CLI, the web console editor, and the CEK rotation flow all emit a byte-identical payload. Diverging here would fail the server precondition.
      const encrypted = await buildConfigPushPayload(config, {
        version: currentVersion + 1,
        sdkEpoch: session.sdkEpoch,
        sdkDerived: session.sdkDerived,
        cek,
        cekGeneration: sealedGeneration,
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
        ...optionalFields({
          restoredFromVersion: options.restoredFromVersion,
          cekGeneration: sealedGeneration,
        }),
      };
      const pushed = await this.fetch<{ version: number; cekGeneration?: number }>(
        lease,
        `/account/api/v1/configs/${this.remote.configId}`,
        { method: 'PUT', body }
      ).catch(async (error: unknown) => {
        if (!(error instanceof RemotePreconditionError)) throw error;
        throw await this.namePaths(error, cek, encrypted.envelope, [config, options.base]);
      });

      await lease.recordSync(
        buildSyncRecord(
          this.bindingKey(),
          encrypted.envelope,
          pushed.data.version,
          sealedGeneration,
          this.syncRecord(lease)
        )
      );
      return { version: pushed.data.version };
    });
  }

  /**
   * What the server holds, as this device last saw it, when that is the version being replaced:
   * the stored envelope version, salt and (v4) content-key wrap, plus the document the edit came
   * from. Any other version
   * means this device has not seen the copy it overwrites; the push then goes without one (and a
   * version conflict or a precondition refusal follows).
   */
  private pushPrior(
    lease: TokenLease,
    currentVersion: number,
    base: RdcConfig | undefined
  ): PushPrior | undefined {
    const seen = this.syncRecord(lease);
    // A record kept across a re-enrollment may lack its salt until the next pull records it again.
    if (seen?.highWater !== currentVersion || seen.fckSalt === undefined) return undefined;
    return {
      envelopeVersion: seen.envelopeVersion,
      fckSalt: seen.fckSalt,
      ...(base ? { base } : {}),
      ...(seen.configKey ? { configKey: seen.configKey } : {}),
    };
  }

  /**
   * The server names refused paths by their STORED envelope key, a blinded pointer: under the
   * config's content key for a v4 store (the one the pushed envelope wraps), under the CEK for a v3
   * store. Map each back to the pointer it blinds under either key, among the paths this push and
   * its base commit; a key that matches none (a value another device added) stays as the server
   * sent it.
   */
  private async namePaths(
    error: RemotePreconditionError,
    cek: CryptoKey,
    pushed: EncryptedConfigPayload['envelope'],
    docs: (RdcConfig | undefined)[]
  ): Promise<RemotePreconditionError> {
    const contentKey = await unwrapEnvelopeConfigKey(pushed, cek, this.binding());
    const blindings = await Promise.all([
      derivePointerBlindingKey(contentKey, this.remote.configId),
      derivePointerBlindingKey(cek, this.remote.configId),
    ]);
    const names = new Map<string, string>();
    for (const doc of docs) {
      if (!doc) continue;
      for (const pointer of pathsToCommit(JSON.parse(JSON.stringify(doc)))) {
        for (const blinding of blindings) {
          names.set(await blindPointer(blinding, pointer), pointer);
        }
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
      await this.leased(async (lease) => {
        this.requireToken(lease);
        await this.fetchSession(lease);
      });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * The store's current CEK generation, from `/session` (T10). `rdc config rotate-cek` reads it before opening
   * the wizard and polls it afterwards, so the CLI learns the rotation finished from the server instead of asking.
   */
  storeGeneration(): Promise<number | undefined> {
    return this.leased(async (lease) => {
      this.requireToken(lease);
      return (await this.fetchSession(lease)).cekGeneration;
    });
  }

  // ─── Private Helpers ──────────────────────────────────────────────────

  /**
   * Unwrap this device's config key (CEK) from its enrollment, without pulling
   * the config. The `--proxy` client seals it to an executor's session key so
   * the executor can open the config for that session (ProxyClient.ensureSession).
   * Rotates the config token like any other request.
   */
  unwrapCek(): Promise<CryptoKey> {
    return this.leased(async (lease) => {
      this.requireToken(lease);
      const session = await this.fetchSession(lease);
      return this.deriveCek(session.serverSecret, lease);
    });
  }

  /** Refuse an operation whose lease holds no token, before any request. */
  private requireToken(lease: TokenLease): void {
    if (!lease.token) {
      throw new RemoteTokenExpiredError(this.configName);
    }
  }

  /** Fetch session crypto material (server_secret, sdk_derived, sdkEpoch) and the token's member. */
  private async fetchSession(lease: TokenLease): Promise<SessionMaterial> {
    const resp = await this.fetch<{
      server_secret: string;
      sdk_derived: string;
      sdkEpoch: number;
      cekGeneration?: number;
      orgRole?: unknown;
      userEmail?: unknown;
    }>(lease, '/account/api/v1/configs/session', { method: 'POST' });

    return {
      serverSecret: fromBase64(resp.data.server_secret),
      sdkDerived: await importAesKey(fromBase64(resp.data.sdk_derived)),
      sdkEpoch: resp.data.sdkEpoch,
      cekGeneration: resp.data.cekGeneration,
      principal: sessionPrincipalOf(resp.data.orgRole, resp.data.userEmail),
    };
  }

  /**
   * A blob that will not open, diagnosed against the CEK generations (T10, F11): when the store's
   * generation (the response's own, else `/session`'s) is newer than the one this device recorded,
   * its key was rotated away and the error is RemoteStaleSlotError, the decrypt failure kept as its
   * cause. Otherwise, or when either generation is unknown, `failure` stands as it was classified.
   */
  private async staleOr(
    lease: TokenLease,
    failure: Error,
    storeGeneration: number | undefined
  ): Promise<Error> {
    const recorded = this.syncRecord(lease)?.cekGeneration;
    if (recorded === undefined || failure instanceof RemoteStaleSlotError) return failure;
    let current = storeGeneration;
    if (current === undefined) {
      try {
        current = (await this.fetchSession(lease)).cekGeneration;
      } catch {
        return failure;
      }
    }
    return current !== undefined && current > recorded
      ? new RemoteStaleSlotError({ cause: failure }, this.configName)
      : failure;
  }

  /** Whether this device enrolled the config (the marker beside its token file); true when that cannot be read, so the key-gone wording stands (RemotePasskeySecretMissingError). */
  private async enrolledHere(): Promise<boolean> {
    try {
      return await this.tokenStorage.enrolledHere(this.configName);
    } catch {
      return true;
    }
  }

  /**
   * Derive CEK from passkey_secret + server_secret. The process's own secure storage (the one
   * `getSecureStorage()` hands out, the only one that reads synchronously) is read through the
   * per-process cache of config-seal-key.ts, which the token file's seal shares, so one operation
   * reads the slot secret once (D9). A secret that fails to open the CEK is read again once,
   * uncached: another step of this process may have replaced it since it was cached (an absence is
   * never cached, so a missing secret needs no second read). An injected storage is read directly.
   */
  private async deriveCek(serverSecret: Uint8Array, lease: TokenLease) {
    const unwrap = (secret: string | null) =>
      unwrapDeviceCek(secret, serverSecret, lease.data?.wrappedCek, this.configName, () =>
        this.enrolledHere()
      );
    if (!isProcessStorage(this.secureStorage)) {
      return unwrap(await this.secureStorage.get(this.remote.storageKeyId));
    }
    try {
      return await unwrap(await readCachedSecret(this.remote.storageKeyId));
    } catch (error) {
      if (!(error instanceof RemoteStaleSlotError)) throw error;
      clearSealKeyCache();
      return unwrap(await readCachedSecret(this.remote.storageKeyId));
    }
  }

  private fetch<T>(
    lease: TokenLease,
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<{ data: T }> {
    return this.http.fetch<T>(lease, path, options);
  }
}
