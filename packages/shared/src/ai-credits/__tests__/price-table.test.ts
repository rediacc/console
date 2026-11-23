import { describe, expect, it } from 'vitest';
import {
  type AiPriceRow,
  findPriceRow,
  marginViolations,
  PRICE_TABLE,
  PRICE_TABLE_VERSION,
} from '../price-table.js';

describe('price table', () => {
  it('has a version and unique models', () => {
    expect(PRICE_TABLE_VERSION).toBeGreaterThanOrEqual(1);
    expect(new Set(PRICE_TABLE.map((r) => r.model)).size).toBe(PRICE_TABLE.length);
  });

  it('prices every row at or above the fee and tier margin in both directions', () => {
    expect(marginViolations()).toEqual([]);
  });

  it('refuses a control row priced below the fee', () => {
    const base = PRICE_TABLE[0];
    // Exactly the provider cost in credits: below the 1.05 fee, so both directions fail.
    const control: AiPriceRow = {
      ...base,
      model: 'control/at-cost',
      creditsPerMTokIn: base.providerUsdPerMTokIn * 1000,
      creditsPerMTokOut: base.providerUsdPerMTokOut * 1000,
    };
    const found = marginViolations([control]);
    expect(found.map((v) => v.direction).sort()).toEqual(['in', 'out']);
  });

  it('holds a premium row to the larger margin', () => {
    const premium = PRICE_TABLE.find((r) => r.tier === 'premium');
    if (!premium) throw new Error('table has no premium row');
    // Passes the standard 1.15 floor but not the premium 1.30 one.
    const control: AiPriceRow = {
      ...premium,
      model: 'control/premium-at-standard',
      creditsPerMTokIn: Math.ceil(premium.providerUsdPerMTokIn * 1.05 * 1.2 * 1000),
      creditsPerMTokOut: Math.ceil(premium.providerUsdPerMTokOut * 1.05 * 1.2 * 1000),
    };
    expect(marginViolations([control]).length).toBe(2);
    expect(marginViolations([{ ...control, tier: 'standard' }])).toEqual([]);
  });

  it('finds a sold model and returns nothing for an unknown one', () => {
    expect(findPriceRow(PRICE_TABLE[0].model)).toBe(PRICE_TABLE[0]);
    expect(findPriceRow('openai/not-sold')).toBeUndefined();
  });
});
