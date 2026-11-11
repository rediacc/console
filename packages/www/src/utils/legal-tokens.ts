/**
 * Entity tokens for the legal pages (agent/plans/PLAN-terms-acceptance.md Design 1).
 *
 * The legal text carries `{{legalName}}`, `{{registryCode}}` and the other entity facts as tokens,
 * so no entity value is typed into a translation. `to()` returns a raw subtree without
 * interpolating, so `interpolateTree` walks the whole section tree. The values mirror what
 * `scripts/gen/gen-legal.ts` substitutes when it renders the archived text, which is what keeps
 * the page and the hashed text saying the same thing.
 */
import { LEGAL_ENTITY } from '@rediacc/shared/legal/entity.generated';
import { LEGAL_URLS } from '@rediacc/shared/legal';
import type { Language } from '../i18n/types';

export type LegalTokens = Record<string, string>;

/** The locale's name for a region code ("EE" -> "Estonia", "Estland", ...). */
export function countryName(code: string, lang: string): string {
  return new Intl.DisplayNames([lang], { type: 'region' }).of(code) ?? code;
}

/** Every token a legal text may carry, for one language. */
export function legalTokens(lang: Language): LegalTokens {
  return {
    legalName: LEGAL_ENTITY.legalName,
    registryCode: LEGAL_ENTITY.registryCode,
    registerName: LEGAL_ENTITY.registerName,
    vatNumber: LEGAL_ENTITY.vatNumber,
    registeredAddress: LEGAL_ENTITY.registeredAddress,
    country: countryName(LEGAL_ENTITY.countryCode, lang),
    termsUrl: LEGAL_URLS.documentUrl('terms-of-service', lang),
    privacyUrl: LEGAL_URLS.documentUrl('privacy-policy', lang),
  };
}

/** `value` with every `{{token}}` in every string replaced; arrays and objects are copied. */
export function interpolateTree<T>(value: T, tokens: LegalTokens): T {
  if (typeof value === 'string') {
    return value.replace(/\{\{(\w+)\}\}/g, (m, name: string) => tokens[name] ?? m) as T;
  }
  if (Array.isArray(value)) return value.map((v) => interpolateTree(v, tokens)) as T;
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, interpolateTree(v, tokens)])
    ) as T;
  }
  return value;
}
