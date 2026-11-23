/**
 * Designs 4 and 5 of PLAN-rmcp-executor-hardening: the container tier caches a
 * decrypted config per (session, team), so one user's team-A and team-B
 * requests run against two different configs, and a warm entry is checked
 * against the store's current version before each command, so a push from
 * another device is seen on the next request.
 *
 * Real X25519 and real config ciphertext; only the account server is a fake.
 */

import {
  cekHandoffEncrypt,
  exportAesKey,
  fromBase64,
  generateCek,
  generateSdkMaster,
  sdkDerive,
  toBase64,
} from '@rediacc/shared/config-crypto';
import { buildConfigPushPayload, type RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import { createContainerConfigLoader } from '../container-config.js';
import { serveCrypto } from '../crypto.js';
import { SessionError, type SessionPrincipal, SessionStore } from '../sessions.js';

const STORE_ID = 'store-1';
const CONFIG_A = '00000000-0000-0000-0000-00000000000a';
const CONFIG_B = '00000000-0000-0000-0000-00000000000b';

const asTeam = (teamId: string): SessionPrincipal => ({
  orgId: 'org-1',
  teamId,
  userId: 'user-1',
  userEmail: 'user-1@example.com',
  orgRole: 'member',
});
const TEAM_A = asTeam('team-a');
const TEAM_B = asTeam('team-b');

function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(data.byteLength);
  copy.set(data);
  return copy.buffer;
}

function configNamed(id: string, version: number, machine: string): RdcConfig {
  return {
    schemaVersion: 3,
    id,
    version,
    resources: {
      machines: { [machine]: { ip: '10.0.0.1', user: 'root' } },
      repositories: {},
    },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

/** A fake account server holding one config per team, each pushable by "another device". */
async function fakeStore(cek: CryptoKey) {
  const sdkEpoch = 7;
  const sdkDerived = await sdkDerive(generateSdkMaster(), sdkEpoch);
  const sdkDerivedB64 = toBase64(await exportAesKey(sdkDerived));
  const seal = (config: RdcConfig, teamId: string) =>
    buildConfigPushPayload(config, {
      storeId: STORE_ID,
      version: config.version as number,
      sdkEpoch,
      sdkDerived,
      cek,
      teamId,
    });
  const stored = new Map<string, { version: number; payload: Awaited<ReturnType<typeof seal>> }>();
  const teamOf: Record<string, string> = { [CONFIG_A]: 'team-a', [CONFIG_B]: 'team-b' };
  for (const [configId, machine] of [
    [CONFIG_A, 'machine-of-a'],
    [CONFIG_B, 'machine-of-b'],
  ] as const) {
    stored.set(configId, {
      version: 1,
      payload: await seal(configNamed(configId, 1, machine), teamOf[configId]),
    });
  }
  const calls = { pulls: 0, listings: 0 };

  const fetchImpl = ((url: string | URL) => {
    const href = String(url);
    if (href.includes('/configs/executor-token')) {
      return Promise.resolve(
        Response.json({
          token: 'rct',
          storeId: STORE_ID,
          serverSecret: toBase64(new Uint8Array(32)),
          configs: [...stored.entries()].map(([configId, entry]) => ({
            configId,
            teamId: teamOf[configId],
            version: entry.version,
          })),
        })
      );
    }
    if (href.endsWith('/configs')) {
      calls.listings += 1;
      return Promise.resolve(
        Response.json({
          newServerToken: 'rct',
          configs: [...stored.entries()].map(([configId, entry]) => ({
            configId,
            teamId: teamOf[configId],
            version: entry.version,
            lastModified: '',
          })),
        })
      );
    }
    const configId = decodeURIComponent(new URL(href).pathname.split('/').pop() ?? '');
    const entry = stored.get(configId);
    if (!entry) return Promise.resolve(Response.json({ error: 'not found' }, { status: 404 }));
    calls.pulls += 1;
    return Promise.resolve(
      Response.json({
        newServerToken: 'rct',
        sdk_derived: sdkDerivedB64,
        configData: entry.payload.encryptedBlob,
        envelope: entry.payload.envelope,
        hmac: entry.payload.hmac,
      })
    );
  }) as typeof fetch;

  /** Another device pushes a new version of `configId` naming `machine`. */
  const externalPush = async (configId: string, machine: string) => {
    const entry = stored.get(configId);
    if (!entry) throw new Error(`no config ${configId}`);
    const version = entry.version + 1;
    stored.set(configId, {
      version,
      payload: await seal(configNamed(configId, version, machine), teamOf[configId]),
    });
  };

  return { fetchImpl, calls, externalPush };
}

async function grantedSession(sessions: SessionStore, who: SessionPrincipal, cek: CryptoKey) {
  const { sessionId, publicKey } = await sessions.open(
    who,
    serveCrypto.generateEphemeralKeyPair,
    serveCrypto.exportPublicKey
  );
  const executorKey = await crypto.subtle.importKey(
    'spki',
    toArrayBuffer(fromBase64(publicKey)),
    { name: 'X25519' },
    false,
    []
  );
  await sessions.grantCek(
    sessionId,
    await cekHandoffEncrypt(await exportAesKey(cek), executorKey),
    who
  );
  return sessionId;
}

const machinesOf = (config: RdcConfig) => Object.keys(config.resources.machines ?? {});

describe('container config cache keyed by (session, team)', () => {
  it("serves one user's team-A then team-B requests two different configs", async () => {
    const cek = await generateCek();
    const store = await fakeStore(cek);
    const sessions = new SessionStore();
    const sessionId = await grantedSession(sessions, TEAM_A, cek);
    const load = createContainerConfigLoader({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      sessions,
      fetchImpl: store.fetchImpl,
    });

    const forA = await load(TEAM_A, sessionId);
    const forB = await load(TEAM_B, sessionId);
    expect(machinesOf(forA)).toEqual(['machine-of-a']);
    expect(machinesOf(forB)).toEqual(['machine-of-b']);
    expect(store.calls.pulls).toBe(2);

    // Each team's warm entry stays its own.
    expect(machinesOf(await load(TEAM_A, sessionId))).toEqual(['machine-of-a']);
    expect(machinesOf(await load(TEAM_B, sessionId))).toEqual(['machine-of-b']);
    expect(store.calls.pulls).toBe(2);
  });
});

describe('container config revalidation', () => {
  it('shows a push from another device on the next request', async () => {
    const cek = await generateCek();
    const store = await fakeStore(cek);
    const sessions = new SessionStore();
    const sessionId = await grantedSession(sessions, TEAM_A, cek);
    const load = createContainerConfigLoader({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      sessions,
      fetchImpl: store.fetchImpl,
    });

    expect(machinesOf(await load(TEAM_A, sessionId))).toEqual(['machine-of-a']);
    await store.externalPush(CONFIG_A, 'pushed-elsewhere');

    const next = await load(TEAM_A, sessionId);
    expect(machinesOf(next)).toEqual(['pushed-elsewhere']);
    expect(next.version).toBe(2);
    expect(store.calls.listings).toBe(1);
    expect(store.calls.pulls).toBe(2);
  });

  it('pulls nothing when the version has not moved (control)', async () => {
    const cek = await generateCek();
    const store = await fakeStore(cek);
    const sessions = new SessionStore();
    const sessionId = await grantedSession(sessions, TEAM_A, cek);
    const load = createContainerConfigLoader({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      sessions,
      fetchImpl: store.fetchImpl,
    });

    const first = await load(TEAM_A, sessionId);
    expect(await load(TEAM_A, sessionId)).toBe(first);
    expect(store.calls.listings).toBe(1);
    expect(store.calls.pulls).toBe(1);
  });

  it('refuses the request when the version cannot be checked', async () => {
    const cek = await generateCek();
    const store = await fakeStore(cek);
    const sessions = new SessionStore();
    const sessionId = await grantedSession(sessions, TEAM_A, cek);
    let listingDown = false;
    const fetchImpl = ((url: string | URL, init?: RequestInit) =>
      listingDown && String(url).endsWith('/configs')
        ? Promise.resolve(Response.json({ error: 'unavailable' }, { status: 503 }))
        : store.fetchImpl(url, init)) as typeof fetch;
    const load = createContainerConfigLoader({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      sessions,
      fetchImpl,
    });

    await load(TEAM_A, sessionId);
    listingDown = true;
    const refusal = await load(TEAM_A, sessionId).catch((error: unknown) => error);
    expect(refusal).toBeInstanceOf(SessionError);
    expect((refusal as Error).message).toMatch(/could not check the config version.*503/);
  });
});
