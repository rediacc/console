/**
 * Search snippets cut a meta description past 160 characters, and a title equal to the page's H1
 * wastes the one place a search result can say something else. Both were fixed by hand for the
 * legal pages (6a049fc810); this keeps them fixed in every locale.
 */
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { LEGAL_PAGES } from '../../lib/legal-pages';

const dir = fileURLToPath(new URL('../translations/', import.meta.url));
const MAX_DESCRIPTION = 160;

type Catalog = {
  pages: Record<string, { meta: { title: string; description: string }; hero: { title: string } }>;
};

const locales = fs
  .readdirSync(dir)
  .filter((f) => f.endsWith('.json') && !f.startsWith('.'))
  .map((f) => f.replace('.json', ''));

describe('legal page meta', () => {
  it('finds the locale catalogs', () => {
    expect(locales).toContain('en');
    expect(locales.length).toBeGreaterThan(1);
  });

  for (const locale of locales) {
    const catalog = JSON.parse(fs.readFileSync(`${dir}${locale}.json`, 'utf8')) as Catalog;
    for (const page of LEGAL_PAGES) {
      it(`${locale} ${page}: description fits a snippet and the title differs from the H1`, () => {
        const { meta, hero } = catalog.pages[page];
        expect(meta.description.length).toBeLessThanOrEqual(MAX_DESCRIPTION);
        expect(meta.title).not.toBe(hero.title);
      });
    }
  }
});
