/**
 * The write-back tests' account server and container executor
 * (agent/plans/PLAN-rmcp-writeback.md WB1-WB3, WB7).
 *
 * The fake account server keeps one config the way the real one does: as the
 * ciphertext the last push sent, behind a compare-and-swap on its version, with
 * config tokens that rotate on every use and allow three uses each. A push must
 * prove every committed key it drops with a tombstone equal to the stored
 * commitment, as the server's anti-downgrade rule demands. Nothing about the
 * crypto is stubbed: the executor really pulls, decrypts with the session's
 * granted key, re-encrypts and pushes, and the test reads the result back by
 * decrypting what the fake stored.
 *
 * `bootContainerExecutor` runs the real serve app in container mode over real
 * HTTP, with a real X25519 key grant, so the wiring from loader to request scope
 * to configFileStorage is the production one.
 */

import type { AddressInfo } from 'node:net';
import { serve } from '@hono/node-server';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import {
  cekHandoffEncrypt,
  encryptPolicyRecord,
  exportAesKey,
  fromBase64,
  generateCek,
  generateSdkMaster,
  sdkDerive,
  toBase64,
} from '@rediacc/shared/config-crypto';
import { fullConfigToRdcConfig } from '@rediacc/shared/config-crypto/rotation';
import {
  buildConfigPushPayload,
  decryptConfigPullPayload,
  type RdcConfig,
} from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import type { ExecuteOptions, ExecuteResult, Executor } from '../../executor/types.js';
import { AuthVerifier } from '../auth.js';
import { createContainerConfigLoader, createExecutorGrantRecorder } from '../container-config.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { authorize } from '../policy.js';
import { createServeApp } from '../server.js';
import { SessionStore } from '../sessions.js';

export const OWNER_TOKEN = 'rdt_owner';
export const EXECUTOR_TOKEN = 'rdt_executor';
export const STORE_ID = 'store-1';
export const CONFIG_ID = '00000000-0000-4000-8000-0000000000aa';
const ACCOUNT_URL = 'https://account.test';
const TOKEN_MAX_USES = 3;

const PRINCIPALS: Record<string, unknown> = {
  [EXECUTOR_TOKEN]: {
    active: true,
    scopes: ['proxy:exec', 'audit:write'],
    orgId: 'org-1',
    teamId: null,
    createdByUserId: 'user-executor',
    userEmail: 'executor@example.com',
    orgRole: 'admin',
  },
  [OWNER_TOKEN]: {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: null,
    createdByUserId: 'user-owner',
    userEmail: 'owner@example.com',
    orgRole: 'owner',
  },
};

/** A PUT the fake accepted or refused, with what it carried. */
export interface PutRecord {
  version: number;
  status: number;
  removedKeys: string[];
}

interface StoredCommitments {
  fckSalt: string;
  fields: Record<string, { hmac: string; kind: string }>;
  removed?: Record<string, { hmac: string; kind: string }>;
  migrated?: unknown;
}

interface StoredEnvelope {
  envelopeVersion: 2 | 3;
  configId: string;
  version: number;
  teamId: string | null;
  lastModified: string;
  sdkEpoch: number;
  commitments: StoredCommitments;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

export interface FakeConfigStore {
  cek: CryptoKey;
  fetch: typeof fetch;
  /** The config as the store holds it, decrypted with the session key. */
  current(): Promise<RdcConfig>;
  version(): number;
  puts: PutRecord[];
  pulls: number;
  /** GET /configs listings, the version check a warm session makes before each command. */
  listings: number;
  /** Bodies of every executor-token mint. */
  mints: { userId: string; sessionId: string; write?: boolean }[];
  /** Push an edit as another device would, bumping the version. */
  externalPush(edit: (config: RdcConfig) => RdcConfig): Promise<void>;
  /** Called before the fake answers a PUT, after the token check: a test injects a racing push here. */
  beforePut?: () => Promise<void>;
  /** When false, answers carry no rotated token, so the executor reuses one token until it is spent. */
  rotate: boolean;
  /** When true, a minted token is born spent (every use answers 401 token_exhausted). */
  mintSpent: boolean;
  /** Config requests refused with 401 because their token was spent. */
  exhausted: number;
}

/** A policy that lets every command through, grand repos included: the writeback tests exercise the push, not the policy. */
export const OPEN_POLICY: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['*'] }, allowGrandRepos: true },
};

/**
 * A fake account server holding `initial`, encrypted under a fresh config key, with `policy` (when
 * given) as the config's policy record, served beside the blob on every pull.
 */
export async function createFakeConfigStore(
  seed: RdcConfig,
  policy?: PolicyDocument
): Promise<FakeConfigStore> {
  // The document's id is the config id the envelope (and its AAD binding) carries.
  const initial = { ...seed, id: CONFIG_ID };
  const cek = await generateCek();
  const sdkEpoch = 4242;
  const sdkDerived = await sdkDerive(generateSdkMaster(), sdkEpoch);
  const sdkDerivedB64 = toBase64(await exportAesKey(sdkDerived));
  const first = await buildConfigPushPayload(initial, {
    storeId: STORE_ID,
    version: initial.version,
    sdkEpoch,
    sdkDerived,
    cek,
  });
  const policyRecord = policy
    ? await encryptPolicyRecord(policy, cek, {
        storeId: STORE_ID,
        configId: CONFIG_ID,
        teamId: null,
        version: 1,
        cekGeneration: 1,
      })
    : null;
  let stored = {
    version: initial.version,
    encryptedBlob: first.encryptedBlob,
    envelope: first.envelope as unknown as StoredEnvelope,
    hmac: first.hmac,
  };
  const tokens = new Map<string, { uses: number; writable: boolean }>();
  const grants = new Map<string, string>();
  let tokenSeq = 0;

  const issue = (writable: boolean, spent = false): string => {
    tokenSeq += 1;
    const token = `rct_${tokenSeq}`;
    tokens.set(token, { uses: spent ? TOKEN_MAX_USES : 0, writable });
    return token;
  };

  const decryptStored = async (): Promise<RdcConfig> => {
    const decrypted = await decryptConfigPullPayload(
      {
        envelope: stored.envelope as never,
        encryptedBlob: stored.encryptedBlob,
        hmac: stored.hmac,
      },
      { cek, sdkDerived, binding: { storeId: STORE_ID, configId: CONFIG_ID, teamId: null } }
    );
    return { ...fullConfigToRdcConfig(decrypted), version: stored.version };
  };

  /** The server's anti-downgrade rule: a stored key may vanish only against a tombstone equal to it. */
  const tombstonesProve = (pushed: StoredCommitments): boolean => {
    const before = stored.envelope.commitments.fields;
    for (const [key, commitment] of Object.entries(before)) {
      if (key in pushed.fields) continue;
      if (pushed.removed?.[key]?.hmac !== commitment.hmac) return false;
    }
    return true;
  };

  /** Claim one use of the presented token: the answer's rotation field and whether it may write, or a 401 answer. */
  const claim = (
    token: string
  ): { rotated: Record<string, string>; writable: boolean } | Response => {
    const entry = tokens.get(token);
    if (!entry)
      return json({ error: 'Config auth failed: invalid_token', code: 'invalid_token' }, 401);
    if (entry.uses >= TOKEN_MAX_USES) {
      fake.exhausted += 1;
      return json({ error: 'Config auth failed: token_exhausted', code: 'token_exhausted' }, 401);
    }
    entry.uses += 1;
    return {
      rotated: fake.rotate ? { newServerToken: issue(entry.writable) } : {},
      writable: entry.writable,
    };
  };

  /** The stored document replaced by an accepted push; the server keeps neither tombstones nor the v2 key map. */
  const store = (body: { version: number; encryptedBlob: string; envelope: StoredEnvelope }) => {
    const { removed: _removed, migrated: _migrated, ...kept } = body.envelope.commitments;
    stored = {
      version: body.version,
      encryptedBlob: body.encryptedBlob,
      envelope: { ...body.envelope, commitments: kept },
      hmac: null,
    };
  };

  /** The 409 a push meets: a lost compare-and-swap, or a dropped key without its tombstone. */
  const casRefusal = (
    body: { version: number; envelope: StoredEnvelope },
    rotated: Record<string, string>
  ): Response | undefined => {
    if (body.version !== stored.version + 1) {
      return json({ ...rotated, error: 'Version conflict' }, 409);
    }
    if (!tombstonesProve(body.envelope.commitments)) {
      return json(
        { ...rotated, error: 'precondition', code: 'precondition_failed', mismatchedPaths: [] },
        409
      );
    }
    return undefined;
  };

  /** POST /configs/session and GET /configs/:id answers. */
  const sessionAnswer = (rotated: Record<string, string>): Response =>
    json({
      ...rotated,
      server_secret: toBase64(new Uint8Array(32)),
      sdk_derived: sdkDerivedB64,
      sdkEpoch,
    });
  const pullAnswer = (rotated: Record<string, string>): Response => {
    fake.pulls += 1;
    return json({
      ...rotated,
      sdk_derived: sdkDerivedB64,
      configData: stored.encryptedBlob,
      envelope: stored.envelope,
      hmac: stored.hmac,
      // The account server serves the policy record beside the config.
      policy: policyRecord,
    });
  };

  /** PUT /configs/:id: read-only refusal, compare-and-swap, the tombstone rule, then the store. */
  const put = async (
    rotated: Record<string, string>,
    writable: boolean,
    raw: string
  ): Promise<Response> => {
    if (!writable) {
      return json(
        { ...rotated, error: 'This config token is read-only.', code: 'read_only_token' },
        403
      );
    }
    await fake.beforePut?.();
    const body = JSON.parse(raw) as {
      version: number;
      encryptedBlob: string;
      envelope: StoredEnvelope;
    };
    const removedKeys = Object.keys(body.envelope.commitments.removed ?? {});
    const refusal = casRefusal(body, rotated);
    fake.puts.push({ version: body.version, status: refusal ? 409 : 200, removedKeys });
    if (refusal) return refusal;
    store(body);
    return json({ ...rotated, version: body.version, sdkEpoch });
  };

  const configCall = (href: string, init?: RequestInit): Promise<Response> => {
    const claimed = claim((init?.headers as Record<string, string>)['X-Config-Token']);
    if (claimed instanceof Response) return Promise.resolve(claimed);
    let kind = 'config';
    if (href.endsWith('/configs/session')) kind = 'session';
    else if (href.endsWith('/configs')) kind = 'list';
    const call = `${init?.method ?? 'GET'} ${kind}`;
    switch (call) {
      case 'GET list':
        fake.listings += 1;
        return Promise.resolve(
          json({
            ...claimed.rotated,
            configs: [
              { configId: CONFIG_ID, teamId: null, version: stored.version, lastModified: '' },
            ],
          })
        );
      case 'PUT config':
        return put(claimed.rotated, claimed.writable, init?.body as string);
      case 'POST session':
        return Promise.resolve(sessionAnswer(claimed.rotated));
      case 'GET config':
        return Promise.resolve(pullAnswer(claimed.rotated));
      default:
        throw new Error(`unexpected config call: ${call} ${href}`);
    }
  };

  /** POST /configs/executor-grant: the grantor is the presented bearer's creator. */
  const recordGrant = (raw: string): Response => {
    const body = JSON.parse(raw) as { sessionId: string; token: string };
    const grantor = (PRINCIPALS[body.token] as { createdByUserId?: string } | undefined)
      ?.createdByUserId;
    if (!grantor) return json({ error: 'refused' }, 403);
    grants.set(body.sessionId, grantor);
    return json({ ok: true });
  };

  /** POST /configs/executor-token: minted only for the recorded grantor of the session. */
  const mint = (raw: string): Response => {
    const body = JSON.parse(raw) as { userId: string; sessionId: string; write?: boolean };
    fake.mints.push(body);
    if (grants.get(body.sessionId) !== body.userId) return json({ error: 'not granted' }, 403);
    return json({
      token: issue(body.write === true, fake.mintSpent),
      storeId: STORE_ID,
      serverSecret: toBase64(new Uint8Array(32)),
      configs: [{ configId: CONFIG_ID, teamId: null, version: stored.version }],
    });
  };

  const accountFetch = ((url: string | URL, init?: RequestInit) => {
    const href = String(url);
    const raw = init?.body as string;
    if (href.includes('/proxy/introspect')) {
      const body = JSON.parse(raw) as { token: string };
      return Promise.resolve(json(PRINCIPALS[body.token] ?? { active: false }));
    }
    if (href.includes('/configs/executor-grant')) return Promise.resolve(recordGrant(raw));
    if (href.includes('/configs/executor-token')) return Promise.resolve(mint(raw));
    if (href.includes('/configs/') || href.endsWith('/configs')) return configCall(href, init);
    throw new Error(`unexpected account call: ${href}`);
  }) as typeof fetch;

  const fake: FakeConfigStore = {
    cek,
    fetch: accountFetch,
    current: decryptStored,
    version: () => stored.version,
    puts: [],
    pulls: 0,
    listings: 0,
    mints: [],
    rotate: true,
    mintSpent: false,
    exhausted: 0,
    async externalPush(edit) {
      const base = await decryptStored();
      const next = edit(structuredClone(base));
      const payload = await buildConfigPushPayload(next, {
        storeId: STORE_ID,
        version: stored.version + 1,
        sdkEpoch,
        sdkDerived,
        cek,
        prior: {
          envelopeVersion: stored.envelope.envelopeVersion,
          fckSalt: stored.envelope.commitments.fckSalt,
          base,
        },
      });
      const envelope = payload.envelope as unknown as StoredEnvelope;
      const { removed: _removed, migrated: _migrated, ...kept } = envelope.commitments;
      stored = {
        version: stored.version + 1,
        encryptedBlob: payload.encryptedBlob,
        envelope: { ...envelope, commitments: kept },
        hmac: null,
      };
    },
  };
  return fake;
}

/** A fake renet: records every call; `answer` decides each result (success by default). */
export function fakeRenet(answer?: (options: ExecuteOptions) => ExecuteResult): {
  executor: Executor;
  calls: ExecuteOptions[];
} {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options): Promise<ExecuteResult> {
        calls.push(options);
        return Promise.resolve(
          answer?.(options) ?? { success: true, exitCode: 0, durationMs: 1, stdout: '' }
        );
      },
    },
  };
}

function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

/** The result line of a /v1/command response. */
export interface CommandResultLine {
  kind: 'result';
  result: {
    success: boolean;
    exitCode: number;
    error?: string;
    errorCode?: string;
    jobId?: string;
  };
  stdout?: string;
  stderr?: string;
}

export interface ContainerExecutor {
  baseUrl: string;
  sessions: SessionStore;
  /** Open a session and grant it the store's key over real X25519; answers the session id. */
  grantKey(): Promise<string>;
  /** Run one command; answers its result line. */
  command(
    pathKey: string,
    params: Record<string, unknown>,
    positionals: Record<string, unknown>,
    extra?: { background?: boolean }
  ): Promise<CommandResultLine>;
  close(): Promise<void>;
}

/** The real serve app in container mode, over real HTTP, against `store`. */
export function bootContainerExecutor(
  store: FakeConfigStore,
  executor: Executor,
  overrides: Partial<ServeDeps> = {}
): Promise<ContainerExecutor> {
  const sessions = new SessionStore();
  const deps: ServeDeps = {
    mode: 'container',
    auth: new AuthVerifier({
      accountUrl: ACCOUNT_URL,
      executorToken: EXECUTOR_TOKEN,
      fetchImpl: store.fetch,
    }),
    sessions,
    crypto: serveCrypto,
    executor,
    loadConfig: createContainerConfigLoader({
      accountUrl: ACCOUNT_URL,
      executorToken: EXECUTOR_TOKEN,
      sessions,
      fetchImpl: store.fetch,
    }),
    recordGrant: createExecutorGrantRecorder({
      accountUrl: ACCOUNT_URL,
      executorToken: EXECUTOR_TOKEN,
      fetchImpl: store.fetch,
    }),
    authorize,
    audit: () => Promise.resolve(),
    // The fake renet answers each call synchronously; no job spool.
    detach: () => false,
    ...overrides,
  };
  const server = serve({ fetch: createServeApp(deps).fetch, port: 0 });
  const baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

  return Promise.resolve({
    baseUrl,
    sessions,
    async grantKey() {
      const opened = await fetch(`${baseUrl}/v1/session`, {
        method: 'POST',
        headers: { authorization: `Bearer ${OWNER_TOKEN}` },
      });
      const { sessionId, publicKey } = (await opened.json()) as {
        sessionId: string;
        publicKey: string;
      };
      const executorPublicKey = await crypto.subtle.importKey(
        'spki',
        buf(fromBase64(publicKey)),
        { name: 'X25519' },
        false,
        []
      );
      const blob = await cekHandoffEncrypt(await exportAesKey(store.cek), executorPublicKey);
      const granted = await fetch(`${baseUrl}/v1/session/${sessionId}/cek`, {
        method: 'POST',
        headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
        body: JSON.stringify(blob),
      });
      if (granted.status !== 200) throw new Error(`grant failed: ${await granted.text()}`);
      return sessionId;
    },
    async command(pathKey, params, positionals, extra = {}) {
      const response = await fetch(`${baseUrl}${PROXY_ROUTES.command}`, {
        method: 'POST',
        headers: { authorization: `Bearer ${OWNER_TOKEN}`, 'content-type': 'application/json' },
        body: JSON.stringify({
          contractVersion: CLI_CONTRACT_VERSION,
          pathKey,
          params,
          positionals,
          ...(extra.background ? { background: true } : {}),
        }),
      });
      const text = await response.text();
      if (response.status !== 200) throw new Error(`command refused (${response.status}): ${text}`);
      const lines = text
        .split('\n')
        .filter(Boolean)
        .map((line) => JSON.parse(line) as { kind: string });
      const result = lines.find((line) => line.kind === 'result');
      if (!result) throw new Error(`no result line in: ${text}`);
      return result as CommandResultLine;
    },
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  });
}
