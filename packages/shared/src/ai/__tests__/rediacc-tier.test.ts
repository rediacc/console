import { describe, expect, it } from 'vitest';
import { findPriceRow } from '../../ai-credits/price-table.js';
import { validateProfile } from '../profile.js';
import {
  asCreditRefusalCode,
  buildRediaccProfile,
  CREDIT_REFUSAL_MESSAGES,
  isRediaccProfile,
  REDIACC_AI_BASE_URL,
  REDIACC_DEFAULT_MODELS,
  REDIACC_TIERS,
  rediaccChoice,
} from '../rediacc-tier.js';
import { resolveProfile } from '../resolve.js';

describe('rediacc tier', () => {
  it('each default model is a price-table row of its own tier', () => {
    for (const tier of REDIACC_TIERS) {
      expect(findPriceRow(REDIACC_DEFAULT_MODELS[tier])?.tier).toBe(tier);
    }
  });

  it('the profile is keyless and aimed at the metered intercept', () => {
    const profile = buildRediaccProfile('standard');
    expect(profile).toMatchObject({ baseURL: 'http://ai.internal/compat', byokOnly: true });
    expect(profile.key).toBeUndefined();
    expect(isRediaccProfile(profile)).toBe(true);
    expect(isRediaccProfile({ ...profile, baseURL: 'https://api.openai.com/v1' })).toBe(false);
  });

  it('the customer guard still refuses the intercept host, so the tier is never read from a config', () => {
    expect(validateProfile(buildRediaccProfile('premium')).ok).toBe(false);
    expect(REDIACC_AI_BASE_URL).toBe('http://ai.internal/compat');
  });

  it('names both choices and every refusal code', () => {
    expect(rediaccChoice('standard')).toBe('rediacc:standard');
    expect(asCreditRefusalCode('INSUFFICIENT_CREDITS')).toBe('INSUFFICIENT_CREDITS');
    expect(asCreditRefusalCode('nope')).toBeUndefined();
    expect(Object.keys(CREDIT_REFUSAL_MESSAGES)).toHaveLength(15);
  });
});

describe('resolveProfile with the rediacc choices', () => {
  it('resolves a named choice to the built-in profile', () => {
    expect(resolveProfile({}, 'rediacc:premium')).toMatchObject({
      ok: true,
      name: 'rediacc:premium',
      source: 'rediacc',
      profile: { model: REDIACC_DEFAULT_MODELS.premium },
    });
  });

  it('resolves a config default that names a choice', () => {
    expect(resolveProfile({ team: { providers: {}, default: 'rediacc:standard' } })).toMatchObject({
      ok: true,
      source: 'rediacc',
      profile: { preset: 'rediacc' },
    });
  });

  it('a config profile cannot shadow a choice', () => {
    const shadow = {
      ...buildRediaccProfile('standard'),
      baseURL: 'https://evil.example/v1',
      key: 'k',
    };
    const result = resolveProfile(
      { team: { providers: { 'rediacc:standard': shadow } } },
      'rediacc:standard'
    );
    expect(result).toMatchObject({
      ok: true,
      source: 'rediacc',
      profile: { baseURL: REDIACC_AI_BASE_URL },
    });
  });

  it('an unknown rediacc name is still unknown', () => {
    expect(resolveProfile({}, 'rediacc:gold')).toMatchObject({
      ok: false,
      reason: 'unknown-profile',
    });
  });
});
