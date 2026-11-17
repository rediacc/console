import { describe, expect, it, vi } from 'vitest';
import { createTranslatorFrom, type TranslationCatalog } from '../translator';
import type { Language } from '../types';

// A two-locale stand-in: the translator only ever reads catalogs[lang].
const en: TranslationCatalog = {
  pages: { pricing: { plans: { pro: { name: 'Pro' } } } },
  list: ['a', 'b'],
};
const catalogs = { en } as unknown as Record<Language, TranslationCatalog>;

describe('translator misses', () => {
  it('strict: a dynamic key whose varying part has no entry fails, naming the key', () => {
    const { t } = createTranslatorFrom(catalogs, 'en', { strict: true });
    const id = 'free';
    expect(() => t(`pages.pricing.plans.${id}.name`)).toThrow(
      /Translation key not found: pages\.pricing\.plans\.free\.name \(lang 'en'\)/
    );
  });

  it('strict: a fallback string does not hide the miss', () => {
    const { t } = createTranslatorFrom(catalogs, 'en', { strict: true });
    expect(() => t('pages.gone', 'English fallback')).toThrow(/pages\.gone/);
  });

  it('strict: a branch asked for as a string fails', () => {
    const { t } = createTranslatorFrom(catalogs, 'en', { strict: true });
    expect(() => t('pages.pricing')).toThrow(/does not point to a string/);
  });

  it('strict: ta() on a missing array fails', () => {
    const { ta } = createTranslatorFrom(catalogs, 'en', { strict: true });
    expect(() => ta('nope')).toThrow(/does not point to an array/);
  });

  it('CONTROL strict: a correct tree is silent', () => {
    const { t, ta } = createTranslatorFrom(catalogs, 'en', { strict: true });
    expect(t('pages.pricing.plans.pro.name')).toBe('Pro');
    expect(ta('list')).toEqual(['a', 'b']);
  });

  it('not strict (dev, browser): a miss warns and returns the key', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { t } = createTranslatorFrom(catalogs, 'en', { strict: false });
    expect(t('pages.pricing.plans.free.name')).toBe('pages.pricing.plans.free.name');
    expect(t('pages.gone', 'English fallback')).toBe('English fallback');
    expect(warn).toHaveBeenCalledTimes(2);
    warn.mockRestore();
  });

  it('the default under vitest is not strict, since it is not a production prerender', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { t } = createTranslatorFrom(catalogs, 'en');
    expect(t('pages.gone')).toBe('pages.gone');
    warn.mockRestore();
  });
});
