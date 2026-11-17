/**
 * The tier names are product names. They were machine-translated into common nouns (ja Business
 * as a "job", tr Enterprise as a "startup", fr Business and Enterprise collapsed into one word)
 * while every gate stayed green, because a translated value is a legitimate value to the
 * completeness, cross-locale and contamination gates. This pins the three names in every locale
 * of the one locale set, so a revert to a translated name fails here.
 */
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SITE_LOCALES } from '@rediacc/locales';
import { describe, expect, it } from 'vitest';

const dir = fileURLToPath(new URL('../translations/', import.meta.url));

const TIERS = {
  professional: 'Professional',
  business: 'Business',
  enterprise: 'Enterprise',
} as const;

type Catalog = { pages: { pricing: { plans: Record<string, { name: string }> } } };

describe('pricing tier names', () => {
  it('covers every site locale, including the default', () => {
    expect(SITE_LOCALES.length).toBe(13);
    expect(SITE_LOCALES).toContain('en');
  });

  for (const locale of SITE_LOCALES) {
    it(`${locale}: Professional, Business and Enterprise stay the English product names`, () => {
      const catalog = JSON.parse(fs.readFileSync(`${dir}${locale}.json`, 'utf8')) as Catalog;
      const got = Object.fromEntries(
        Object.keys(TIERS).map((id) => [id, catalog.pages.pricing.plans[id]?.name])
      );
      expect(got).toEqual(TIERS);
    });
  }
});
