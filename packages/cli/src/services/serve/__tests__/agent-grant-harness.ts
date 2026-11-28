/**
 * A fake account server for agent-grant sessions, with REAL ciphertext: the config is sealed under a content key
 * exactly as a CLI push seals it, and that key is wrapped for the grant with `wrapConfigKeyForAgentGrant`, the
 * browser's own function. Nothing about the crypto is stubbed, so a session that could not truly open its grant
 * would hold nothing and every assertion over it would fail.
 *
 * The policy records are real too: sealed with `encryptPolicyRecord` under the grant's CEK, and their policy keys
 * wrapped for the grant with `wrapPolicyKeyForAgentGrant`, one wrap for a grant on the org-level config and two (its
 * own config's and the org-level config's) for a team grant, as the console mints them.
 */

import {
  deriveAuthTag,
  derivePolicyKey,
  encryptPolicyRecord,
  exportAesKey,
  formatAgentBearer,
  generateCek,
  generateConfigKey,
  generateSdkMaster,
  hashAuthTag,
  newAgentGrantSecret,
  type PolicyRecord,
  randomBytes,
  sdkDerive,
  toBase64,
  wrapConfigKeyForAgentGrant,
  wrapPolicyKeyForAgentGrant,
} from '@rediacc/shared/config-crypto';
import { buildConfigPushPayload, type RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import { expect } from 'vitest';

export const EXECUTOR_TOKEN = 'rdt_executor';
export const ORG_ID = 'org-1';
const STORE_ID = 'store-1';
/** The org-level config a team grant's listing carries beside its own. */
export const ORG_CONFIG_ID = 'cfg-org';

/** Everything allowed for every role: the policy a grant runs under unless a case names its own. */
export const OPEN_POLICY: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['*'] } },
};

/** One wrapped policy key, as `agent-session` answers it. */
interface FakePolicyKey {
  policyConfigId: string;
  policyTeamId: string | null;
  wrapped: string;
}

const pointerOf = (configId: string, teamId: string | null) => `${configId}/${teamId ?? ''}`;

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
  /** The grant user, as the account reads it for every open. */
  orgRole: 'owner' | 'admin' | 'member';
  userEmail: string;
  teamSlug: string | null;
  /** The policy keys wrapped for the grant; empty for a grant minted with none. */
  policyKeys: FakePolicyKey[];
  /** `configId/teamId` -> the policy record the store holds for it. */
  policyRecords: Map<string, PolicyRecord>;
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
  /** While set, every agent-session call waits for it before it is answered (a slow account, for races). */
  holdOpens?: Promise<void>;
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

/**
 * The policy records that apply to a grant, sealed under its CEK, and the policy keys wrapped for it: its own config,
 * and for a team grant the org-level config too (one wrap or two, as the console mints them).
 */
async function sealPolicies(input: {
  grantId: string;
  configId: string;
  teamId: string | null;
  cek: CryptoKey;
  secretBytes: Uint8Array;
  serverSecretBytes: Uint8Array;
  cekGeneration: number;
  policies: { org?: PolicyDocument; team?: PolicyDocument } | undefined;
  wraps: boolean;
}): Promise<{ policyKeys: FakePolicyKey[]; policyRecords: Map<string, PolicyRecord> }> {
  const { cek, cekGeneration } = input;
  const org = input.policies?.org ?? OPEN_POLICY;
  const pointers: { configId: string; teamId: string | null; document?: PolicyDocument }[] =
    input.teamId === null
      ? [{ configId: input.configId, teamId: null, document: org }]
      : [
          { configId: input.configId, teamId: input.teamId, document: input.policies?.team },
          { configId: ORG_CONFIG_ID, teamId: null, document: org },
        ];
  const policyKeys: FakePolicyKey[] = [];
  const policyRecords = new Map<string, PolicyRecord>();
  for (const pointer of pointers) {
    const binding = { storeId: STORE_ID, configId: pointer.configId, teamId: pointer.teamId };
    if (pointer.document) {
      policyRecords.set(
        pointerOf(pointer.configId, pointer.teamId),
        await encryptPolicyRecord(pointer.document, cek, { ...binding, version: 1, cekGeneration })
      );
    }
    if (!input.wraps) continue;
    const policyKey = await derivePolicyKey(cek, { ...binding, cekGeneration });
    policyKeys.push({
      policyConfigId: pointer.configId,
      policyTeamId: pointer.teamId,
      wrapped: await wrapPolicyKeyForAgentGrant(
        policyKey,
        input.secretBytes,
        input.serverSecretBytes,
        {
          grantId: input.grantId,
          storeId: STORE_ID,
          configId: input.configId,
          cekGeneration,
          policyConfigId: pointer.configId,
          policyTeamId: pointer.teamId,
        }
      ),
    });
  }
  return { policyKeys, policyRecords };
}

/** The store's answer to a request the grant's chain may make, once its token checked out. */
function storeAnswer(
  grant: FakeGrant,
  url: string,
  path: string,
  newServerToken: string
): Response {
  if (path === '/configs') {
    const entry = { configId: grant.configId, teamId: grant.teamId, version: grant.version };
    // A team chain lists its own team's configs and the org-level one (config-team-access.ts).
    const org = { configId: ORG_CONFIG_ID, teamId: null, version: 1 };
    return json({ newServerToken, configs: grant.teamId === null ? [entry] : [entry, org] });
  }
  const policyPath = /^\/configs\/([^/]+)\/policy$/.exec(path);
  if (policyPath) {
    const teamId = new URL(url).searchParams.get('teamId');
    const record = grant.policyRecords.get(pointerOf(policyPath[1] as string, teamId));
    if (!record) return json({ newServerToken, code: 'policy_not_found', error: 'none' }, 404);
    return json({ newServerToken, ...record });
  }
  if (path !== `/configs/${grant.configId}`) return json({ error: 'not found' }, 404);
  return json({
    newServerToken,
    sdk_derived: grant.sdkDerivedB64,
    configData: grant.payload.encryptedBlob,
    envelope: grant.payload.envelope,
    hmac: grant.payload.hmac,
    policy: grant.policyRecords.get(pointerOf(grant.configId, grant.teamId)) ?? null,
  });
}

export async function makeGrant(input: {
  grantId: string;
  teamId?: string | null;
  configId: string;
  machine: string;
  scope?: FakeGrant['scope'];
  overrides?: FakeGrant['overrides'];
  expiresAt?: string;
  /** The org policy (the org-level config's record) and the team policy (a team grant's own record). */
  policies?: { org?: PolicyDocument; team?: PolicyDocument };
  orgRole?: FakeGrant['orgRole'];
  userEmail?: string;
  /** False mints the grant with no policy key wrapped, as no grant may be any more. */
  wraps?: boolean;
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
  const { policyKeys, policyRecords } = await sealPolicies({
    grantId: input.grantId,
    configId: input.configId,
    teamId,
    cek,
    secretBytes,
    serverSecretBytes,
    cekGeneration,
    policies: input.policies,
    wraps: input.wraps !== false,
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
    orgRole: input.orgRole ?? 'owner',
    userEmail: input.userEmail ?? `person-${input.grantId}@example.test`,
    teamSlug: teamId ? `slug-${teamId}` : null,
    policyKeys,
    policyRecords,
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
  /** `POST /configs/agent-session` under the executor's bearer. A tag that is not the grant's is refused, as the account refuses it. */
  const openSession = async (init?: RequestInit): Promise<Response> => {
    expect(init?.headers).toMatchObject({ authorization: `Bearer ${EXECUTOR_TOKEN}` });
    const body = JSON.parse(init?.body as string) as { grantId: string; authTag: string };
    account.openBodies.push(body);
    if (account.failNextOpenWith) {
      const status = account.failNextOpenWith;
      account.failNextOpenWith = undefined;
      return json({ error: 'down' }, status);
    }
    const grant = byId.get(body.grantId);
    const tagMatches =
      grant !== undefined && (await hashAuthTag(body.authTag)) === grant.authTagHash;
    if (!grant || !tagMatches || account.refused.has(body.grantId)) {
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
      policyKeys: grant.policyKeys,
      orgRole: grant.orgRole,
      userEmail: grant.userEmail,
      teamSlug: grant.teamSlug,
    });
  };

  /** The config store: a config token, no Authorization; every answer rotates the token. */
  const storeRequest = (url: string, path: string, init?: RequestInit): Response => {
    const token = (init?.headers as Record<string, string>)['X-Config-Token'];
    const grantId = tokens.get(token);
    if (account.expireNextToken) {
      account.expireNextToken = false;
      return json({ code: 'token_expired', error: 'expired' }, 401);
    }
    const grant = grantId === undefined ? undefined : byId.get(grantId);
    if (!grant) return json({ code: 'invalid_token', error: 'unknown' }, 401);
    tokens.delete(token);
    return storeAnswer(grant, url, path, mint(grant.grantId));
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
        return (account.holdOpens ?? Promise.resolve()).then(() => openSession(init));
      }
      return Promise.resolve(storeRequest(String(url), path, init));
    }) as unknown as typeof fetch,
  };
  return account;
}
