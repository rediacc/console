import { describe, expect, it } from 'vitest';
import { orderedKeys, titleNumber } from '../legal-order';

describe('titleNumber', () => {
  it('reads a section and a subsection number', () => {
    expect(titleNumber('10. Changes')).toEqual([10]);
    expect(titleNumber('2.4 Cookies')).toEqual([2, 4]);
    expect(titleNumber('Introduction')).toBeNull();
    expect(titleNumber(undefined)).toBeNull();
  });
});

describe('orderedKeys', () => {
  it('orders by number, not by key order, and moves unnumbered keys to the end in their original order', () => {
    const entries = {
      z: { title: '10. Last' },
      a: { title: 'No number' },
      m: { title: '2. Second' },
      b: { title: '1. First' },
      c: { title: 'Also none' },
    };
    expect(orderedKeys(entries)).toEqual(['b', 'm', 'z', 'a', 'c']);
  });

  it('puts 2.10 after 2.9', () => {
    expect(orderedKeys({ x: { title: '2.10 Ten' }, y: { title: '2.9 Nine' } })).toEqual(['y', 'x']);
  });

  // Every locale of every legal page, ordered by the English numbering: its own titles then read 1..n, and each section's subsections n.1..n.m, so a stale number in a translation fails here.
  const LOCALES = import.meta.glob('../../i18n/translations/*.json', {
    eager: true,
    import: 'default',
  });
  const PAGES = [
    'privacyPolicy',
    'cookiePolicy',
    'termsOfService',
    'refundPolicy',
    'telemetryPolicy',
  ] as const;
  type Titled = Record<string, { title: string; subsections?: Record<string, { title: string }> }>;

  it('covers all 13 locales', () => {
    expect(Object.keys(LOCALES)).toHaveLength(13);
  });

  const EN = LOCALES['../../i18n/translations/en.json'] as {
    pages: Record<string, { sections: Titled }>;
  };

  for (const [path, file] of Object.entries(LOCALES)) {
    for (const page of PAGES) {
      it(`orders ${page} in ${path.split('/').pop()}`, () => {
        const sections = (file as { pages: Record<string, { sections: Titled }> }).pages[page]
          .sections;
        const enSections = EN.pages[page].sections;
        const keys = orderedKeys(sections, enSections);
        expect(keys.map((k) => titleNumber(sections[k].title)?.[0])).toEqual(
          keys.map((_, i) => i + 1)
        );
        for (const k of keys) {
          const subs = sections[k].subsections;
          if (!subs) continue;
          const sectionNumber = titleNumber(sections[k].title)?.[0];
          expect(
            orderedKeys(subs, enSections[k]?.subsections).map((s) =>
              titleNumber(subs[s].title)?.join('.')
            )
          ).toEqual(Object.keys(subs).map((_, i) => `${sectionNumber}.${i + 1}`));
        }
      });
    }
  }
});
