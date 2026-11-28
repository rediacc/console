/**
 * Container-tier config loading.
 *
 * The daemon tier reads an enrolled config off its own disk. The container tier
 * has no disk worth the name and no enrollment: it starts with nothing, and the
 * only key it will ever see is the one a client grants for a session. So the
 * config has to come down the wire, encrypted, and be opened in RAM with that
 * granted key.
 *
 * TWO SECRETS, TWO SOURCES, ON PURPOSE:
 *
 *   the config TOKEN , "may fetch the bytes". Minted by the account server for
 *                       the executor, against the executor's OWN credential.
 *   the config KEY   , "may open the bytes". Granted by the USER, per session,
 *                       over X25519, held in RAM only.
 *
 * Neither half is sufficient. An executor holding a config token and no grant
 * has an opaque blob. That split is the whole reason this tier can be defended:
 * the container never holds a durable secret, and the key dies with the session.
 *
 * WHY THE EXECUTOR MINTS ITS OWN TOKEN rather than the client handing one over:
 * config tokens ROTATE on use (three uses, then exhausted). Two holders of one
 * chain race each other and the loser's copy dies. A browser could absorb that
 * and re-bootstrap silently, but the CLI could not, bootstrap-session is
 * 2FA-gated, so a CLI whose config token died would need a human at a browser to
 * get its own `config remote` access back. Lending the executor the client's
 * token would break the client as a side effect of using --proxy. Separate,
 * independently-rotating tokens keep the two apart.
 */

import type { AiConfigs } from '@rediacc/shared/ai';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { memoryPolicyHighWater } from '../config/policy-record.js';
import { deadlineFetch } from './account-fetch.js';
import type { AgentGrantSessions } from './agent-grant-session.js';
import { AuthError } from './auth.js';
import { ConfigChain, type ExecutorGrant, SessionConfigStore } from './config-writeback.js';
import { SessionError, type SessionPrincipal, SessionStore } from './sessions.js';

export interface ContainerConfigLoaderOptions {
  /** Account server base URL, e.g. https://eu.rediacc.cloud */
  accountUrl: string;
  /** The executor's own account token. Must carry proxy:exec. */
  executorToken: string;
  /** The store holding the granted keys. Answers sessionFor(principal). */
  sessions: SessionStore;
  fetchImpl?: typeof fetch;
}

/**
 * Build the `loadConfig` the container tier injects into ServeDeps.
 *
 * The decrypted config is cached PER (SESSION, TEAM), which is the entire
 * economic argument for a warm container: the second command in a session pays
 * no pull and no decrypt. The team is part of the key because one user's
 * session can serve requests under two teams, and each team has its own config
 * (Design 4 of PLAN-rmcp-executor-hardening): keyed by session alone, a team-B
 * request would run against team A's config. Every request after the first
 * revalidates the cached version against the store with one metadata read and
 * re-pulls on a mismatch (Design 5), so another device's push is seen on the
 * next command. It is dropped when the session is, so a config never outlives
 * the key that opened it.
 *
 * The config it returns is bound to the session's writeback
 * (config-writeback.ts): a command dispatched against it pushes its config
 * changes back to config storage through a writable chain, and the next command
 * of the session reads the pushed version (agent/plans/PLAN-rmcp-writeback.md).
 */
export function createContainerConfigLoader(
  options: ContainerConfigLoaderOptions
): (principal: SessionPrincipal, configSessionId?: string) => Promise<RdcConfig> {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const { sessions, executorToken } = options;

  /**
   * storeKey(sessionId, teamId) -> that session's config store for that team
   * (the decrypted config and its writeback, config-writeback.ts). RAM only;
   * never serialized, never written. The promise is cached, so concurrent first
   * requests share one pull and one store, and with it one write serialization.
   */
  const stores = new Map<string, Promise<SessionConfigStore>>();
  const storeKey = (sessionId: string, teamId: string | null): string =>
    `${sessionId}\u0000${teamId ?? ''}`;
  /** `${userId}\0${teamId}` -> the one config-token chain this container holds for that user and team. */
  const chains = new Map<string, ConfigChain>();
  /** The newest version of each policy record this container opened: an older one is a replay. */
  const policyHighWater = memoryPolicyHighWater();

  /** Drop cached configs whose session has gone. Nothing decrypted outlives its key. */
  const pruneDeadSessions = (): void => {
    for (const key of stores.keys()) {
      const sessionId = key.slice(0, key.indexOf('\u0000'));
      try {
        sessions.principal(sessionId);
      } catch {
        stores.delete(key);
      }
    }
  };

  const chainFor = (principal: SessionPrincipal): ConfigChain => {
    const key = `${principal.userId}\u0000${principal.teamId ?? ''}`;
    let chain = chains.get(key);
    if (!chain) {
      chain = new ConfigChain({
        accountUrl: options.accountUrl,
        executorToken,
        userId: principal.userId,
        fetchImpl,
      });
      chains.set(key, chain);
    }
    return chain;
  };

  const openStore = async (
    principal: SessionPrincipal,
    sessionId: string,
    cek: CryptoKey
  ): Promise<SessionConfigStore> => {
    const chain = chainFor(principal);
    // Minted for THIS principal under THIS session. The account server checks they are in the executor's org, an active config-store member, and the recorded grantor of the session (recordGrant below) before answering.
    const grant = await chain.mint(sessionId);
    const target = pickConfig(grant.configs, principal.teamId);
    return SessionConfigStore.open({
      chain,
      sessionId,
      cek,
      target: { storeId: grant.storeId, ...target },
      orgConfigId: grant.configs.find((entry) => entry.teamId === null)?.configId ?? null,
      policyHighWater,
    });
  };

  return async function loadConfig(
    principal: SessionPrincipal,
    configSessionId?: string
  ): Promise<RdcConfig> {
    pruneDeadSessions();

    // A request that names its session (the console's X-Config-Session) gets THAT session's key, ownership-checked; one that does not falls back to the principal's latest grant (the CLI proxy path).
    const sessionId = sessions.sessionForExec(principal, configSessionId);
    if (!sessionId) {
      // Same message the store itself produces, so the client is told the one thing that will fix this rather than shown a stack trace.
      throw new SessionError(
        'This session has no config key yet. Complete the key grant before running commands.'
      );
    }

    // Touches the session (keeping it alive) and fails loudly if the key is gone.
    const cek = sessions.requireCek(sessionId);

    const key = storeKey(sessionId, principal.teamId);
    const cached = stores.get(key);
    if (cached) {
      // A warm store is checked against the store's current version first; a push from another device re-pulls here.
      return (await cached).revalidate();
    }
    const store = openStore(principal, sessionId, cek);
    stores.set(key, store);
    // A failed open is not cached: the next request tries again.
    store.catch(() => {
      if (stores.get(key) === store) stores.delete(key);
    });
    // The store's current document, bound to its writeback: a request scope built around it pushes its writes back to config storage.
    return (await store).config;
  };
}

/**
 * Route an agent-grant principal to its own grant session instead of the user-keyed `loadConfig`
 * (PLAN-rmcp-agent-grants.md Design 4). The principal of a grant (`agentGrantId` set) names a session of
 * `agentSessions`, which holds the one config the grant opens; every other principal goes to `userLoader`.
 * A grant principal never reaches the user-keyed loader, even when the grant sessions are absent: it is
 * refused, because that loader would look up the grant's synthetic user and say nothing useful.
 */
export function routeAgentPrincipals(
  userLoader: (principal: SessionPrincipal, configSessionId?: string) => Promise<RdcConfig>,
  agentSessions: AgentGrantSessions | undefined
): (principal: SessionPrincipal, configSessionId?: string) => Promise<RdcConfig> {
  return async (principal, configSessionId) => {
    if (!principal.agentGrantId) return await userLoader(principal, configSessionId);
    if (!agentSessions) throw new SessionError('This executor does not serve agent grants.');
    return agentSessions.currentConfig(principal);
  };
}

/**
 * The AI profile sources of a chat, team over shared (D3 of PLAN-console-ai-providers): the config
 * the request runs against, and the org's shared config beside it, opened through the same loader
 * under the same session. A principal with no team runs against the shared config already, and an
 * agent grant's principal has only its grant's config, so both get the one source. A team with no
 * config of its own falls back to the shared one in `pickConfig`, which makes both sources the same
 * document and changes nothing. A shared config that cannot be opened fails the request, as the
 * team config would: a profile is never resolved against half of what the store holds.
 */
export function teamOverSharedAiConfigs(
  loadConfig: (principal: SessionPrincipal, configSessionId?: string) => Promise<RdcConfig>
): (
  principal: SessionPrincipal,
  config: RdcConfig,
  configSessionId?: string
) => Promise<AiConfigs> {
  return async (principal, config, configSessionId) => {
    if (principal.agentGrantId || !principal.teamId) return { team: config.ai };
    const shared = await loadConfig({ ...principal, teamId: null }, configSessionId);
    return { team: config.ai, shared: shared.ai };
  };
}

export interface ExecutorGrantRecorderOptions {
  /** Account server base URL, e.g. https://eu.rediacc.cloud */
  accountUrl: string;
  /** The executor's own account token. Must carry proxy:exec. */
  executorToken: string;
  fetchImpl?: typeof fetch;
}

/**
 * Build the `recordGrant` the container tier injects into ServeDeps.
 *
 * The account server mints a config token for a user only under a session that
 * user granted (PLAN-backup-program S7). The proof is the user's own bearer at
 * the moment it completes the CEK grant leg: the executor presents it (the same
 * token it just introspected) next to its own credential, and the server
 * records {session, executor token, grantor} for one idle window. Without that
 * record an admin-created executor could mint a config token for any member.
 */
export function createExecutorGrantRecorder(
  options: ExecutorGrantRecorderOptions
): (sessionId: string, bearerToken: string) => Promise<void> {
  const accountUrl = options.accountUrl.replace(/\/+$/, '');
  const doFetch = deadlineFetch(options.fetchImpl ?? globalThis.fetch);

  return async function recordGrant(sessionId: string, bearerToken: string): Promise<void> {
    const response = await doFetch(`${accountUrl}/account/api/v1/configs/executor-grant`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${options.executorToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ sessionId, token: bearerToken }),
    });
    if (!response.ok) {
      const message = await describe(response, 'could not record the key grant');
      // Only a refusal is a 401/403; an unavailable account server (5xx, 429) surfaces as a server fault, not as a refused grant.
      if (response.status === 401 || response.status === 403) {
        throw new AuthError(message, response.status);
      }
      throw new Error(message);
    }
  };
}

/**
 * The config a principal's commands run against.
 *
 * Prefer the one scoped to their team; fall back to the org-wide (team-less)
 * config. A store with neither is a misconfiguration, and saying so beats
 * running commands against an arbitrary tenant's config.
 */
function pickConfig(
  configs: ExecutorGrant['configs'],
  teamId: string | null
): { configId: string; teamId: string | null } {
  const forTeam = teamId ? configs.find((entry) => entry.teamId === teamId) : undefined;
  const shared = configs.find((entry) => entry.teamId === null);
  const chosen = forTeam ?? shared;

  if (!chosen) {
    throw new SessionError(
      teamId
        ? `Config storage holds no config for team "${teamId}" and no shared config to fall back to.`
        : 'Config storage holds no shared config for this organization.'
    );
  }
  return { configId: chosen.configId, teamId: chosen.teamId };
}

async function describe(response: Response, what: string): Promise<string> {
  const body = await response.text().catch(() => '');
  const detail = body.slice(0, 200);
  return `The executor ${what} from the account server (${response.status})${detail ? `: ${detail}` : ''}.`;
}
