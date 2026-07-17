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
 *   the config TOKEN  — "may fetch the bytes". Minted by the account server for
 *                       the executor, against the executor's OWN credential.
 *   the config KEY    — "may open the bytes". Granted by the USER, per session,
 *                       over X25519, held in RAM only.
 *
 * Neither half is sufficient. An executor holding a config token and no grant
 * has an opaque blob. That split is the whole reason this tier can be defended:
 * the container never holds a durable secret, and the key dies with the session.
 *
 * WHY THE EXECUTOR MINTS ITS OWN TOKEN rather than the client handing one over:
 * config tokens ROTATE on use (three uses, then exhausted). Two holders of one
 * chain race each other and the loser's copy dies. A browser could absorb that
 * and re-bootstrap silently, but the CLI could not — bootstrap-session is
 * 2FA-gated, so a CLI whose config token died would need a human at a browser to
 * get its own `config remote` access back. Lending the executor the client's
 * token would break the client as a side effect of using --proxy. Separate,
 * independently-rotating tokens keep the two apart.
 */

import type { EncryptedConfigPayload } from '@rediacc/shared/config-crypto';
import { fromBase64, importAesKey } from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { decryptConfigPullPayload } from '@rediacc/shared/config-schema';
import { SessionError, type SessionPrincipal, SessionStore } from './sessions.js';

/** What the account server hands an executor so it can fetch a member's config. */
interface ExecutorGrant {
  token: string;
  storeId: string;
  serverSecret: string;
  configs: { configId: string; teamId: string | null; version: number }[];
}

interface PullResponse {
  newServerToken: string;
  sdk_derived: string;
  configData: string;
  envelope: EncryptedConfigPayload['envelope'];
  hmac: string | null;
}

export interface ContainerConfigLoaderOptions {
  /** Account server base URL, e.g. https://eu.rediacc.com */
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
 * The decrypted config is cached PER SESSION, which is the entire economic
 * argument for a warm container: the second command in a session pays no pull,
 * no decrypt, and no round trip. It is dropped when the session is, so a config
 * never outlives the key that opened it.
 */
export function createContainerConfigLoader(
  options: ContainerConfigLoaderOptions
): (principal: SessionPrincipal) => Promise<RdcConfig> {
  const accountUrl = options.accountUrl.replace(/\/+$/, '');
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  const { sessions, executorToken } = options;

  /** sessionId -> decrypted config. RAM only; never serialized, never written. */
  const cache = new Map<string, RdcConfig>();

  /** Drop cached configs whose session has gone. Nothing decrypted outlives its key. */
  const pruneDeadSessions = (): void => {
    for (const sessionId of cache.keys()) {
      try {
        sessions.principal(sessionId);
      } catch {
        cache.delete(sessionId);
      }
    }
  };

  return async function loadConfig(
    principal: SessionPrincipal,
    configSessionId?: string
  ): Promise<RdcConfig> {
    pruneDeadSessions();

    // A request that names its session (the console's X-Config-Session) gets
    // THAT session's key, ownership-checked; one that does not falls back to
    // the principal's latest grant (the CLI proxy path).
    const sessionId = sessions.sessionForExec(principal, configSessionId);
    if (!sessionId) {
      // Same message the store itself produces, so the client is told the one
      // thing that will fix this rather than shown a stack trace.
      throw new SessionError(
        'This session has no config key yet. Complete the key grant before running commands.'
      );
    }

    // Touches the session (keeping it alive) and fails loudly if the key is gone.
    const cek = sessions.requireCek(sessionId);

    const cached = cache.get(sessionId);
    if (cached) return cached;

    // Minted for THIS principal. The account server checks they are in the
    // executor's org and are an active config-store member before answering.
    const grant = await mintExecutorGrant(principal.userId);
    const target = pickConfig(grant.configs, principal.teamId);

    const pull = await pullConfig(grant.token, target.configId, target.teamId);

    const payload: EncryptedConfigPayload = {
      envelope: pull.envelope,
      encryptedBlob: pull.configData,
      hmac: pull.hmac ?? '',
    };

    // The key is the SESSION's, never the executor's — it has none of its own.
    const decrypted = await decryptConfigPullPayload(payload, {
      cek,
      sdkDerived: await importAesKey(fromBase64(pull.sdk_derived)),
    });

    const config = fullConfigToRdcConfig(decrypted);
    cache.set(sessionId, config);
    return config;
  };

  async function mintExecutorGrant(userId: string): Promise<ExecutorGrant> {
    const response = await doFetch(`${accountUrl}/account/api/v1/configs/executor-token`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${executorToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ userId }),
    });
    if (!response.ok) {
      throw new SessionError(await describe(response, 'could not obtain a config token'));
    }
    return (await response.json()) as ExecutorGrant;
  }

  async function pullConfig(
    configToken: string,
    configId: string,
    teamId: string | null
  ): Promise<PullResponse> {
    const query = teamId ? `?teamId=${encodeURIComponent(teamId)}` : '';
    const response = await doFetch(
      `${accountUrl}/account/api/v1/configs/${encodeURIComponent(configId)}${query}`,
      { headers: { 'X-Config-Token': configToken } }
    );
    if (!response.ok) {
      throw new SessionError(await describe(response, 'could not fetch the config'));
    }
    return (await response.json()) as PullResponse;
  }
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
