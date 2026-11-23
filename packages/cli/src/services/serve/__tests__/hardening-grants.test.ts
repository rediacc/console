/**
 * Design 6 of PLAN-rmcp-executor-hardening (executor side): the grant index is
 * keyed by (org, user, team) and holds every live grant, so a second grant never
 * silently replaces the first. Real X25519; no account server involved.
 */

import {
  cekHandoffEncrypt,
  exportAesKey,
  fromBase64,
  generateCek,
} from '@rediacc/shared/config-crypto';
import { describe, expect, it } from 'vitest';
import { serveCrypto } from '../crypto.js';
import { type SessionPrincipal, SessionStore } from '../sessions.js';

const asTeam = (teamId: string | null): SessionPrincipal => ({
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

async function grant(sessions: SessionStore, who: SessionPrincipal): Promise<string> {
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
    await cekHandoffEncrypt(await exportAesKey(await generateCek()), executorKey),
    who
  );
  return sessionId;
}

describe('grants per (org, user, team)', () => {
  it('resolves two grants of one user in two teams, and revoking one leaves the other', async () => {
    const sessions = new SessionStore();
    const inA = await grant(sessions, TEAM_A);
    const inB = await grant(sessions, TEAM_B);

    expect(sessions.sessionFor(TEAM_A)).toBe(inA);
    expect(sessions.sessionFor(TEAM_B)).toBe(inB);

    sessions.close(inA);
    expect(sessions.sessionFor(TEAM_A)).toBeUndefined();
    expect(sessions.sessionFor(TEAM_B)).toBe(inB);
  });

  it('keeps both grants of one team: the newest wins, and closing it falls back to the other', async () => {
    let clock = 1_000_000;
    const sessions = new SessionStore({ now: () => clock });
    const older = await grant(sessions, TEAM_A);
    clock += 1_000;
    const newer = await grant(sessions, TEAM_A);

    expect(sessions.sessionFor(TEAM_A)).toBe(newer);
    sessions.close(newer);
    expect(sessions.sessionFor(TEAM_A)).toBe(older);
  });

  it('drops an expired grant from the lookup', async () => {
    let clock = 1_000_000;
    const sessions = new SessionStore({ now: () => clock, ttlMs: 60_000 });
    const stale = await grant(sessions, TEAM_A);
    clock += 50_000;
    const live = await grant(sessions, TEAM_B);
    clock += 20_000; // the team-A grant idles past its TTL, the team-B one does not

    expect(sessions.sessionFor(TEAM_A)).toBeUndefined();
    expect(sessions.sessionFor(TEAM_B)).toBe(live);
    expect(stale).not.toBe(live);
  });
});
