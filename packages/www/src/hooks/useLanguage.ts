import { useSyncExternalStore } from 'react';
import { getLanguageFromPath } from '../i18n/language-utils';
import type { Language } from '../i18n/types';

/**
 * Creates a store for managing language state that properly handles View Transitions.
 * The store subscribes to 'astro:after-swap' (View Transitions) and 'popstate' (back/forward)
 * to ensure language updates when navigating between pages.
 */
function createLanguageStore() {
  let currentLanguage: Language =
    typeof window === 'undefined' ? 'en' : getLanguageFromPath(window.location.pathname);

  const listeners = new Set<() => void>();

  const updateLanguage = () => {
    const newLanguage = getLanguageFromPath(window.location.pathname);
    if (newLanguage !== currentLanguage) {
      currentLanguage = newLanguage;
      listeners.forEach((listener) => listener());
    }
  };

  return {
    subscribe: (listener: () => void) => {
      listeners.add(listener);

      // Subscribe to View Transitions completion
      document.addEventListener('astro:after-swap', updateLanguage);
      // Subscribe to browser back/forward navigation
      window.addEventListener('popstate', updateLanguage);

      return () => {
        listeners.delete(listener);
        // Only remove event listeners when all subscribers are gone
        if (listeners.size === 0) {
          document.removeEventListener('astro:after-swap', updateLanguage);
          window.removeEventListener('popstate', updateLanguage);
        }
      };
    },
    getSnapshot: () => currentLanguage,
    getServerSnapshot: () => 'en' as Language,
  };
}

// Singleton store instance
let languageStore: ReturnType<typeof createLanguageStore> | null = null;

function getLanguageStore() {
  if (typeof window === 'undefined') {
    // Return a minimal store for SSR
    return {
      subscribe: () => () => {},
      getSnapshot: () => 'en' as Language,
      getServerSnapshot: () => 'en' as Language,
    };
  }

  languageStore ??= createLanguageStore();
  return languageStore;
}

/**
 * React hook that provides the current language from the URL path.
 * Automatically updates when navigating between pages via View Transitions
 * or browser back/forward buttons.
 *
 * @returns The current language code (e.g., 'en', 'de', 'es')
 */
export function useLanguage(): Language {
  const store = getLanguageStore();
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getServerSnapshot);
}
