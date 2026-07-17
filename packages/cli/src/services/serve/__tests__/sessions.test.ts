/**
 * Session store: the CEK grant is bound to the principal who opened the session.
 *
 * SEC-3. The grant endpoint authenticates the caller but the STORE is where
 * ownership is enforced, so that a future caller cannot forget the check and
 * quietly reopen the hole. The crypto here is real X25519, because a grant that
 * only works against a mock proves nothing about the boundary.
 */

import {
  cekHandoffEncrypt,
  exportAesKey,
  fromBase64,
  generateCek,
} from '@rediacc/shared/config-crypto';
import { describe, expect, it } from 'vitest';
import { serveCrypto } from '../crypto.js';
import { SessionError, type SessionPrincipal, SessionStore } from '../sessions.js';

const ALICE: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-alice',
  userEmail: 'alice@example.com',
  orgRole: 'owner',
};

// A different real user in the SAME org: same tenant, different person.
const BOB: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-bob',
  userEmail: 'bob@example.com',
  orgRole: 'owner',
};

/** Seal a fresh CEK to a session's public key, exactly as a client would. */
async function sealCekTo(publicKeyB64: string): Promise<{
  blob: Awaited<ReturnType<typeof cekHandoffEncrypt>>;
  rawCek: ArrayBuffer;
}> {
  const cek = await generateCek();
  const rawCek = await exportAesKey(cek);
  const publicKey = await crypto.subtle.importKey(
    'spki',
    fromBase64(publicKeyB64),
    { name: 'X25519' },
    false,
    []
  );
  return { blob: await cekHandoffEncrypt(rawCek, publicKey), rawCek };
}

async function openFor(store: SessionStore, principal: SessionPrincipal) {
  return store.open(principal, serveCrypto.generateEphemeralKeyPair, serveCrypto.exportPublicKey);
}

describe('SessionStore CEK grant ownership (SEC-3)', () => {
  it('accepts a grant from the principal who opened the session', async () => {
    const store = new SessionStore();
    const { sessionId, publicKey } = await openFor(store, ALICE);
    const { blob, rawCek } = await sealCekTo(publicKey);

    await store.grantCek(sessionId, blob, ALICE);

    const held = await exportAesKey(store.requireCek(sessionId));
    expect(Buffer.from(held)).toEqual(Buffer.from(rawCek));
  });

  it('refuses a grant from a DIFFERENT principal, even with a valid token', async () => {
    const store = new SessionStore();
    // Alice opens; her public key is what a grant must seal to.
    const { sessionId, publicKey } = await openFor(store, ALICE);
    const { blob } = await sealCekTo(publicKey);

    // Bob, a real user in the same org, tries to complete Alice's grant.
    await expect(store.grantCek(sessionId, blob, BOB)).rejects.toBeInstanceOf(SessionError);

    // Alice's session is left with no key: a rejected grant does not partially
    // apply, and her later commands cannot run against a key Bob supplied.
    expect(() => store.requireCek(sessionId)).toThrow(/no config key yet/i);
  });

  it('does not reveal whether the session exists when the grant is not the owner', async () => {
    const store = new SessionStore();
    const { sessionId, publicKey } = await openFor(store, ALICE);
    const { blob } = await sealCekTo(publicKey);

    // A wrong-owner grant and a grant to a made-up id must fail the SAME way, so
    // an attacker cannot enumerate live session ids by the error text.
    let ownerMismatch: unknown;
    let unknownId: unknown;
    await store.grantCek(sessionId, blob, BOB).catch((e: unknown) => {
      ownerMismatch = e;
    });
    await store.grantCek('11111111-1111-1111-1111-111111111111', blob, BOB).catch((e: unknown) => {
      unknownId = e;
    });

    expect((ownerMismatch as Error).message).toBe((unknownId as Error).message);
  });

  it('still refuses a second grant to a session that already has its key', async () => {
    const store = new SessionStore();
    const { sessionId, publicKey } = await openFor(store, ALICE);
    const first = await sealCekTo(publicKey);
    await store.grantCek(sessionId, first.blob, ALICE);

    const second = await sealCekTo(publicKey);
    await expect(store.grantCek(sessionId, second.blob, ALICE)).rejects.toThrow(
      /already received its key/i
    );
  });
});

describe('SessionStore.sessionForExec (the X-Config-Session selection rule)', () => {
  /** Open a session for a principal and complete a real grant on it. */
  async function openAndGrant(store: SessionStore, principal: SessionPrincipal): Promise<string> {
    const { sessionId, publicKey } = await openFor(store, principal);
    const { blob } = await sealCekTo(publicKey);
    await store.grantCek(sessionId, blob, principal);
    return sessionId;
  }

  it('falls back to the principal-indexed session when no session is named', async () => {
    const store = new SessionStore();
    const granted = await openAndGrant(store, ALICE);

    expect(store.sessionForExec(ALICE)).toBe(granted);
    expect(store.sessionForExec(BOB)).toBeUndefined();
  });

  it('honours the NAMED session over the latest-grant index', async () => {
    // Alice grants through two live sessions (say, a browser and a CLI). The
    // index points at the newest, but a request that names the older one must
    // get the older one — the client chose it.
    const store = new SessionStore();
    const first = await openAndGrant(store, ALICE);
    const second = await openAndGrant(store, ALICE);

    expect(store.sessionFor(ALICE)).toBe(second);
    expect(store.sessionForExec(ALICE, first)).toBe(first);
  });

  it('refuses a named session that belongs to someone else, indistinguishably', async () => {
    const store = new SessionStore();
    const alices = await openAndGrant(store, ALICE);

    // Bob naming Alice's session and Bob naming a nonexistent one must fail the
    // same way, so the header cannot be used to probe which ids are live.
    let wrongOwner: unknown;
    let unknownId: unknown;
    try {
      store.sessionForExec(BOB, alices);
    } catch (e) {
      wrongOwner = e;
    }
    try {
      store.sessionForExec(BOB, '22222222-2222-2222-2222-222222222222');
    } catch (e) {
      unknownId = e;
    }

    expect(wrongOwner).toBeInstanceOf(SessionError);
    expect(unknownId).toBeInstanceOf(SessionError);
    expect((wrongOwner as Error).message).toBe((unknownId as Error).message);
  });

  it('throws for a named session that never existed', () => {
    const store = new SessionStore();
    expect(() => store.sessionForExec(ALICE, 'no-such-session')).toThrow(SessionError);
  });
});
