/**
 * A fake account server for agent-grant sessions, with REAL ciphertext: the config is sealed under a content key
 * exactly as a CLI push seals it, and that key is wrapped for the grant with `wrapConfigKeyForAgentGrant`, the
 * browser's own function. Nothing about the crypto is stubbed, so a session that could not truly open its grant
 * would hold nothing and every assertion over it would fail.
 */

import {
  deriveAuthTag,
  exportAesKey,
  formatAgentBearer,
  generateCek,
  generateConfigKey,
  generateSdkMaster,
  hashAuthTag,
  newAgentGrantSecret,
  randomBytes,
  sdkDerive,
  toBase64,
  wrapConfigKeyForAgentGrant,
} from '@rediacc/shared/config-crypto';
import { buildConfigPushPayload, type RdcConfig } from '@rediacc/shared/config-schema';
import { expect } from 'vitest';

export const EXECUTOR_TOKEN = 'rdt_executor';
export const ORG_ID = 'org-1';
export const STORE_ID = 'store-1';

export interface FakeGrant {
  grantId: string;
  teamId: string | null;
  configId: string;
  /** The agent secret, as the Worker posts it (base64url of `S`). */
  secret: string;
  secretBytes: Uint8Array;
  /** What the account stores: SHA-256 of the auth tag. */
  authTagHash: string;
  scope: { readOnly: boolean; tools?: string[]; machines?: string[]; repos?: string[] };
  overrides: { grandRepos: '*' | string[] | null; clusterOps: '*' | string[] | null };
  expiresAt: string;
  /** The version the store holds the config at. */
  version: number;
  /** What the grant's config looks like now. */
  config: RdcConfig;
  wrappedConfigKey: string;
  serverSecret: string;
  configKeyVersion: number;
  cekGeneration: number;
  payload: Awaited<ReturnType<typeof buildConfigPushPayload>>;
  sdkDerivedB64: string;
}

export interface FakeAccount {
  fetch: typeof fetch;
  grants: Map<string, FakeGrant>;
  /** Every request, as `METHOD path`. */
  calls: string[];
  /** Bodies posted to agent-session. */
  openBodies: { grantId: string; authTag: string }[];
  /** Grants the account refuses to open (403 with the one code). */
  refused: Set<string>;
  /** Answer 401 token_expired to the next store request of a token, once. */
  expireNextToken: boolean;
  /** Answer this status to the next agent-session call. */
  failNextOpenWith?: number;
  /** Re-seal a grant's config at a new version. */
  bump(grantId: string, config: RdcConfig): Promise<void>;
  count(prefix: string): number;
}

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

export function configOf(id: string, machine: string): RdcConfig {
  return {
    schemaVersion: 3,
    id,
    version: 1,
    credentials: { ssh: { privateKey: `KEY-${id}` } },
    resources: {
      machines: { [machine]: { ip: '10.9.9.9', user: 'deploy', port: 22 } },
      repositories: {
        demo: {
          grand: 'latest',
          placement: { machine },
          tags: { latest: { repositoryGuid: '11111111-1111-4111-8111-111111111111' } },
        },
      },
    },
    state: { repos: { demo: { latest: { networkId: 2816 } } } },
    encryption: { mode: 'plaintext' },
  };
}

export async function makeGrant(input: {
  grantId: string;
  teamId?: string | null;
  configId: string;
  machine: string;
  scope?: FakeGrant['scope'];
  overrides?: FakeGrant['overrides'];
  expiresAt?: string;
}): Promise<FakeGrant & { cek: CryptoKey; sdkDerived: CryptoKey; configKey: CryptoKey }> {
  const teamId = input.teamId ?? null;
  const secretBytes = newAgentGrantSecret();
  const bearer = formatAgentBearer(input.grantId, secretBytes);
  const secret = bearer.slice(bearer.indexOf('.') + 1);
  const authTagHash = await hashAuthTag(await deriveAuthTag(secretBytes));
  const cek = await generateCek();
  const configKey = await generateConfigKey();
  const serverSecretBytes = randomBytes(32);
  const cekGeneration = 1;
  const configKeyVersion = 1;
  const wrappedConfigKey = await wrapConfigKeyForAgentGrant(
    configKey,
    secretBytes,
    serverSecretBytes,
    {
      grantId: input.grantId,
      storeId: STORE_ID,
      configId: input.configId,
      teamId,
      configKeyVersion,
      cekGeneration,
    }
  );
  const sdkEpoch = 777;
  const sdkDerived = await sdkDerive(generateSdkMaster(), sdkEpoch);
  const config = configOf(input.configId, input.machine);
  const payload = await buildConfigPushPayload(config, {
    storeId: STORE_ID,
    ...(teamId ? { teamId } : {}),
    version: 4,
    sdkEpoch,
    sdkDerived,
    cek,
    cekGeneration,
    configKey: { key: configKey, version: configKeyVersion, cekGeneration },
  });
  return {
    grantId: input.grantId,
    teamId,
    configId: input.configId,
    secret,
    secretBytes,
    authTagHash,
    scope: input.scope ?? { readOnly: false },
    overrides: input.overrides ?? { grandRepos: null, clusterOps: null },
    expiresAt: input.expiresAt ?? new Date(Date.now() + 3_600_000).toISOString(),
    version: 4,
    config,
    wrappedConfigKey,
    serverSecret: toBase64(serverSecretBytes),
    configKeyVersion,
    cekGeneration,
    payload,
    sdkDerivedB64: toBase64(await exportAesKey(sdkDerived)),
    cek,
    sdkDerived,
    configKey,
  };
}

/** The fake account over `grants`. Tokens rotate on every store request, as the real store's do. */
export function fakeAccount(
  grants: (FakeGrant & { cek: CryptoKey; sdkDerived: CryptoKey; configKey: CryptoKey })[]
): FakeAccount {
  const byId = new Map(grants.map((g) => [g.grantId, g]));
  /** token -> grant id; a rotated token replaces its predecessor. */
  const tokens = new Map<string, string>();
  let serial = 0;
  const mint = (grantId: string): string => {
    serial += 1;
    const token = `rct_${grantId}_${serial}`;
    tokens.set(token, grantId);
    return token;
  };
  /** `POST /configs/agent-session` under the executor's bearer. */
  const openSession = (init?: RequestInit): Response => {
    expect(init?.headers).toMatchObject({ authorization: `Bearer ${EXECUTOR_TOKEN}` });
    const body = JSON.parse(init?.body as string) as { grantId: string; authTag: string };
    account.openBodies.push(body);
    if (account.failNextOpenWith) {
      const status = account.failNextOpenWith;
      account.failNextOpenWith = undefined;
      return json({ error: 'down' }, status);
    }
    const grant = byId.get(body.grantId);
    if (!grant || account.refused.has(body.grantId)) {
      return json({ error: 'refused', code: 'agent_session_refused' }, 403);
    }
    return json({
      wrappedConfigKey: grant.wrappedConfigKey,
      configKeyVersion: grant.configKeyVersion,
      serverSecret: grant.serverSecret,
      cekGeneration: grant.cekGeneration,
      storeId: STORE_ID,
      configId: grant.configId,
      teamId: grant.teamId,
      configToken: mint(grant.grantId),
      expiresAt: grant.expiresAt,
      overrides: grant.overrides,
      scope: grant.scope,
    });
  };

  /** The config store: a config token, no Authorization; every answer rotates the token. */
  const storeRequest = (path: string, init?: RequestInit): Response => {
    const token = (init?.headers as Record<string, string>)['X-Config-Token'];
    const grantId = tokens.get(token);
    if (account.expireNextToken) {
      account.expireNextToken = false;
      return json({ code: 'token_expired', error: 'expired' }, 401);
    }
    const grant = grantId === undefined ? undefined : byId.get(grantId);
    if (!grant) return json({ code: 'invalid_token', error: 'unknown' }, 401);
    tokens.delete(token);
    const newServerToken = mint(grant.grantId);
    if (path === '/configs') {
      const entry = { configId: grant.configId, teamId: grant.teamId, version: grant.version };
      return json({ newServerToken, configs: [entry] });
    }
    if (path !== `/configs/${grant.configId}`) return json({ error: 'not found' }, 404);
    return json({
      newServerToken,
      sdk_derived: grant.sdkDerivedB64,
      configData: grant.payload.encryptedBlob,
      envelope: grant.payload.envelope,
      hmac: grant.payload.hmac,
    });
  };

  const account: FakeAccount = {
    grants: byId,
    calls: [],
    openBodies: [],
    refused: new Set(),
    expireNextToken: false,
    count: (prefix) => account.calls.filter((call) => call.startsWith(prefix)).length,
    async bump(grantId, config) {
      const grant = byId.get(grantId) as (typeof grants)[number];
      grant.version += 1;
      grant.config = config;
      grant.payload = await buildConfigPushPayload(config, {
        storeId: STORE_ID,
        ...(grant.teamId ? { teamId: grant.teamId } : {}),
        version: grant.version,
        sdkEpoch: 777,
        sdkDerived: grant.sdkDerived,
        cek: grant.cek,
        cekGeneration: grant.cekGeneration,
        configKey: {
          key: grant.configKey,
          version: grant.configKeyVersion,
          cekGeneration: grant.cekGeneration,
        },
      });
    },
    fetch: ((url: string | URL, init?: RequestInit) => {
      const path = new URL(String(url)).pathname.replace('/account/api/v1', '');
      const method = init?.method ?? 'GET';
      account.calls.push(`${method} ${path}`);
      if (path === '/configs/agent-session' && method === 'POST') {
        return Promise.resolve(openSession(init));
      }
      return Promise.resolve(storeRequest(path, init));
    }) as unknown as typeof fetch,
  };
  return account;
}
