import type { TranslationCatalog } from '../translator';
import type { Language } from '../types';

/** One lazily imported catalog: the shape `import('./client/<locale>.json')` resolves to. */
export type CatalogLoader = () => Promise<{ default: TranslationCatalog }>;

/**
 * The client catalogs as a store: English held from the start, every other locale fetched
 * on demand and kept once it arrives.
 *
 * WHY A STORE AND NOT A RECORD. The thirteen slices used to sit in one eager chunk, about
 * 142 KB that every page paid for to read one of them. Here each non-English slice is a
 * separate chunk behind its own loader, so a page fetches its own locale and nothing else,
 * and a component that asks for a locale not yet fetched re-renders when it lands instead of
 * forcing the whole set up front.
 *
 * `listeners` is the `useSyncExternalStore` contract: `subscribe` registers, `get` is the
 * snapshot, and a catalog's arrival is the one event that changes it.
 */
export function createCatalogStore(
  english: TranslationCatalog,
  loaders: Readonly<Record<Exclude<Language, 'en'>, CatalogLoader>>
) {
  const loaded: Partial<Record<Language, TranslationCatalog>> = { en: english };
  const pending = new Map<Language, Promise<void>>();
  const listeners = new Set<() => void>();

  const load = (lang: Language): Promise<void> => {
    if (loaded[lang]) return Promise.resolve();
    const inFlight = pending.get(lang);
    if (inFlight !== undefined) return inFlight;
    const request = loaders[lang as Exclude<Language, 'en'>]()
      .then((module) => {
        loaded[lang] = module.default;
        for (const listener of listeners) listener();
      })
      .catch((error: unknown) => {
        // Forget the failed request so the next ask retries; until then the caller keeps rendering the fallback catalog rather than raw keys.
        pending.delete(lang);
        console.error(`Failed to load the ${lang} client translations`, error);
      });
    pending.set(lang, request);
    return request;
  };

  return {
    load,
    /** Every locale the loaders know, for the server, which renders all of them. */
    loadAll: (): Promise<void[]> =>
      Promise.all(Object.keys(loaders).map((lang) => load(lang as Language))),
    get: (lang: Language): TranslationCatalog | undefined => loaded[lang],
    /** Every catalog held so far, for the SSR set assertion. */
    all: (): Partial<Record<Language, TranslationCatalog>> => ({ ...loaded }),
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
