/**
 * toBase64 takes inputs far larger than the engine's argument limit. Spreading a whole config blob into one
 * `String.fromCharCode` call overflowed the stack on `rdc machine add` against a real config (2026-09-26).
 */

import { describe, expect, it } from 'vitest';
import { fromBase64 as e2eFromBase64, toBase64 as e2eToBase64 } from '../../e2e/crypto.js';
import { fromBase64, toBase64 } from '../aes.js';

// 1 MiB is far past the argument limit the old single spread hit (a few hundred thousand on V8).
const big = new Uint8Array(1024 * 1024).map((_, i) => (i * 131 + 7) & 0xff);
const same = (a: Uint8Array, b: Uint8Array) => Buffer.from(a).equals(Buffer.from(b));

// Each 1 MiB round trip takes about 110 ms alone (99-124 ms over 3 runs) but a loaded full ci:quick run took 10654 ms, past vitest's 10 s default; the payload stays at 1 MiB so the old single-spread overflow still bites (verified: spreading 1 MiB throws RangeError), and this 60 s timeout (about 500x the median) only absorbs host load.
const LOADED_HOST_TIMEOUT_MS = 60_000;

describe('toBase64 on a large input', () => {
  it(
    'config-crypto round-trips 1 MiB without overflowing the stack',
    () => {
      expect(same(fromBase64(toBase64(big)), big)).toBe(true);
    },
    LOADED_HOST_TIMEOUT_MS
  );

  it(
    'e2e round-trips 1 MiB without overflowing the stack',
    () => {
      expect(same(e2eFromBase64(e2eToBase64(big)), big)).toBe(true);
    },
    LOADED_HOST_TIMEOUT_MS
  );

  it('matches the single-call encoding on a small input', () => {
    const small = big.subarray(0, 1000);
    expect(toBase64(small)).toBe(btoa(String.fromCharCode(...small)));
  });
});
