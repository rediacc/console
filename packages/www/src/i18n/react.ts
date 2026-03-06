import { useMemo } from 'react';
import type { Language } from './types';
import { createTranslator } from './utils';

/**
 * React hook for using translations in React components
 * Uses useMemo to ensure stable references and prevent hydration mismatches
 */
export function useTranslation(lang: Language = 'en') {
  return useMemo(() => createTranslator(lang), [lang]);
}
