import { createElement } from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import german from '../client/de.json';
import english from '../client/en.json';
import { useTranslation } from '../react';
import type { Language } from '../types';

function Probe({ lang }: { lang: Language }) {
  const { t } = useTranslation(lang);
  return createElement('span', null, t('captchaRetry'));
}

const render = (lang: Language) => renderToString(createElement(Probe, { lang }));

describe('useTranslation on the server', () => {
  it('renders the requested locale from the catalog loaded before any island evaluates', () => {
    expect(german.captchaRetry).not.toBe(english.captchaRetry);
    expect(render('de')).toContain(german.captchaRetry);
  });

  it('renders English for English', () => {
    expect(render('en')).toContain(english.captchaRetry);
  });
});
