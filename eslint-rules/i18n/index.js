/**
 * ESLint i18n Plugin
 *
 * Custom rules for strict i18n validation in locale JSON files and TypeScript source.
 */

import { noEmptyTranslations } from './no-empty-translations.js';
import { sortedKeys } from './sorted-keys.js';
import { keyNamingConvention } from './key-naming-convention.js';
import { interpolationMatch } from './interpolation-match.js';
import { noUnusedKeys } from './no-unused-keys.js';
import { crossLanguageConsistency } from './cross-language-consistency.js';
import { translationCoverage } from './translation-coverage.js';
import { noUntranslatedValues } from './no-untranslated-values.js';
import { interpolationConsistency } from './interpolation-consistency.js';
import { translationStaleness } from './translation-staleness.js';

/**
 * Plugin for JSON locale file validation
 */
export const i18nJsonPlugin = {
  rules: {
    'no-empty-translations': noEmptyTranslations,
    'sorted-keys': sortedKeys,
    'key-naming-convention': keyNamingConvention,
    'no-unused-keys': noUnusedKeys,
    'cross-language-consistency': crossLanguageConsistency,
    'translation-coverage': translationCoverage,
    'no-untranslated-values': noUntranslatedValues,
    'interpolation-consistency': interpolationConsistency,
    'translation-staleness': translationStaleness,
  },
};

/**
 * Plugin for TypeScript source file i18n validation
 */
export const i18nSourcePlugin = {
  rules: {
    'interpolation-match': interpolationMatch,
  },
};

// Export individual rules for direct import
export { noEmptyTranslations } from './no-empty-translations.js';
export { sortedKeys } from './sorted-keys.js';
export { keyNamingConvention } from './key-naming-convention.js';
export { interpolationMatch } from './interpolation-match.js';
export { noUnusedKeys } from './no-unused-keys.js';
export { crossLanguageConsistency } from './cross-language-consistency.js';
export { translationCoverage } from './translation-coverage.js';
export { noUntranslatedValues } from './no-untranslated-values.js';
export { interpolationConsistency } from './interpolation-consistency.js';
export { translationStaleness } from './translation-staleness.js';

// Default export for ESLint plugin
export default i18nJsonPlugin;
