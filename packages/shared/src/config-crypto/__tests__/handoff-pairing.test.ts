/**
 * Known-answer vector for the CLI relay handoff fingerprint and pairing code.
 *
 * The CLI, the portal and the E2E helpers all derive these from the same
 * functions; this vector pins the output so a drift in any build shows up.
 * The expected values were computed independently with Python's hashlib.
 */

import { describe, expect, it } from 'vitest';
import { handoffKeyHash, handoffPairingCode, handoffPollVerifier } from '../handoff.js';

// X25519 SPKI header + the RFC 7748 section 6.1 Alice public key.
const FIXED_SPKI = Uint8Array.from(
  Buffer.from(
    '302a300506032b656e032100' + '8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a',
    'hex'
  )
);
const EXPECTED_KEY_HASH = 'KRxSk-AwRSpZmFGnxymPPxbD_xvfr8tZiSfyYx-fpkE';
const EXPECTED_PAIRING_CODE = 'FEQF-FE9A-GBCU';

describe('handoffKeyHash', () => {
  it('matches the known-answer vector', async () => {
    expect(await handoffKeyHash(FIXED_SPKI)).toBe(EXPECTED_KEY_HASH);
  });

  it('is 43 base64url characters with no padding', async () => {
    const random = crypto.getRandomValues(new Uint8Array(44));
    const hash = await handoffKeyHash(random);
    expect(hash).toMatch(/^[\w-]{43}$/);
  });
});

describe('handoffPairingCode', () => {
  it('matches the known-answer vector', async () => {
    expect(await handoffPairingCode(FIXED_SPKI)).toBe(EXPECTED_PAIRING_CODE);
  });

  it('uses only the 32-symbol alphabet in XXXX-XXXX-XXXX form', async () => {
    for (let i = 0; i < 20; i++) {
      const code = await handoffPairingCode(crypto.getRandomValues(new Uint8Array(44)));
      expect(code).toMatch(/^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$/);
    }
  });

  it('changes when a single key bit changes', async () => {
    const flipped = Uint8Array.from(FIXED_SPKI);
    flipped[flipped.length - 1] ^= 1;
    expect(await handoffPairingCode(flipped)).not.toBe(EXPECTED_PAIRING_CODE);
  });
});

describe('handoffPollVerifier', () => {
  // S = bytes 0x00..0x1f, sent as 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8'.
  const RAW_SECRET = Uint8Array.from({ length: 32 }, (_, i) => i);

  it('hashes the raw 32 secret bytes (the known-answer vector)', async () => {
    expect(await handoffPollVerifier(RAW_SECRET)).toBe(
      'Yw3NKWbEM2aRElRIu7JbT_QSpJxzLbLIq8G4WBvXEN0'
    );
  });

  it('is not the hash of the base64url text the CLI sends', async () => {
    const text = new TextEncoder().encode('AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8');
    expect(await handoffPollVerifier(text)).not.toBe('Yw3NKWbEM2aRElRIu7JbT_QSpJxzLbLIq8G4WBvXEN0');
  });
});
