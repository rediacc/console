import { LEGAL_ENTITY } from '@rediacc/shared/legal/entity.generated';
import { describe, expect, it } from 'vitest';
import { interpolateTree, legalTokens } from '../legal-tokens';

describe('interpolateTree', () => {
  const tokens = { legalName: 'Acme OU', country: 'Estonia' };

  it('replaces tokens in strings, arrays and nested objects without mutating the input', () => {
    const input = {
      title: 'Terms of {{legalName}}',
      content: ['Based in {{country}}.', 'No tokens'],
      sub: { items: [{ text: '{{legalName}} / {{legalName}}' }] },
      count: 3,
    };
    const snapshot = JSON.stringify(input);
    expect(interpolateTree(input, tokens)).toEqual({
      title: 'Terms of Acme OU',
      content: ['Based in Estonia.', 'No tokens'],
      sub: { items: [{ text: 'Acme OU / Acme OU' }] },
      count: 3,
    });
    expect(JSON.stringify(input)).toBe(snapshot);
  });

  it('leaves an unknown token in place', () => {
    expect(interpolateTree('{{nope}} and {{legalName}}', tokens)).toBe('{{nope}} and Acme OU');
  });
});

describe('legalTokens', () => {
  it('carries the entity values and a localized country name', () => {
    const en = legalTokens('en');
    expect(en.legalName).toBe(LEGAL_ENTITY.legalName);
    expect(en.country).toBe('Estonia');
    expect(legalTokens('de').country).toBe('Estland');
    expect(en.termsUrl).toContain('/en/terms-of-service');
  });
});
