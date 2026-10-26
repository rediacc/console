/**
 * C2: a session records the org that opened it. grantCek and sessionForExec refuse
 * a principal of another org with the indistinguishable EXECUTOR_SESSION_UNKNOWN
 * code, the self-check tolerates an issued token with no creator, and two users'
 * sessions never share a decrypted-config cache entry. Real X25519 and real
 * config ciphertext; only the account server is a fake.
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
import { describe, expect, it, vi } from 'vitest';
import { AuthVerifier } from '../auth.js';
import { createContainerConfigLoader } from '../container-config.js';
import { serveCrypto } from '../crypto.js';
import {
  SESSION_UNKNOWN_CODE,
  SessionError,
  type SessionPrincipal,
  SessionStore,
} from '../sessions.js';

const principal = (orgId: string, userId: string): SessionPrincipal => ({
  orgId,
  teamId: null,
  userId,
  userEmail: `${userId}@example.com`,
  orgRole: 'owner',
});

const ALICE_A = principal('org-a', 'user-alice');
const ALICE_B = principal('org-b', 'user-alice');
const BOB_A = principal('org-a', 'user-bob');

function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(data.byteLength);
  copy.set(data);
  return copy.buffer;
}

async function openSession(store: SessionStore, who: SessionPrincipal, cek?: CryptoKey) {
  const { sessionId, publicKey } = await store.open(
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
  const blob = await cekHandoffEncrypt(
    await exportAesKey(cek ?? (await generateCek())),
    executorKey
  );
  return { sessionId, blob };
}

async function expectUnknown(run: () => unknown): Promise<void> {
  let caught: unknown;
  try {
    await run();
  } catch (error) {
    caught = error;
  }
  expect(caught).toBeInstanceOf(SessionError);
  expect((caught as SessionError).code).toBe(SESSION_UNKNOWN_CODE);
  expect((caught as SessionError).message).toBe('Unknown or expired session. Open a new one.');
}

describe('session org binding', () => {
  it('refuses grantCek from the same user id in another org as an unknown session', async () => {
    const store = new SessionStore();
    const { sessionId, blob } = await openSession(store, ALICE_A);

    await expectUnknown(() => store.grantCek(sessionId, blob, ALICE_B));
    expect(() => store.requireCek(sessionId)).toThrow(/no config key yet/);

    // The opener in the right org still completes the grant.
    await store.grantCek(sessionId, blob, ALICE_A);
    expect(store.requireCek(sessionId)).toBeDefined();
  });

  it('refuses sessionForExec for a named session and for the grant index across orgs', async () => {
    const store = new SessionStore();
    const { sessionId, blob } = await openSession(store, ALICE_A);
    await store.grantCek(sessionId, blob, ALICE_A);

    await expectUnknown(() => store.sessionForExec(ALICE_B, sessionId));
    expect(store.sessionForExec(ALICE_B)).toBeUndefined();
    expect(store.sessionForExec(ALICE_A, sessionId)).toBe(sessionId);
    expect(store.sessionForExec(ALICE_A)).toBe(sessionId);
  });

  it('keeps a user with live sessions in two orgs independently reachable', async () => {
    const store = new SessionStore();
    const a = await openSession(store, ALICE_A);
    await store.grantCek(a.sessionId, a.blob, ALICE_A);
    const b = await openSession(store, ALICE_B);
    await store.grantCek(b.sessionId, b.blob, ALICE_B);

    expect(store.sessionFor(ALICE_A)).toBe(a.sessionId);
    expect(store.sessionFor(ALICE_B)).toBe(b.sessionId);

    // Closing one org's session leaves the other's index slot intact.
    store.close(a.sessionId);
    expect(store.sessionFor(ALICE_A)).toBeUndefined();
    expect(store.sessionFor(ALICE_B)).toBe(b.sessionId);
  });

  it('answers the same for a foreign-org session and for one that never existed', async () => {
    const store = new SessionStore();
    const { sessionId } = await openSession(store, ALICE_A);

    const message = (run: () => unknown) => {
      try {
        run();
      } catch (error) {
        return error as SessionError;
      }
      throw new Error('expected a refusal');
    };
    const foreign = message(() => store.sessionForExec(ALICE_B, sessionId));
    const missing = message(() => store.sessionForExec(ALICE_B, 'no-such-session'));
    expect(foreign.message).toBe(missing.message);
    expect(foreign.code).toBe(missing.code);
  });
});

describe('capability self-check', () => {
  it('tolerates an issued token with no creator', async () => {
    const fetchImpl = vi.fn(() =>
      Promise.resolve(
        Response.json({
          active: true,
          scopes: ['proxy:exec', 'audit:write'],
          orgId: 'org-a',
          teamId: null,
          createdByUserId: null,
          userEmail: null,
          orgRole: null,
        })
      )
    );
    const auth = new AuthVerifier({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_issued',
      pinnedOrgId: 'org-a',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(await auth.canWriteAudit()).toEqual({ ok: true });
  });
});

describe('config cache', () => {
  it('never shares a decrypted-config entry between two users', async () => {
    const configId = '00000000-0000-0000-0000-0000000000aa';
    const config: RdcConfig = {
      schemaVersion: 3,
      id: configId,
      version: 1,
      resources: { machines: {}, repositories: {} },
      encryption: { mode: 'plaintext' },
    } as RdcConfig;

    const sessions = new SessionStore();
    // One org-wide CEK, as production has: both users' sessions hold the same key.
    const cek = await generateCek();
    const alice = await openSession(sessions, ALICE_A, cek);
    const bob = await openSession(sessions, BOB_A, cek);
    await sessions.grantCek(alice.sessionId, alice.blob, ALICE_A);
    await sessions.grantCek(bob.sessionId, bob.blob, BOB_A);
    const sdkEpoch = 7;
    const sdkDerived = await sdkDerive(generateSdkMaster(), sdkEpoch);
    const payload = await buildConfigPushPayload(config, {
      storeId: 'store-1',
      version: 1,
      sdkEpoch,
      sdkDerived,
      cek,
    });

    const sdkDerivedB64 = toBase64(await exportAesKey(sdkDerived));
    const mints: string[] = [];
    const fetchImpl = vi.fn((url: string | URL, init?: RequestInit) => {
      const href = String(url);
      if (href.includes('/configs/executor-token')) {
        const body = JSON.parse(String(init?.body)) as { userId: string };
        mints.push(body.userId);
        return Promise.resolve(
          Response.json({
            token: 'rct',
            storeId: 'store-1',
            serverSecret: toBase64(new Uint8Array(32)),
            configs: [{ configId, teamId: null, version: 1 }],
          })
        );
      }
      return Promise.resolve(
        Response.json({
          newServerToken: 'rct2',
          sdk_derived: sdkDerivedB64,
          configData: payload.encryptedBlob,
          envelope: payload.envelope,
          hmac: payload.hmac,
        })
      );
    }) as unknown as typeof fetch;

    const load = createContainerConfigLoader({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      sessions,
      fetchImpl,
    });

    const forAlice = await load(ALICE_A);
    const forBob = await load(BOB_A);
    expect(forAlice).not.toBe(forBob);
    expect(mints).toEqual(['user-alice', 'user-bob']);

    // A second load of the same user is the warm hit; the other user's entry stays theirs.
    expect(await load(ALICE_A)).toBe(forAlice);
    expect(await load(BOB_A)).toBe(forBob);
    expect(mints).toHaveLength(2);

    // Closing one session drops only that user's entry.
    sessions.close(alice.sessionId);
    await expect(load(ALICE_A)).rejects.toBeInstanceOf(SessionError);
    expect(await load(BOB_A)).toBe(forBob);
  });
});
