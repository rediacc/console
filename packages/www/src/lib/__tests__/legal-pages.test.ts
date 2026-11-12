import { describe, expect, it } from 'vitest';
import { type LegalPageKey, legalPageName } from '../legal-pages';

describe('legalPageName', () => {
  it('strips the pages. prefix from a listed legal page', () => {
    expect(legalPageName('pages.termsOfService')).toBe('termsOfService');
    expect(legalPageName('pages.telemetryPolicy')).toBe('telemetryPolicy');
  });

  it('throws for a key outside LEGAL_PAGES', () => {
    expect(() => legalPageName('pages.pricing' as LegalPageKey)).toThrow(/not a legal page/);
  });

  it('throws for a key that carries a listed name only as a suffix', () => {
    expect(() => legalPageName('other.termsOfService' as LegalPageKey)).toThrow(/not a legal page/);
  });
});
