/**
 * The executor's agent-grant sessions (agent/plans/PLAN-rmcp-agent-grants.md Design 4).
 *
 * One session per GRANT, never per user: two grants of one user hold two sessions with two configs, so a
 * call under the team-B grant can never run against team A's config (the cross-team regression the
 * user-keyed sessions of sessions.ts cannot rule out).
 *
 * The agent secret `S` arrives with every call (the MCP Worker passes it through the Durable Object) and is
 * used for exactly two things inside one call: proving it is the grant's secret, and, when the session is
 * missing, opening it. It is never stored, never logged and never part of an error message. What a session
 * holds is what the account server's `POST /configs/agent-session` answered, with `S` already spent:
 *
 *   - the config's content key, unwrapped into a NON-extractable AES-GCM key (the container never holds the
 *     org CEK for an agent principal, D56), kept in this process only;
 *   - the rotating config-token chain the answer carried (`X-Config-Token`), which fetches that one config;
 *   - the SHA-256 of the auth tag, so a later call is checked against the grant without keeping `S`;
 *   - the grant's scope and overrides, and its expiry.
 *
 * The decrypted config is cached under `(grantId, configVersion)`. Every call asks the store for the
 * config's current version (a listing read with no blob) and re-pulls on a mismatch, as the user-keyed
 * loader does (Design 5 of PLAN-rmcp-executor-hardening). After a container sleep the store is empty and
 * the next call rebuilds the session from its `S`, one `agent-session` call.
 *
 * A REFUSED open (the account's one indistinguishable 403) drops the session: a grant the account will not
 * serve is not held. An unavailable account server is not a refusal, it throws {@link AgentSessionUnavailable}
 * and the session is kept.
 *
 * NO WRITEBACK. The session holds the content key, not the CEK a push must wrap it under, so its config is
 * handed out unbound: a command that writes the spec is refused by the request scope before any host job
 * (CONFIG_WRITE_UNAVAILABLE, services/core/request-context.ts), and a state write lives for the request only.
 *
 * NO POLICY, SO EVERY CALL IS REFUSED FOR NOW. The org and team policy records are sealed under the CEK
 * (PLAN-rmcp-policy-record.md), which an agent grant never holds, and the `agent-session` answer carries
 * neither a policy nor the grant user's org role. The session therefore binds no effective policy, and its
 * principal is a `member`: `decide` answers "No policy is configured; members may not run ..." for every
 * command, which is the safe direction. Reading the role as `owner` instead would run an org that DOES have
 * a policy as if it had none (its deny rules invisible to the executor). The grant needs a policy it can open
 * before any tool can run under it; see the AG-X report.
 */

import type { EncryptedConfigPayload } from '@rediacc/shared/config-crypto';
import {
  AGENT_GRANT_SECRET_BYTES,
  deriveAuthTag,
  ENVELOPE_VERSION,
  fromBase64,
  hashAuthTag,
  importAesKey,
  selectiveDecryptWithConfigKey,
  unwrapConfigKeyForAgentGrant,
} from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { deadlineFetch, describeFetchError } from './account-fetch.js';
import type { AgentGrantOverrides } from './policy.js';
import { SessionError, type SessionPrincipal } from './sessions.js';

const API = '/account/api/v1';

/** The 401 reasons a fresh open cures: the chain's token was spent, expired, or is unknown to the store. */
const REMINT_REASONS = new Set(['token_exhausted', 'token_expired', 'invalid_token']);

/** The grant's scope as the account answers it (`scope_json`): the read-only flag and the three allowlists. */
export interface AgentGrantScopeAnswer {
  readOnly: boolean;
  tools?: string[];
  machines?: string[];
  repos?: string[];
}

/** An override axis in the account's shape: exact names, every one, or nothing. */
type OverrideAxis = '*' | string[] | null;

/** The `agent-session` answer (private/account/src/dto/agent-grant.dto.ts `agentSessionResponse`). */
interface AgentSessionAnswer {
  wrappedConfigKey: string;
  configKeyVersion: number;
  serverSecret: string;
  cekGeneration: number;
  storeId: string;
  configId: string;
  teamId: string | null;
  configToken: string;
  expiresAt: string;
  overrides: { grandRepos: OverrideAxis; clusterOps: OverrideAxis };
  scope: AgentGrantScopeAnswer;
}

/** The account refused to open the grant (revoked, expired, wrong tag, or a membership that ended). Nothing says which. */
export class AgentSessionRefused extends Error {
  constructor(message = 'This agent grant cannot be opened.') {
    super(message);
    this.name = 'AgentSessionRefused';
  }
}

/** The account server could not answer (network, 5xx, 429, or a malformed answer): the grant is not judged. */
export class AgentSessionUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AgentSessionUnavailable';
  }
}

/** What one live session exposes to a call: its principal, scope, overrides and the config at its current version. */
export interface AgentGrantHandle {
  grantId: string;
  principal: SessionPrincipal;
  scope: AgentGrantScopeAnswer;
  overrides: AgentGrantOverrides;
  config: RdcConfig;
}

interface SessionRecord {
  grantId: string;
  authTagHash: string;
  storeId: string;
  configId: string;
  teamId: string | null;
  /** The config's content key, non-extractable. */
  configKey: CryptoKey;
  /** The chain's newest token; the store rotates it on every request. */
  token: string;
  expiresAtMs: number;
  overrides: AgentGrantOverrides;
  scope: AgentGrantScopeAnswer;
  /** Config version -> the config decrypted at it; only the newest is kept. */
  documents: Map<string, RdcConfig>;
  /** The version `documents` last held, for the one-entry eviction. */
  current: { version: number; key: string } | undefined;
  /** Requests of this session run one at a time, so the token never has two holders. */
  tail: Promise<unknown>;
}

export interface AgentGrantSessionsOptions {
  /** Account server base URL, e.g. https://eu.rediacc.cloud */
  accountUrl: string;
  /** The executor's own account token. Must carry proxy:exec. */
  executorToken: string;
  /** The org this executor is pinned to; the principal of every grant session carries it. */
  orgId: string;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

/** Strict base64url (no padding) of exactly 32 bytes, or null. Never echoes the input. */
function parseSecret(text: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]+$/.test(text) || text.length % 4 === 1) return null;
  const b64 = text.replaceAll('-', '+').replaceAll('_', '/');
  const bytes = Uint8Array.from(
    Buffer.from(b64 + '='.repeat((4 - (b64.length % 4)) % 4), 'base64')
  );
  if (bytes.byteLength !== AGENT_GRANT_SECRET_BYTES) return null;
  const canonical = Buffer.from(bytes)
    .toString('base64')
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '');
  return canonical === text ? bytes : null;
}

/** The overrides in the shape `authorize` reads (`AgentGrantOverrides`). */
function overridesOf(answer: AgentSessionAnswer['overrides']): AgentGrantOverrides {
  const grand = answer.grandRepos;
  return {
    allowGrandRepos: grand === '*' ? true : (grand ?? false),
    allowClusterOps: answer.clusterOps === '*',
  };
}

/** Whether a store answer says the chain's token was spent, expired or unknown, which a fresh open cures. */
function tokenLapsed(answer: { status: number; body: Record<string, unknown> }): boolean {
  const reason = typeof answer.body.code === 'string' ? answer.body.code : '';
  return answer.status === 401 && REMINT_REASONS.has(reason);
}

/** `${grantId}\0${version}`: the cache key of one decrypted document. */
const documentKey = (grantId: string, version: number): string => `${grantId}\u0000${version}`;

/** The principal an agent grant runs as. No user is named: the answer carries none, and an email nobody owns matches no `users` rule. The role is `member`, the least a policy-less org grants (see the module doc). */
function principalOf(orgId: string, grantId: string, teamId: string | null): SessionPrincipal {
  return {
    orgId,
    teamId,
    userId: `agent-grant:${grantId}`,
    userEmail: `agent-grant:${grantId}`,
    orgRole: 'member',
    agentGrantId: grantId,
  };
}

/**
 * The executor's grant sessions, one per grant id. RAM only; nothing here is written anywhere.
 */
export class AgentGrantSessions {
  private readonly sessions = new Map<string, SessionRecord>();
  /** Opens in flight, so concurrent first calls of one grant share one `agent-session` call. */
  private readonly opening = new Map<string, Promise<SessionRecord>>();
  private readonly accountUrl: string;
  private readonly fetch: typeof fetch;
  private readonly now: () => number;

  constructor(private readonly options: AgentGrantSessionsOptions) {
    this.accountUrl = options.accountUrl.replace(/\/+$/, '');
    this.fetch = deadlineFetch(options.fetchImpl ?? globalThis.fetch);
    this.now = options.now ?? Date.now;
  }

  /** The org the sessions' principals carry. */
  get orgId(): string {
    return this.options.orgId;
  }

  /** Grants holding a session now (tests and the revoke push read it). */
  get size(): number {
    return this.sessions.size;
  }

  /** Whether a session is held for `grantId`. */
  has(grantId: string): boolean {
    return this.sessions.has(grantId);
  }

  /** Drop a grant's session and every config decrypted under it (a refusal, an expiry, a pushed revocation). */
  drop(grantId: string): void {
    this.sessions.delete(grantId);
  }

  /**
   * The session of `grantId` for one call, opened or rebuilt from `secret` when none is held, with its
   * config brought to the store's current version.
   *
   * @throws AgentSessionRefused when `secret` is not the grant's, or the account will not open the grant.
   * @throws AgentSessionUnavailable when the account server could not answer.
   */
  async acquire(grantId: string, secret: string): Promise<AgentGrantHandle> {
    const bytes = parseSecret(secret);
    if (!bytes) throw new AgentSessionRefused();
    try {
      const authTagHash = await hashAuthTag(await deriveAuthTag(bytes));
      const record = await this.recordFor(grantId, bytes, authTagHash);
      const config = await this.settled(record, bytes);
      return {
        grantId,
        principal: principalOf(this.options.orgId, grantId, record.teamId),
        scope: record.scope,
        overrides: record.overrides,
        config,
      };
    } finally {
      bytes.fill(0);
    }
  }

  /**
   * The config a grant's session holds right now, for the loader (`routeAgentPrincipals`): the document
   * `acquire` settled for the call in flight. No secret is involved; a session that is gone is an error.
   */
  currentConfig(principal: SessionPrincipal): RdcConfig {
    const record = principal.agentGrantId ? this.sessions.get(principal.agentGrantId) : undefined;
    const held = record?.current ? record.documents.get(record.current.key) : undefined;
    if (!record || !held || this.now() >= record.expiresAtMs) {
      throw new SessionError(
        'This agent grant has no open session. Open it again with its secret.'
      );
    }
    return held;
  }

  /** The record of `grantId`, checked against `secret`'s tag, or a fresh open when none is held. */
  private async recordFor(
    grantId: string,
    secret: Uint8Array,
    authTagHash: string
  ): Promise<SessionRecord> {
    const held = this.sessions.get(grantId);
    if (held) {
      if (this.now() >= held.expiresAtMs) this.drop(grantId);
      else if (held.authTagHash === authTagHash) return held;
      else throw new AgentSessionRefused();
    }
    const pending = this.opening.get(grantId);
    if (pending) return await pending;
    const opened = this.open(grantId, secret, authTagHash);
    this.opening.set(grantId, opened);
    try {
      return await opened;
    } finally {
      this.opening.delete(grantId);
    }
  }

  /** One `agent-session` call, and the session it answers. */
  private async open(
    grantId: string,
    secret: Uint8Array,
    authTagHash: string
  ): Promise<SessionRecord> {
    const answer = await this.agentSession(grantId, await deriveAuthTag(secret));
    let configKey: CryptoKey;
    try {
      configKey = await unwrapConfigKeyForAgentGrant(
        answer.wrappedConfigKey,
        secret,
        fromBase64(answer.serverSecret),
        {
          grantId,
          storeId: answer.storeId,
          configId: answer.configId,
          teamId: answer.teamId,
          configKeyVersion: answer.configKeyVersion,
          cekGeneration: answer.cekGeneration,
        }
      );
    } catch {
      // A wrap that does not open under this grant's slot key is a grant the executor cannot serve: refused, and not held.
      throw new AgentSessionRefused();
    }
    const record: SessionRecord = {
      grantId,
      authTagHash,
      storeId: answer.storeId,
      configId: answer.configId,
      teamId: answer.teamId,
      configKey,
      token: answer.configToken,
      expiresAtMs: Date.parse(answer.expiresAt),
      overrides: overridesOf(answer.overrides),
      scope: answer.scope,
      documents: new Map(),
      current: undefined,
      tail: Promise.resolve(),
    };
    this.sessions.set(grantId, record);
    return record;
  }

  /** `POST /configs/agent-session` under the executor's bearer. A refusal drops any session held for the grant. */
  private async agentSession(grantId: string, authTag: string): Promise<AgentSessionAnswer> {
    let response: Response;
    try {
      response = await this.fetch(`${this.accountUrl}${API}/configs/agent-session`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${this.options.executorToken}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({ grantId, authTag }),
      });
    } catch (error) {
      throw new AgentSessionUnavailable(
        `The executor could not reach the account server to open the grant: ${describeFetchError(error)}.`
      );
    }
    if (response.status === 403) {
      this.drop(grantId);
      throw new AgentSessionRefused();
    }
    if (!response.ok) {
      throw new AgentSessionUnavailable(
        `The account server answered ${response.status} to the grant's session request.`
      );
    }
    const body = (await response.json().catch(() => null)) as AgentSessionAnswer | null;
    if (
      !body ||
      typeof body.wrappedConfigKey !== 'string' ||
      typeof body.configToken !== 'string' ||
      typeof body.configId !== 'string' ||
      Number.isNaN(Date.parse(body.expiresAt))
    ) {
      throw new AgentSessionUnavailable('The account server answered a malformed grant session.');
    }
    return body;
  }

  /** The record's config at the store's current version, serialized with every other request of the session. */
  private settled(record: SessionRecord, secret: Uint8Array): Promise<RdcConfig> {
    const run = record.tail.then(() => this.revalidate(record, secret));
    record.tail = run.catch(() => undefined);
    return run;
  }

  private async revalidate(record: SessionRecord, secret: Uint8Array): Promise<RdcConfig> {
    const listing = await this.storeRequest(record, secret, `${API}/configs`);
    if (listing.status >= 400) {
      throw new AgentSessionUnavailable(
        `The config store refused the version check (${listing.status}).`
      );
    }
    const entries = Array.isArray(listing.body.configs)
      ? (listing.body.configs as { configId?: unknown; teamId?: unknown; version?: unknown }[])
      : [];
    const entry = entries.find(
      (item) => item.configId === record.configId && (item.teamId ?? null) === record.teamId
    );
    if (!entry || typeof entry.version !== 'number') {
      // The grant's one config is gone from the listing: nothing is served from a copy that cannot be checked.
      this.drop(record.grantId);
      throw new AgentSessionRefused();
    }
    const key = documentKey(record.grantId, entry.version);
    const cached = record.documents.get(key);
    if (cached) return this.seat(record, entry.version, key, cached);
    return this.seat(record, entry.version, key, await this.pull(record, secret));
  }

  /** Make `config` the session's current document, evicting the one it replaces. */
  private seat(record: SessionRecord, version: number, key: string, config: RdcConfig): RdcConfig {
    if (record.current && record.current.key !== key) record.documents.delete(record.current.key);
    record.documents.set(key, config);
    record.current = { version, key };
    return config;
  }

  private async pull(record: SessionRecord, secret: Uint8Array): Promise<RdcConfig> {
    const query = record.teamId ? `?teamId=${encodeURIComponent(record.teamId)}` : '';
    const answer = await this.storeRequest(
      record,
      secret,
      `${API}/configs/${encodeURIComponent(record.configId)}${query}`
    );
    if (answer.status >= 400) {
      throw new AgentSessionUnavailable(`The config store refused the pull (${answer.status}).`);
    }
    const pulled = answer.body as unknown as {
      configData: string;
      sdk_derived: string;
      envelope: EncryptedConfigPayload['envelope'];
      hmac: string | null;
    };
    const payload: EncryptedConfigPayload = {
      envelope: pulled.envelope,
      encryptedBlob: pulled.configData,
      hmac: pulled.hmac,
    };
    const decrypted = await selectiveDecryptWithConfigKey(
      payload,
      record.configKey,
      await importAesKey(fromBase64(pulled.sdk_derived)),
      { storeId: record.storeId, configId: record.configId, teamId: record.teamId }
    ).catch(() => {
      throw new AgentSessionUnavailable(
        'The pulled config did not open under this grant: it was not sealed for it.'
      );
    });
    return { ...fullConfigToRdcConfig(decrypted), version: pulled.envelope.version };
  }

  /**
   * One config-store request on the session's chain: the newest token, the token the store rotates to kept
   * (an error body carries it too), and one fresh `agent-session` open when the token was spent or expired.
   */
  private async storeRequest(
    record: SessionRecord,
    secret: Uint8Array,
    path: string
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    const first = await this.send(record, path);
    if (!tokenLapsed(first)) return first;
    const fresh = await this.agentSession(record.grantId, await deriveAuthTag(secret));
    record.token = fresh.configToken;
    const second = await this.send(record, path);
    if (tokenLapsed(second)) {
      throw new AgentSessionUnavailable('The grant chain was refused again after a fresh open.');
    }
    return second;
  }

  private async send(
    record: SessionRecord,
    path: string
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    let response: Response;
    try {
      response = await this.fetch(`${this.accountUrl}${path}`, {
        method: 'GET',
        headers: { 'X-Config-Token': record.token, 'x-config-envelope': String(ENVELOPE_VERSION) },
      });
    } catch (error) {
      throw new AgentSessionUnavailable(
        `The executor could not reach the config store: ${describeFetchError(error)}.`
      );
    }
    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    // The store rotated the token before it answered, error or not: the old one is spent.
    if (typeof body.newServerToken === 'string') record.token = body.newServerToken;
    return { status: response.status, body };
  }
}
