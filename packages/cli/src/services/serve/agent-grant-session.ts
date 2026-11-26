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
 * POLICY. The agent is judged as its person, narrowed by the grant (operator ruling ASKED:2026-11-25T19:55Z).
 * The principal carries the grant user's real org role, email and team slug from the `agent-session` answer,
 * and `authorize` makes it an agent through the grant's overrides. The policy is read from the records, as
 * the user-keyed loader reads it (config-writeback.ts): the org-level config's record as the ceiling, the
 * grant config's own record narrowing it. The grant holds no CEK, so each record opens under the policy key
 * wrapped for that one pointer (`policyKeys`, unwrapped at open into non-extractable decrypt-only keys):
 * the grant config's and the org-level config's, and no other. A grant that carries no policy key for its
 * own config is refused (clean break), and a record whose pointer the grant holds no key for refuses the
 * grant too, since nothing about it could be judged. The effective policy is bound to every document the
 * session pulls, so the authorizer reads the records' verdict and never a `policy` field in the document.
 */

import type { EncryptedConfigPayload } from '@rediacc/shared/config-crypto';
import {
  deriveAuthTag,
  ENVELOPE_VERSION,
  fromBase64,
  hashAuthTag,
  importAesKey,
  type PolicyKey,
  selectiveDecryptWithConfigKey,
  unwrapConfigKeyForAgentGrant,
  unwrapPolicyKeyForAgentGrant,
} from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { EffectivePolicy } from '@rediacc/shared/policy';
import {
  bindEffectivePolicy,
  loadEffectivePolicy,
  memoryPolicyHighWater,
  type PolicyHighWater,
  type PolicyPointer,
  parsePolicyRecordField,
} from '../config/policy-record.js';
import { deadlineFetch, describeFetchError } from './account-fetch.js';
import {
  type AgentSessionAnswer,
  documentKey,
  isWrappedPolicyKey,
  overridesOf,
  parseSecret,
  pointerKey,
  principalOf,
  tokenLapsed,
} from './agent-grant-wire.js';
import type { AgentGrantOverrides } from './policy.js';
import { SessionError, type SessionPrincipal } from './sessions.js';

const API = '/account/api/v1';

/** How long a pushed revocation is remembered: the longest grant lifetime (D54, 30 days). */
const REVOKED_MEMORY_MS = 30 * 24 * 60 * 60 * 1000;

/** The grant's scope as the account answers it (`scope_json`): the read-only flag and the three allowlists. */
export interface AgentGrantScopeAnswer {
  readOnly: boolean;
  tools?: string[];
  machines?: string[];
  repos?: string[];
}

const ORG_ROLES = new Set<SessionPrincipal['orgRole']>(['owner', 'admin', 'member']);

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
  /** The principal the grant runs as: its user's role, email and team, from the open. */
  principal: SessionPrincipal;
  /** `pointerKey` of a policy record's config -> the policy key unwrapped for that pointer. */
  policyKeys: Map<string, PolicyKey>;
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
  /** High-water marks of the policy records read; RAM for the container's life by default. */
  policyHighWater?: PolicyHighWater;
}

/**
 * The executor's grant sessions, one per grant id. RAM only; nothing here is written anywhere.
 */
export class AgentGrantSessions {
  private readonly sessions = new Map<string, SessionRecord>();
  /**
   * Opens in flight, so concurrent first calls of one grant share one `agent-session` call. Each carries the
   * hash of the auth tag it was started with: only a call whose secret derives the same tag joins it.
   */
  private readonly opening = new Map<
    string,
    { authTagHash: string; record: Promise<SessionRecord> }
  >();
  /**
   * Grants revoked by a push (box AG-S5), grant id -> when the entry may go. A revoked grant is refused
   * here without asking the account, and an open still in flight when the push arrives cannot bring the
   * session back. An entry outlives the longest grant (30 days), so it is never needed after that.
   */
  private readonly revoked = new Map<string, number>();
  private readonly accountUrl: string;
  private readonly fetch: typeof fetch;
  private readonly now: () => number;
  private readonly policyHighWater: PolicyHighWater;

  constructor(private readonly options: AgentGrantSessionsOptions) {
    this.accountUrl = options.accountUrl.replace(/\/+$/, '');
    this.fetch = deadlineFetch(options.fetchImpl ?? globalThis.fetch);
    this.now = options.now ?? Date.now;
    this.policyHighWater = options.policyHighWater ?? memoryPolicyHighWater();
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

  /** Drop a grant's session and every config decrypted under it (a refusal, an expiry). */
  drop(grantId: string): void {
    this.sessions.delete(grantId);
  }

  /**
   * A pushed revocation (box AG-S5, Design 5): drop the session and its cached config, and refuse the grant
   * from now on without an account call. A call already holding the session record finishes with it; the
   * next `acquire` is refused. Returns whether a session was held.
   */
  revoke(grantId: string): boolean {
    const now = this.now();
    for (const [id, until] of this.revoked) if (until <= now) this.revoked.delete(id);
    this.revoked.set(grantId, now + REVOKED_MEMORY_MS);
    const held = this.sessions.has(grantId);
    this.drop(grantId);
    return held;
  }

  private isRevoked(grantId: string): boolean {
    const until = this.revoked.get(grantId);
    if (until === undefined) return false;
    if (until > this.now()) return true;
    this.revoked.delete(grantId);
    return false;
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
    if (!bytes || this.isRevoked(grantId)) throw new AgentSessionRefused();
    try {
      const authTagHash = await hashAuthTag(await deriveAuthTag(bytes));
      const record = await this.recordFor(grantId, bytes, authTagHash);
      const config = await this.settled(record, bytes);
      return {
        grantId,
        principal: record.principal,
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

  /**
   * The unexpired record held for `grantId` when `authTagHash` is its tag; undefined when none is held (an
   * expired one is dropped first).
   *
   * @throws AgentSessionRefused when a record is held under another tag.
   */
  private heldFor(grantId: string, authTagHash: string): SessionRecord | undefined {
    const held = this.sessions.get(grantId);
    if (!held) return undefined;
    if (this.now() >= held.expiresAtMs) {
      this.drop(grantId);
      return undefined;
    }
    if (held.authTagHash !== authTagHash) throw new AgentSessionRefused();
    return held;
  }

  /**
   * The record of `grantId`, checked against `secret`'s tag, or a fresh open when none is held.
   *
   * A call joins an open in flight only when its tag matches the one that open was started with. Any other
   * call waits for that open to settle and is then judged against what it left: refused by the held
   * record's tag when the open succeeded, or opening on its own when it failed. It never starts a second
   * `agent-session` call beside the first, so a wrong secret can neither share the session nor, through the
   * account's refusal, drop the session the right secret is opening.
   */
  private async recordFor(
    grantId: string,
    secret: Uint8Array,
    authTagHash: string
  ): Promise<SessionRecord> {
    for (;;) {
      const held = this.heldFor(grantId, authTagHash);
      if (held) return held;
      const pending = this.opening.get(grantId);
      if (!pending) break;
      if (pending.authTagHash === authTagHash) return await pending.record;
      await pending.record.catch(() => undefined);
    }
    const opened = this.open(grantId, secret, authTagHash);
    this.opening.set(grantId, { authTagHash, record: opened });
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
    const policyKeys = await this.unwrapPolicyKeys(grantId, secret, answer);
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
      principal: principalOf(this.options.orgId, grantId, answer),
      policyKeys,
      documents: new Map(),
      current: undefined,
      tail: Promise.resolve(),
    };
    // A revocation pushed while this open was in flight wins: the session is never held.
    if (this.isRevoked(grantId)) throw new AgentSessionRefused();
    this.sessions.set(grantId, record);
    return record;
  }

  /**
   * The grant's policy keys, each unwrapped for its own pointer. A grant with no key for its own config is
   * refused (clean break: no grant is served without the policy its person is judged by), and so is one
   * whose wrap does not open under this grant's slot key and pointer.
   */
  private async unwrapPolicyKeys(
    grantId: string,
    secret: Uint8Array,
    answer: AgentSessionAnswer
  ): Promise<Map<string, PolicyKey>> {
    const own = pointerKey(answer.configId, answer.teamId);
    const wrapsOwn = answer.policyKeys.some(
      (entry) => pointerKey(entry.policyConfigId, entry.policyTeamId) === own
    );
    if (!wrapsOwn) {
      throw new AgentSessionRefused(
        'This agent grant carries no policy key for its config, so its policy cannot be read. Create the grant again.'
      );
    }
    const serverSecret = fromBase64(answer.serverSecret);
    const keys = new Map<string, PolicyKey>();
    for (const entry of answer.policyKeys) {
      try {
        keys.set(
          pointerKey(entry.policyConfigId, entry.policyTeamId),
          await unwrapPolicyKeyForAgentGrant(entry.wrapped, secret, serverSecret, {
            grantId,
            storeId: answer.storeId,
            configId: answer.configId,
            cekGeneration: answer.cekGeneration,
            policyConfigId: entry.policyConfigId,
            policyTeamId: entry.policyTeamId,
          })
        );
      } catch {
        throw new AgentSessionRefused();
      }
    }
    return keys;
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
    if (body && !(Array.isArray(body.policyKeys) && body.policyKeys.every(isWrappedPolicyKey))) {
      // No wraps at all, or wraps in no shape the executor reads: a grant whose policy cannot be opened is refused.
      throw new AgentSessionRefused(
        'This agent grant carries no policy keys, so its policy cannot be read. Create the grant again.'
      );
    }
    if (
      !body ||
      typeof body.wrappedConfigKey !== 'string' ||
      typeof body.configToken !== 'string' ||
      typeof body.configId !== 'string' ||
      Number.isNaN(Date.parse(body.expiresAt)) ||
      !ORG_ROLES.has(body.orgRole) ||
      typeof body.userEmail !== 'string' ||
      (body.teamSlug !== null && typeof body.teamSlug !== 'string')
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
    const org = entries.find(
      (item) => (item.teamId ?? null) === null && typeof item.configId === 'string'
    );
    // A team grant's policy has the org-level record as its ceiling: a store that lists none cannot be judged, so the grant is refused rather than served without the ceiling.
    if (record.teamId !== null && !org) {
      this.drop(record.grantId);
      throw new AgentSessionRefused(
        'This agent grant is on a team, and the store holds no org-level config whose policy applies to it.'
      );
    }
    const orgConfigId = org ? (org.configId as string) : null;
    return this.seat(record, entry.version, key, await this.pull(record, secret, orgConfigId));
  }

  /** Make `config` the session's current document, evicting the one it replaces. */
  private seat(record: SessionRecord, version: number, key: string, config: RdcConfig): RdcConfig {
    if (record.current && record.current.key !== key) record.documents.delete(record.current.key);
    record.documents.set(key, config);
    record.current = { version, key };
    return config;
  }

  private async pull(
    record: SessionRecord,
    secret: Uint8Array,
    orgConfigId: string | null
  ): Promise<RdcConfig> {
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
      policy?: unknown;
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
    const effective = await this.effectivePolicy(record, secret, orgConfigId, pulled.policy);
    const config: RdcConfig = {
      ...fullConfigToRdcConfig(decrypted),
      version: pulled.envelope.version,
    };
    bindEffectivePolicy(config, effective);
    return config;
  }

  /**
   * The effective policy of the grant's config, from the records only: the one that rode with the pull and
   * the org-level config's, each opened under the policy key the grant holds for its pointer.
   */
  private async effectivePolicy(
    record: SessionRecord,
    secret: Uint8Array,
    orgConfigId: string | null,
    pulledPolicy: unknown
  ): Promise<EffectivePolicy> {
    const keyFor = (pointer: PolicyPointer): Promise<PolicyKey> => {
      const key = record.policyKeys.get(pointerKey(pointer.configId, pointer.teamId));
      if (key) return Promise.resolve(key);
      // A record the grant cannot open would leave its rules unread: the grant cannot be judged, so it is not served.
      this.drop(record.grantId);
      return Promise.reject(
        new AgentSessionRefused(
          `This agent grant holds no policy key for config ${pointer.configId}, whose policy applies to it. Create the grant again.`
        )
      );
    };
    try {
      return await loadEffectivePolicy({
        storeId: record.storeId,
        config: { configId: record.configId, teamId: record.teamId },
        ...(pulledPolicy === undefined ? {} : { pulled: parsePolicyRecordField(pulledPolicy) }),
        orgConfigId,
        fetchRecord: (configId, teamId) => this.fetchPolicyRecord(record, secret, configId, teamId),
        key: keyFor,
        highWater: this.policyHighWater,
      });
    } catch (error) {
      if (error instanceof AgentSessionRefused || error instanceof AgentSessionUnavailable) {
        throw error;
      }
      throw new AgentSessionUnavailable(
        `The grant's policy could not be read: ${(error as Error).message}`
      );
    }
  }

  /** `GET /configs/:id/policy` on the grant's chain: the record, or null when none is saved for that config. */
  private async fetchPolicyRecord(
    record: SessionRecord,
    secret: Uint8Array,
    configId: string,
    teamId: string | null
  ) {
    const query = teamId ? `?teamId=${encodeURIComponent(teamId)}` : '';
    const answer = await this.storeRequest(
      record,
      secret,
      `${API}/configs/${encodeURIComponent(configId)}/policy${query}`
    );
    if (answer.status === 404 && answer.body.code === 'policy_not_found') return null;
    if (answer.status >= 400) {
      throw new AgentSessionUnavailable(
        `The config store refused the policy record read (${answer.status}).`
      );
    }
    const { version, cekGeneration, blob } = answer.body;
    return parsePolicyRecordField({ version, cekGeneration, blob });
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
