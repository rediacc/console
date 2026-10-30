import { describe, expect, it } from 'vitest';
import de from '../../i18n/translations/de.json';
import en from '../../i18n/translations/en.json';
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
  it('orders by number, not by key order, and keeps unnumbered keys last in place', () => {
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

  it('renders every locale of the privacy policy in the English reading order', () => {
    // The de file stores its sections as 10, 9, 5, 7, ...: key order would render them so.
    for (const file of [en, de]) {
      const sections = file.pages.privacyPolicy.sections as Record<string, { title: string }>;
      const numbers = orderedKeys(sections).map((k) => titleNumber(sections[k].title)?.[0]);
      expect(numbers).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      const subs = file.pages.privacyPolicy.sections.informationWeCollect.subsections as Record<
        string,
        { title: string }
      >;
      expect(orderedKeys(subs).map((k) => titleNumber(subs[k].title)?.join('.'))).toEqual([
        '2.1',
        '2.2',
        '2.3',
        '2.4',
        '2.5',
        '2.6',
      ]);
    }
  });
});
