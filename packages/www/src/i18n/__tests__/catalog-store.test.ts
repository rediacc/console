import { NON_ENGLISH_LOCALES } from '@rediacc/locales';
import { describe, expect, it, vi } from 'vitest';
import { type CatalogLoader, createCatalogStore } from '../react/catalog-store';
import type { Language } from '../types';

const OTHER_LOCALES = NON_ENGLISH_LOCALES;

function loaders(overrides: Partial<Record<(typeof OTHER_LOCALES)[number], CatalogLoader>> = {}) {
  const calls: string[] = [];
  const map = Object.fromEntries(
    OTHER_LOCALES.map((lang) => [
      lang,
      overrides[lang] ??
        (() => {
          calls.push(lang);
          return Promise.resolve({ default: { greeting: `hello-${lang}` } });
        }),
    ])
  ) as Record<(typeof OTHER_LOCALES)[number], CatalogLoader>;
  return { map, calls };
}

describe('createCatalogStore', () => {
  it('holds English from the start and nothing else', () => {
    const { map, calls } = loaders();
    const store = createCatalogStore({ greeting: 'hello' }, map);
    expect(store.get('en')).toEqual({ greeting: 'hello' });
    expect(store.get('de')).toBeUndefined();
    expect(calls).toEqual([]);
  });

  it('fetches only the locale asked for, once, and notifies subscribers', async () => {
    const { map, calls } = loaders();
    const store = createCatalogStore({}, map);
    const listener = vi.fn();
    store.subscribe(listener);

    await Promise.all([store.load('de'), store.load('de')]);
    await store.load('de');

    expect(calls).toEqual(['de']);
    expect(store.get('de')).toEqual({ greeting: 'hello-de' });
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('never calls a loader for English', async () => {
    const { map, calls } = loaders();
    const store = createCatalogStore({ greeting: 'hello' }, map);
    await store.load('en');
    expect(calls).toEqual([]);
  });

  it('loadAll fetches every non-English locale', async () => {
    const { map, calls } = loaders();
    const store = createCatalogStore({}, map);
    await store.loadAll();
    const byCode = (a: string, b: string) => a.localeCompare(b);
    expect(calls.toSorted(byCode)).toEqual(OTHER_LOCALES.toSorted(byCode));
    expect(Object.keys(store.all()).toSorted(byCode)).toEqual(
      ['en', ...OTHER_LOCALES].toSorted(byCode)
    );
  });

  it('forgets a failed fetch so the next ask retries', async () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
    let attempts = 0;
    const { map } = loaders({
      ja: () => {
        attempts += 1;
        return attempts === 1
          ? Promise.reject(new Error('offline'))
          : Promise.resolve({ default: { greeting: 'konnichiwa' } });
      },
    });
    const store = createCatalogStore({}, map);

    await store.load('ja');
    expect(store.get('ja')).toBeUndefined();
    expect(errors).toHaveBeenCalledTimes(1);

    await store.load('ja' as Language);
    expect(store.get('ja')).toEqual({ greeting: 'konnichiwa' });
    errors.mockRestore();
  });

  it('stops notifying a listener once it unsubscribes', async () => {
    const { map } = loaders();
    const store = createCatalogStore({}, map);
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    unsubscribe();
    await store.load('fr');
    expect(listener).not.toHaveBeenCalled();
  });
});
