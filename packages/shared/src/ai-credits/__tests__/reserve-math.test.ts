import { describe, expect, it } from 'vitest';
import { PRICE_TABLE } from '../price-table.js';
import {
  actualCredits,
  clampMaxTokens,
  estimateInputTokens,
  MAX_TOKENS_CLAMP,
  worstCaseCredits,
} from '../reserve-math.js';

const row = { ...PRICE_TABLE[0], creditsPerMTokIn: 1000, creditsPerMTokOut: 4000 };

describe('reserve math', () => {
  it('estimates one input token per 3 bytes, rounding up', () => {
    expect(estimateInputTokens(0)).toBe(0);
    expect(estimateInputTokens(3)).toBe(1);
    expect(estimateInputTokens(4)).toBe(2);
  });

  it('clamps max_tokens and defaults to the clamp', () => {
    expect(clampMaxTokens(undefined)).toBe(MAX_TOKENS_CLAMP);
    expect(clampMaxTokens(100_000)).toBe(MAX_TOKENS_CLAMP);
    expect(clampMaxTokens(512.9)).toBe(512);
  });

  it('refuses a max_tokens below 1 or not finite', () => {
    expect(() => clampMaxTokens(0)).toThrow(RangeError);
    expect(() => clampMaxTokens(Number.NaN)).toThrow(RangeError);
  });

  it('computes the worst case from the body and the clamped output', () => {
    // 3_000_000 bytes -> 1_000_000 input tokens, output clamped to MAX_TOKENS_CLAMP.
    expect(worstCaseCredits(row, 3_000_000, 500_000)).toBe(
      Math.ceil((1_000_000 * 1000 + MAX_TOKENS_CLAMP * 4000) / 1_000_000)
    );
  });

  it('charges actual usage rounded up to a whole credit', () => {
    expect(actualCredits(row, { promptTokens: 1, completionTokens: 0 })).toBe(1);
    expect(actualCredits(row, { promptTokens: 0, completionTokens: 0 })).toBe(0);
    expect(actualCredits(row, { promptTokens: 1000, completionTokens: 1000 })).toBe(5);
  });

  it('keeps the worst case at or above the actual charge for usage inside the estimate', () => {
    const bodyBytes = 30_000;
    const worst = worstCaseCredits(row, bodyBytes, 2000);
    const actual = actualCredits(row, {
      promptTokens: estimateInputTokens(bodyBytes),
      completionTokens: 2000,
    });
    expect(worst).toBeGreaterThanOrEqual(actual);
  });

  it('rejects negative usage', () => {
    expect(() => actualCredits(row, { promptTokens: -1, completionTokens: 0 })).toThrow(RangeError);
  });
});
