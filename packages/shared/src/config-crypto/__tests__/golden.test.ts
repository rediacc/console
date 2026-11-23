/**
 * Golden Vectors — decrypt-direction known-answer tests.
 *
 * Every constant that feeds a key derivation is pinned here twice: once as the
 * exact string/byte value, and once through a precomputed ciphertext that only
 * decrypts if the whole derivation chain still produces the same key. Editing
 * any salt, info string, iteration count, or concatenation order makes these
 * fail LOUDLY — which is exactly the alarm the v1 PRF-salt divergence never
 * had (setup wrote 'rediacc-secret-v1', unlock read 32 zero bytes, and no test
 * could tell).
 *
 * The precomputed values (wrapped CEK, handoff blob, X25519 key) were
 * generated ONCE with a throwaway script; the deterministic HKDF vectors (the
 * recovery and machine-secret ones were checked against an independent
 * RFC 5869 implementation in Python's hmac module) are reproducible from the
 * fixed inputs alone. Do NOT regenerate to
 * make a red test green — a red test here means a break in compatibility with
 * every existing store.
 */

import { describe, expect, it } from 'vitest';
import { hkdfDeriveKey } from '../hkdf.js';
import {
  cekHandoffDecrypt,
  cekUnwrap,
  deriveMachineSecretSlotSecret,
  deriveRecoverySlotSecret,
  deriveWrappingKey,
  exportAesKey,
  fromBase64,
  HKDF_INFO,
  PRF_EVAL_SALT_VALUE,
  parseRecoveryCode,
  prfEvalSalt,
  sdkDerive,
} from '../index.js';
import type { CekHandoffBlob } from '../types.js';

const bytesToHex = (data: Uint8Array): string =>
  Array.from(data, (b) => b.toString(16).padStart(2, '0')).join('');

/** Sequential test bytes: seq(0x20, 4) = 20 21 22 23. */
const seq = (start: number, length: number): Uint8Array =>
  new Uint8Array(Array.from({ length }, (_, i) => start + i));

// ─── Fixed inputs ────────────────────────────────────────────────────────────

const PASSKEY_SECRET = seq(0x00, 32);
const SERVER_SECRET = seq(0x20, 32);
const CEK_RAW_HEX = bytesToHex(seq(0x40, 32));
const SDK_MASTER = seq(0x60, 32);
const HANDOFF_CEK_RAW_HEX = bytesToHex(seq(0x80, 32));
const RECOVERY_SALT_B64 = 'sLGys7S1tre4ubq7vL2+vw=='; // b0b1...bf

// ─── Pinned string constants ─────────────────────────────────────────────────

describe('golden: pinned constants', () => {
  it('PRF eval salt is the exact v2 string', () => {
    expect(PRF_EVAL_SALT_VALUE).toBe('rediacc-prf-eval-v2');
    expect(bytesToHex(prfEvalSalt())).toBe(
      bytesToHex(new TextEncoder().encode('rediacc-prf-eval-v2'))
    );
  });

  it('HKDF info strings are exact', () => {
    expect(HKDF_INFO.SDK_DERIVE).toBe('rediacc-config-sdk-v1');
    expect(HKDF_INFO.WRAPPING_KEY).toBe('rediacc-config-wrapping-key-v1');
    expect(HKDF_INFO.FIELD_COMMITMENT).toBe('rediacc-config-fck-v1');
    expect(HKDF_INFO.RECOVERY_SLOT).toBe('rediacc-recovery-slot-v1');
    expect(HKDF_INFO.MACHINE_SECRET).toBe('rediacc-machine-secret-v1');
  });
});

// ─── Wrapping key + CEK unwrap ───────────────────────────────────────────────

describe('golden: deriveWrappingKey / cekUnwrap', () => {
  it('deriveWrappingKey produces the pinned key bytes', async () => {
    const wrappingKey = await deriveWrappingKey(PASSKEY_SECRET, SERVER_SECRET);
    expect(bytesToHex(await exportAesKey(wrappingKey))).toBe(
      'b7f047ff8e2bf18ebbaa632fa17d85f768fd8e097713325d74c3e39dce40e093'
    );
  });

  it("deriveWrappingKey is HKDF(passkey || server, 'rediacc-wrapping-salt-v1', WRAPPING_KEY)", async () => {
    // Pins the internal salt literal and the concatenation ORDER: passkey secret first, server secret second.
    const combined = new Uint8Array(64);
    combined.set(PASSKEY_SECRET, 0);
    combined.set(SERVER_SECRET, 32);
    const manual = await hkdfDeriveKey(
      combined,
      new TextEncoder().encode('rediacc-wrapping-salt-v1'),
      HKDF_INFO.WRAPPING_KEY
    );
    const viaApi = await deriveWrappingKey(PASSKEY_SECRET, SERVER_SECRET);
    expect(bytesToHex(await exportAesKey(manual))).toBe(bytesToHex(await exportAesKey(viaApi)));
  });

  it('cekUnwrap recovers the pinned CEK from a precomputed wrapped blob', async () => {
    const wrappedCek =
      'LyU9y5u2wAhjnCqE5tKP5tsy8qbzQdLuuwJAqi0k1UJFhK0NB48IFXXXmJuE2xICxyrCtt7wKgJ70sf6';
    const wrappingKey = await deriveWrappingKey(PASSKEY_SECRET, SERVER_SECRET);
    const cek = await cekUnwrap(wrappedCek, wrappingKey);
    expect(bytesToHex(await exportAesKey(cek))).toBe(CEK_RAW_HEX);
  });
});

// ─── Slot secret KDFs ────────────────────────────────────────────────────────

describe('golden: slot secret derivation', () => {
  it('machine secret parses from messy input and derives the pinned secret', async () => {
    // Same characters and salt as the recovery vector below: the prefix and the HKDF info keep the two apart.
    const messy = 'rm1 7gv2lvcb yq8c4ctm fvIz5kst nvqvcma9';
    const secret = await deriveMachineSecretSlotSecret(messy, {
      algorithm: 'HKDF-SHA256',
      salt: RECOVERY_SALT_B64,
    });
    expect(bytesToHex(secret)).toBe(
      '031c4328ee68a5a722c2ad05b9bd7ea626b3c3162772fa20dd7f3a2b1da2a843'
    );
  });

  it('recovery code parses from messy input and derives the pinned secret', async () => {
    const canonical = 'RC1-7GV21VCB-YQ8C4CTM-FV1Z5KST-NVQVCMA9';
    // Lowercase, no prefix, no dashes, Crockford aliases (l→1, I→1) — all must normalize back to the canonical form the secret was derived from.
    const messy = '7gv2lvcb yq8c4ctm fvIz5kst nvqvcma9';
    expect(parseRecoveryCode(messy)).toBe(canonical);

    const secret = await deriveRecoverySlotSecret(messy, {
      method: 'recovery',
      algorithm: 'HKDF-SHA256',
      salt: RECOVERY_SALT_B64,
    });
    expect(bytesToHex(secret)).toBe(
      'e86f8e9c30955cb6f6a7783def0714cfa2e71e004eee3ffdfeef1a26c503d2ab'
    );
  });
});

// ─── SDK derivation ──────────────────────────────────────────────────────────

describe('golden: sdkDerive', () => {
  it('fixed master + epoch 5913166 produces the pinned key', async () => {
    const key = await sdkDerive(SDK_MASTER, 5913166);
    expect(bytesToHex(await exportAesKey(key))).toBe(
      'f69096e5872b24ee8dbd1c078880b93ec38f94d51c1cbecdafe8a13ce7743133'
    );
  });

  it('epoch enters the KDF as its ASCII decimal string (salt position)', async () => {
    const manual = await hkdfDeriveKey(
      SDK_MASTER,
      new TextEncoder().encode('5913166'),
      HKDF_INFO.SDK_DERIVE
    );
    const viaApi = await sdkDerive(SDK_MASTER, 5913166);
    expect(bytesToHex(await exportAesKey(manual))).toBe(bytesToHex(await exportAesKey(viaApi)));
  });
});

// ─── X25519 handoff ──────────────────────────────────────────────────────────

describe('golden: cekHandoffDecrypt', () => {
  it('decrypts a precomputed handoff blob with a fixed recipient key', async () => {
    // The blob was sealed under HKDF info 'rediacc-cek-handoff-v1'; a drift in
    // that literal (or the ECDH/HKDF/AES-GCM composition) fails this decrypt.
    const recipientPkcs8 = fromBase64(
      'MC4CAQAwBQYDK2VuBCIEIPDGUBsGFTDw8wyvGgyO+Z9gex/KFY6aoxTzmye87gFD'
    );
    const blob: CekHandoffBlob = {
      v: 1,
      eph: 'MCowBQYDK2VuAyEAF8k0nn2v0L0OVneI/qs3fD7cEemDlFjC4UPiidmOnWw=',
      salt: '2ZdO9EUkJBjYNiAQmP7+eA==',
      iv: 'oiCftx8Jraao7Eg1',
      ct: '/C0Oq0qMdp3JuOA6rv6FJLDhBwJHEAtfeUavdovKxxI/sZF3wE19JaGUPHUQfjE2',
    };

    const privateKey = await crypto.subtle.importKey(
      'pkcs8',
      recipientPkcs8.buffer as ArrayBuffer,
      { name: 'X25519' },
      false,
      ['deriveBits']
    );
    const cekRaw = await cekHandoffDecrypt(blob, privateKey);
    expect(bytesToHex(cekRaw)).toBe(HANDOFF_CEK_RAW_HEX);
  });
});
