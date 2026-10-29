import { describe, expect, it } from 'vitest';
import {
  applyJitter,
  INITIAL_DELAY_MS,
  MAX_DELAY_MS,
  nextPollStep,
  nextTransportStep,
  startTransportErrors,
  TRANSPORT_BUDGET_MS,
} from '../backoff.js';

const mid = () => 0.5; // zero jitter
const low = () => 0; // -20 %
const high = () => 1 - Number.EPSILON; // +20 %

describe('applyJitter', () => {
  it('is the identity at the midpoint', () => {
    expect(applyJitter(10_000, mid)).toBe(10_000);
  });
  it('reaches -20 % at the low bound', () => {
    expect(applyJitter(10_000, low)).toBe(8_000);
  });
  it('reaches +20 % at the high bound', () => {
    expect(applyJitter(10_000, high)).toBe(12_000);
  });
  it('never leaves the band for a sweep of random values', () => {
    for (let i = 0; i < 1000; i++) {
      const v = applyJitter(5_000, () => i / 1000);
      expect(v).toBeGreaterThanOrEqual(4_000);
      expect(v).toBeLessThanOrEqual(6_000);
    }
  });
});

describe('nextPollStep', () => {
  it('multiplies by 1.5 on a poll with no new lines', () => {
    const s = nextPollStep(INITIAL_DELAY_MS, { newLines: false, more: false }, mid);
    expect(s.nextBaseMs).toBe(3_000);
    expect(s.delayMs).toBe(3_000);
  });
  it('caps at 30 s', () => {
    let base = INITIAL_DELAY_MS;
    for (let i = 0; i < 20; i++) {
      base = nextPollStep(base, { newLines: false, more: false }, mid).nextBaseMs;
    }
    expect(base).toBe(MAX_DELAY_MS);
    expect(nextPollStep(MAX_DELAY_MS, { newLines: false, more: false }, mid).delayMs).toBe(30_000);
  });
  it('resets to 2 s when new lines arrive', () => {
    const s = nextPollStep(20_000, { newLines: true, more: false }, mid);
    expect(s.nextBaseMs).toBe(INITIAL_DELAY_MS);
    expect(s.delayMs).toBe(2_000);
  });
  it('polls at once when more is true, and resets the base', () => {
    const s = nextPollStep(20_000, { newLines: false, more: true }, high);
    expect(s.delayMs).toBe(0);
    expect(s.nextBaseMs).toBe(INITIAL_DELAY_MS);
  });
  it('applies jitter bounds to the delay but not to the carried base', () => {
    const lo = nextPollStep(INITIAL_DELAY_MS, { newLines: false, more: false }, low);
    const hi = nextPollStep(INITIAL_DELAY_MS, { newLines: false, more: false }, high);
    expect(lo.delayMs).toBe(2_400);
    expect(hi.delayMs).toBe(3_600);
    expect(lo.nextBaseMs).toBe(3_000);
    expect(hi.nextBaseMs).toBe(3_000);
  });
});

describe('transport-error ladder', () => {
  it('starts at 2 s and grows by 1.5 up to the 30 s cap', () => {
    let state = startTransportErrors(0);
    const delays: number[] = [];
    for (let i = 0; i < 12; i++) {
      const step = nextTransportStep(state, i, mid);
      if (step.giveUp) throw new Error('unexpected give-up');
      delays.push(step.delayMs);
      state = step.state;
    }
    expect(delays.slice(0, 3)).toEqual([2_000, 3_000, 4_500]);
    expect(Math.max(...delays)).toBe(MAX_DELAY_MS);
  });
  it('applies jitter within bounds', () => {
    const state = startTransportErrors(0);
    const lo = nextTransportStep(state, 0, low);
    const hi = nextTransportStep(state, 0, high);
    if (lo.giveUp || hi.giveUp) throw new Error('unexpected give-up');
    expect(lo.delayMs).toBe(1_600);
    expect(hi.delayMs).toBe(2_400);
  });
  it('gives up once the 10 minute budget is spent', () => {
    const state = startTransportErrors(1_000);
    expect(nextTransportStep(state, 1_000 + TRANSPORT_BUDGET_MS - 1, mid).giveUp).toBe(false);
    expect(nextTransportStep(state, 1_000 + TRANSPORT_BUDGET_MS, mid).giveUp).toBe(true);
  });
  it('never schedules a wait past the budget', () => {
    const state = { baseMs: MAX_DELAY_MS, firstFailureAtMs: 0 };
    const step = nextTransportStep(state, TRANSPORT_BUDGET_MS - 5_000, high);
    if (step.giveUp) throw new Error('unexpected give-up');
    expect(step.delayMs).toBe(5_000);
  });
  it('restarts a fresh ladder after a success', () => {
    const step = nextTransportStep(startTransportErrors(900_000), 900_000, mid);
    if (step.giveUp) throw new Error('unexpected give-up');
    expect(step.delayMs).toBe(2_000);
  });
});
