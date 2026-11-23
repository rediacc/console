/**
 * Config write-back for the container tier (agent/plans/PLAN-rmcp-writeback.md
 * Design 4, 5).
 *
 * A command the hosted executor dispatches runs against the config it pulled and
 * decrypted for the session. Its writes are pushed back to the config store here,
 * so a `repo create` that registered a repo has saved that registration (and the
 * repo's only credential) before its create job touches the host. A write that
 * cannot be saved throws, and the command fails before the host job.
 *
 * THREE PIECES:
 *
 *   ConfigChain        one config-token chain per container instance per (user,
 *                      team). Every config-store request goes through it, one at a
 *                      time, presenting the newest token and keeping the token the
 *                      store rotates to (an error body carries it too). A token the
 *                      store calls spent, expired or unknown is replaced by a fresh
 *                      mint, once per operation; a second refusal fails the write.
 *   SessionConfigStore the session's config as the store holds it: the document,
 *                      its version, and the stored envelope's salt (what a push
 *                      needs to prove a deletion with a tombstone). Writes to it are
 *                      serialized, one pull/session/PUT sequence at a time.
 *   pushWithReplay     the write itself: apply the edit to the newest copy, push it
 *                      with compare-and-swap, and on a version conflict pull the
 *                      store's copy and apply the edit again, as the CLI's own
 *                      RemoteResourceState does (services/config/resource-state.ts).
 *                      A conflict that outlasts every replay fails the write with
 *                      CONFIG_CONFLICT.
 *
 * The chain is minted writable (`write: true`); the account server honours that
 * only under a live grant for this session, executor and user, and applies the
 * team access table to every push as it does for any member.
 */

import type { EncryptedConfigPayload } from '@rediacc/shared/config-crypto';
import { ENVELOPE_VERSION, fromBase64, importAesKey } from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import {
  buildConfigPushPayload,
  decryptConfigPullPayload,
  type PushPrior,
  type RdcConfig,
} from '@rediacc/shared/config-schema';
import {
  ConfigConflictError,
  ConfigWriteFailedError,
  currentCommandName,
} from '../core/config-write-errors.js';
import { bindConfigWriteback, type ConfigWriteback } from '../core/request-context.js';
import { deadlineFetch, describeFetchError } from './account-fetch.js';
import { SessionError } from './sessions.js';

/** Version conflicts a write replays before it fails with CONFIG_CONFLICT: the first push plus three replays. */
export const MAX_CONFLICT_REPLAYS = 3;

/** The 401 reasons a fresh mint cures: the token was spent, expired, or is unknown to the store. */
const REMINT_REASONS = new Set(['token_exhausted', 'token_expired', 'invalid_token']);

/** What the account server hands an executor for one session: a config token and the configs it may reach. */
export interface ExecutorGrant {
  token: string;
  storeId: string;
  serverSecret: string;
  configs: { configId: string; teamId: string | null; version: number }[];
}

/** The config a session's commands run against, as the store addresses it (the v3 AAD binding). */
export interface ConfigTarget {
  storeId: string;
  configId: string;
  teamId: string | null;
}

/** Runs async sections one at a time, in arrival order. A failed section does not stop the next. */
export class SerialQueue {
  private tail: Promise<unknown> = Promise.resolve();

  run<T>(section: () => Promise<T>): Promise<T> {
    const result = this.tail.then(section);
    this.tail = result.catch(() => undefined);
    return result;
  }
}

/** One write's budget across its requests: a chain is re-minted at most once per operation. */
export interface ChainOperation {
  sessionId: string;
  reminted: boolean;
}

/** A config-store answer: the status and the parsed JSON body (an empty object when it had none). */
interface StoreAnswer {
  status: number;
  body: Record<string, unknown>;
}

/** A chain the store refused again after its one re-mint. */
export class ChainExhaustedError extends Error {
  constructor(readonly reason: string) {
    super(`the config token chain was refused (${reason}) again after a fresh mint`);
    this.name = 'ChainExhaustedError';
  }
}

export interface ConfigChainOptions {
  accountUrl: string;
  /** The executor's own account token, which mints the chain. */
  executorToken: string;
  userId: string;
  fetchImpl: typeof fetch;
}

/**
 * One config-token chain (see the module doc). Requests are serialized, so the
 * chain never has two holders racing one token, which is what spends a token's
 * grace uses and exhausts it.
 */
export class ConfigChain {
  private token: string | undefined;
  private readonly queue = new SerialQueue();
  private readonly accountUrl: string;
  private readonly fetch: typeof fetch;

  constructor(private readonly options: ConfigChainOptions) {
    this.accountUrl = options.accountUrl.replace(/\/+$/, '');
    this.fetch = deadlineFetch(options.fetchImpl);
  }

  /**
   * Mint a writable chain under `sessionId`'s grant and make it this chain's
   * token. Every new session mints, because the mint is where the account
   * server checks that the user granted THIS session; the previous token is
   * dropped, so the chain keeps one live token.
   */
  mint(sessionId: string): Promise<ExecutorGrant> {
    return this.queue.run(() => this.mintUnlocked(sessionId));
  }

  /** One config-store request on this chain; see ConfigChain. */
  request(path: string, init: { method?: string; body?: unknown }, op: ChainOperation) {
    return this.queue.run(() => this.requestUnlocked(path, init, op));
  }

  private async mintUnlocked(sessionId: string): Promise<ExecutorGrant> {
    const response = await this.fetch(`${this.accountUrl}/account/api/v1/configs/executor-token`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${this.options.executorToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ userId: this.options.userId, sessionId, write: true }),
    });
    if (!response.ok) {
      throw new SessionError(await describe(response, 'could not obtain a config token'));
    }
    const grant = (await response.json()) as ExecutorGrant;
    this.token = grant.token;
    return grant;
  }

  private async requestUnlocked(
    path: string,
    init: { method?: string; body?: unknown },
    op: ChainOperation
  ): Promise<StoreAnswer> {
    if (!this.token) await this.mintUnlocked(op.sessionId);
    for (;;) {
      const answer = await this.send(path, init);
      const reason = typeof answer.body.code === 'string' ? answer.body.code : '';
      if (answer.status !== 401 || !REMINT_REASONS.has(reason)) return answer;
      if (op.reminted) throw new ChainExhaustedError(reason);
      op.reminted = true;
      await this.mintUnlocked(op.sessionId);
    }
  }

  /** One request with the chain's current token; keeps the token the store rotated to. */
  private async send(
    path: string,
    init: { method?: string; body?: unknown }
  ): Promise<StoreAnswer> {
    const json = init.body === undefined ? undefined : JSON.stringify(init.body);
    const response = await this.fetch(`${this.accountUrl}${path}`, {
      method: init.method ?? 'GET',
      headers: {
        'X-Config-Token': this.token ?? '',
        'x-config-envelope': String(ENVELOPE_VERSION),
        ...(json === undefined ? {} : { 'content-type': 'application/json' }),
      },
      ...(json === undefined ? {} : { body: json }),
    });
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    // The store rotated the token before it answered, error or not: the old one is spent.
    if (typeof body.newServerToken === 'string') this.token = body.newServerToken;
    return { status: response.status, body };
  }
}

/** The envelope fields a pull answers with; the store's own copy of what was pushed. */
interface PulledEnvelope {
  configData: string;
  sdk_derived: string;
  envelope: EncryptedConfigPayload['envelope'] & { commitments: { fckSalt: string } };
  hmac: string | null;
}

/** What a push needs to know of the stored envelope it replaces (PushPrior without the document). */
type StoredEnvelope = Omit<PushPrior, 'base'>;

export interface SessionConfigStoreOptions {
  chain: ConfigChain;
  sessionId: string;
  target: ConfigTarget;
  /** The session's granted config key. */
  cek: CryptoKey;
}

/**
 * The session's config as the store holds it, and the writeback every request
 * scope around it saves through (see the module doc). `config` is always the
 * store's document at `version`, so it is also the base a push proves its
 * deletions against.
 */
export class SessionConfigStore implements ConfigWriteback {
  private readonly queue = new SerialQueue();
  private document!: RdcConfig;
  private storedVersion = 0;
  private stored!: StoredEnvelope;

  private constructor(private readonly options: SessionConfigStoreOptions) {}

  /** Pull the session's config through `options.chain` and open it with the session's key. */
  static async open(options: SessionConfigStoreOptions): Promise<SessionConfigStore> {
    const store = new SessionConfigStore(options);
    const op: ChainOperation = { sessionId: options.sessionId, reminted: false };
    let refused: string | undefined;
    try {
      refused = await store.pull(op);
    } catch (error) {
      refused = error instanceof Error ? error.message : String(error);
    }
    if (refused) {
      throw new SessionError(
        `The executor could not fetch the config: ${refused.replace(/\.$/, '')}.`
      );
    }
    return store;
  }

  /** The store's document, at `version`. */
  get config(): RdcConfig {
    return this.document;
  }

  get version(): number {
    return this.storedVersion;
  }

  /** Save `edit`, serialized with every other write of this session's config. */
  write(edit: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    return this.queue.run(() => this.pushWithReplay(edit));
  }

  /**
   * The write without the serialization `write` adds: apply `edit` to the newest
   * copy and push it, replaying a version conflict on a fresh pull. Exposed so
   * a test can show what the serialization prevents; production calls `write`.
   */
  async pushWithReplay(edit: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
    const op: ChainOperation = { sessionId: this.options.sessionId, reminted: false };
    for (let conflicts = 0; ; conflicts++) {
      const base = this.document;
      // On a copy: an edit may mutate the document it is given, and `base` must stay the store's copy for the tombstones.
      const next = edit(structuredClone(base));
      if (JSON.stringify(next) === JSON.stringify(base)) return base;
      const pushed = await this.pushOnce(next, base, op);
      if (pushed !== 'conflict') return pushed;
      if (conflicts === MAX_CONFLICT_REPLAYS) {
        throw new ConfigConflictError(currentCommandName(), conflicts + 1);
      }
      const refused = await this.ask(() => this.pull(op));
      if (refused) throw new ConfigWriteFailedError(currentCommandName(), refused);
    }
  }

  /** `/session` then PUT of `next`, proving every path `base` holds and `next` drops. */
  private async pushOnce(
    next: RdcConfig,
    base: RdcConfig,
    op: ChainOperation
  ): Promise<RdcConfig | 'conflict'> {
    const { chain, target, cek } = this.options;
    const session = await this.ask(() =>
      chain.request('/account/api/v1/configs/session', { method: 'POST' }, op)
    );
    if (session.status >= 400) throw this.refusal(session);
    const sdkEpoch = Number(session.body.sdkEpoch);
    const sdkDerived = await importAesKey(fromBase64(String(session.body.sdk_derived)));
    const version = this.storedVersion + 1;
    const encrypted = await buildConfigPushPayload(next, {
      version,
      sdkEpoch,
      sdkDerived,
      cek,
      storeId: target.storeId,
      ...(target.teamId ? { teamId: target.teamId } : {}),
      prior: { ...this.stored, base },
    });
    const answer = await this.ask(() =>
      chain.request(
        `/account/api/v1/configs/${encodeURIComponent(target.configId)}`,
        {
          method: 'PUT',
          body: {
            ...(target.teamId ? { teamId: target.teamId } : {}),
            version,
            encryptedBlob: encrypted.encryptedBlob,
            sdkEpoch,
            envelope: encrypted.envelope,
          },
        },
        op
      )
    );
    // A 409 without a code is the compare-and-swap lost; a coded one (precondition_failed, stale_cek_generation) is a refusal no replay cures.
    if (answer.status === 409 && answer.body.code === undefined) return 'conflict';
    if (answer.status >= 400) throw this.refusal(answer);
    const stored = typeof answer.body.version === 'number' ? answer.body.version : version;
    this.replace({ ...next, version: stored }, stored, {
      envelopeVersion: encrypted.envelope.envelopeVersion,
      fckSalt: encrypted.envelope.commitments.fckSalt,
    });
    return this.document;
  }

  /**
   * Pull the store's copy and make it this store's document. A refusal is
   * answered as its reason rather than thrown, so `open` reports it as a session
   * failure (the loader's historical 404) and a write as a failed write; a
   * transport failure is thrown for the caller to classify.
   */
  private async pull(op: ChainOperation): Promise<string | undefined> {
    const { chain, target, cek } = this.options;
    const query = target.teamId ? `?teamId=${encodeURIComponent(target.teamId)}` : '';
    const answer = await chain.request(
      `/account/api/v1/configs/${encodeURIComponent(target.configId)}${query}`,
      {},
      op
    );
    if (answer.status >= 400) return storeReason(answer, 'the config pull');
    const pulled = answer.body as unknown as PulledEnvelope;
    // The key is the SESSION's, never the executor's. The binding is the config the executor asked for: a blob the store serves for another store, config or team does not open (envelope v3 AAD).
    const decrypted = await decryptConfigPullPayload(
      { envelope: pulled.envelope, encryptedBlob: pulled.configData, hmac: pulled.hmac },
      {
        cek,
        sdkDerived: await importAesKey(fromBase64(pulled.sdk_derived)),
        binding: { storeId: target.storeId, configId: target.configId, teamId: target.teamId },
      }
    );
    const version = pulled.envelope.version;
    this.replace({ ...fullConfigToRdcConfig(decrypted), version }, version, {
      envelopeVersion: pulled.envelope.envelopeVersion,
      fckSalt: pulled.envelope.commitments.fckSalt,
    });
    return undefined;
  }

  /** Re-seat on the store's copy, and bind it so the next request scope around it saves here too. */
  private replace(config: RdcConfig, version: number, stored: StoredEnvelope): void {
    this.document = config;
    this.storedVersion = version;
    this.stored = stored;
    bindConfigWriteback(config, this);
  }

  /** A chain request (or a pull), its transport failures turned into a failed write. */
  private async ask<T>(send: () => Promise<T>): Promise<T> {
    try {
      return await send();
    } catch (error) {
      if (error instanceof ConfigWriteFailedError) throw error;
      // A spent chain and a refused re-mint (a lapsed grant) are not cured by retrying; an unanswered request may be.
      const refused = error instanceof ChainExhaustedError || error instanceof SessionError;
      const reason = refused ? (error as Error).message : describeFetchError(error);
      throw new ConfigWriteFailedError(currentCommandName(), reason, { retryable: !refused });
    }
  }

  private refusal(answer: StoreAnswer): ConfigWriteFailedError {
    return new ConfigWriteFailedError(currentCommandName(), storeReason(answer, 'the config push'));
  }
}

/** The store's own words for a refusal: its error and code, with the status. */
function storeReason(answer: StoreAnswer, what: string): string {
  const error = typeof answer.body.error === 'string' ? answer.body.error : undefined;
  const code = typeof answer.body.code === 'string' ? ` (${answer.body.code})` : '';
  return `${what} was refused with HTTP ${answer.status}${error ? `: ${error}` : ''}${code}`;
}

async function describe(response: Response, what: string): Promise<string> {
  const body = await response.text().catch(() => '');
  const detail = body.slice(0, 200);
  return `The executor ${what} from the account server (${response.status})${detail ? `: ${detail}` : ''}.`;
}
