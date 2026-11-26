/**
 * Review 7703789b.2, .3: the production wiring that records an AI chat turn (server.ts chatRecording).
 *
 * A config the store named a CEK generation for is sealed under the session's granted key at that
 * generation. A config with none (the daemon's enrolled file) is refused with the reason, which is
 * how the chat route warns instead of recording a turn the store could not open. The ai-routes tests
 * inject their own recording object, so this binding is tested here against a real SessionStore.
 */

import {
  cekHandoffEncrypt,
  exportAesKey,
  fromBase64,
  generateCek,
} from '@rediacc/shared/config-crypto';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../config-writeback.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../config-writeback.js')>()),
  // The generation the store wrapped a config under; a test config carries it as a field.
  cekGenerationOf: (config: RdcConfig) => (config as unknown as { gen?: number }).gen,
}));

import { outputService } from '../../core/output.js';
import { serveCrypto } from '../crypto.js';
import type { ServeDeps } from '../deps.js';
import { chatRecording } from '../server.js';
import { type SessionPrincipal, SessionStore } from '../sessions.js';

const ALICE: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-alice',
  userEmail: 'alice@example.com',
  orgRole: 'owner',
};

function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(data.byteLength);
  copy.set(data);
  return copy.buffer;
}

async function grantedSession(store: SessionStore) {
  const { sessionId, publicKey } = await store.open(
    ALICE,
    serveCrypto.generateEphemeralKeyPair,
    serveCrypto.exportPublicKey
  );
  const rawCek = await exportAesKey(await generateCek());
  const key = await crypto.subtle.importKey(
    'spki',
    toArrayBuffer(fromBase64(publicKey)),
    { name: 'X25519' },
    false,
    []
  );
  await store.grantCek(sessionId, await cekHandoffEncrypt(rawCek, key), ALICE);
  return { sessionId, rawCek };
}

function recording(store: SessionStore) {
  const deps = { sessions: store } as unknown as ServeDeps;
  return chatRecording(deps, {
    record: () => Promise.resolve('recorded' as never),
    pendingConversations: () => 0,
  });
}

const withGeneration = (gen?: number) => ({ gen }) as unknown as RdcConfig;

describe('chatRecording (the chat route production wiring)', () => {
  it('seals under the granted session key at the generation the store named', async () => {
    const store = new SessionStore();
    const { rawCek } = await grantedSession(store);

    const key = recording(store).keyOf(ALICE, withGeneration(3), undefined);

    expect(typeof key).toBe('object');
    if (typeof key === 'string') return;
    expect(key.cekGeneration).toBe(3);
    expect(Array.from((await key.cek()) ?? [])).toEqual(Array.from(rawCek));
  });

  it('refuses a config with no CEK generation, naming why (the daemon case)', async () => {
    const store = new SessionStore();
    await grantedSession(store);

    const key = recording(store).keyOf(ALICE, withGeneration(undefined), undefined);

    expect(key).toMatch(/named no CEK generation/);
  });

  it('control: a principal with no granted session gets no key bytes, and no throw', async () => {
    const store = new SessionStore();
    await grantedSession(store);
    const stranger = { ...ALICE, userId: 'user-bob' };

    const key = recording(store).keyOf(stranger, withGeneration(1), undefined);

    expect(typeof key).toBe('object');
    if (typeof key === 'string') return;
    await expect(key.cek()).resolves.toBeUndefined();
  });

  it('warns through the output service when a turn is not recorded', () => {
    const warn = vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);
    recording(new SessionStore()).onUnrecorded?.('no key', 'conv-1');
    expect(warn).toHaveBeenCalledWith('AI conversation conv-1 is not recorded: no key');
    warn.mockRestore();
  });
});
