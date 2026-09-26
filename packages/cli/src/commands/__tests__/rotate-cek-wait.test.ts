/**
 * `rdc config rotate-cek` learns that the rotation finished from the server's CEK generation, not from a
 * question. It used to ask "Did the browser report the rotation as complete?", and both wrong answers lied
 * (operator, 2026-09-26).
 */

import { describe, expect, it } from 'vitest';
import { waitForGeneration } from '../config-remote.js';

const noSleep = async () => {};

describe('waitForGeneration', () => {
  it('returns true once the store generation passes the one read before the wizard', async () => {
    const seen = [1, 1, 2];
    let polls = 0;
    const done = await waitForGeneration(() => Promise.resolve(seen[polls++]), 1, {
      intervalMs: 1,
      timeoutMs: 100,
      sleep: noSleep,
    });
    expect(done).toBe(true);
    expect(polls).toBe(3);
  });

  it('returns false when the wait runs out with nothing rotated', async () => {
    const done = await waitForGeneration(() => Promise.resolve(1), 1, {
      intervalMs: 10,
      timeoutMs: 50,
      sleep: noSleep,
    });
    expect(done).toBe(false);
  });

  it('an unknown generation counts as 0, so a store that starts reporting 1 is not read as rotated from 1', async () => {
    const done = await waitForGeneration(() => Promise.resolve(undefined), 0, {
      intervalMs: 10,
      timeoutMs: 30,
      sleep: noSleep,
    });
    expect(done).toBe(false);
  });
});
