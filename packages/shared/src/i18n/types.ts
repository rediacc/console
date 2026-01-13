/**
 * Shared i18n types for CLI and Web.
 * These types define the structure of the common translations.
 */

import type { TranslationKey } from './translation-keys.generated';

/**
 * Type-safe translation function options.
 * Supports interpolation variables and pluralization.
 */
export interface TranslationOptions {
  /** Interpolation variables */
  [key: string]: unknown;
  /** Count for pluralization */
  count?: number;
  /** Context for contextual translations */
  context?: string;
  /** Default value if key is missing */
  defaultValue?: string;
}

/**
 * Type-safe translation function.
 * Use this instead of TFunction from i18next for compile-time validation.
 *
 * @example
 * ```typescript
 * interface Props {
 *   t: TypedTFunction;
 * }
 *
 * // TypeScript will error if key doesn't exist:
 * t('auth:login.email')        // Valid
 * t('auth:login.typo')         // Error: not a valid key
 * t('common:status.pending')   // Valid with namespace
 * t('status.pending')          // Valid without namespace (common keys)
 * ```
 */
export type TypedTFunction = {
  (key: TranslationKey, options?: TranslationOptions): string;
  /**
   * Use this overload for dynamically constructed keys.
   * Add `as TranslationKey` to assert the key is valid.
   * @example t(`${namespace}:${key}` as TranslationKey)
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (key: any, options?: TranslationOptions): string;
};

/**
 * Re-export TranslationKey for convenience
 */
export type { TranslationKey };

/**
 * Supported languages in the application.
 */
export const SUPPORTED_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/**
 * Default language for the application.
 */
export const DEFAULT_LANGUAGE: SupportedLanguage = 'en';

/**
 * Structure of the shared common translations.
 */
export interface SharedCommonTranslations {
  errors: {
    anErrorOccurred: string;
    cliCommandFailed: string;
    criticalSystemError: string;
    failedToCreateTask: string;
    failedToFork: string;
    helloFunctionError: string;
    machinesValidationError: string;
    noErrorMessage: string;
    operationFailed: string;
    passwordValidation: string;
    tfaVerificationFailed: string;
    unknownError: string;
    vaultTestFailed: string;
    vsCodeConnectionFailed: string;
  };
  success: {
    helloFunctionSuccess: string;
  };
  status: {
    cancelled: string;
    completed: string;
    failed: string;
    pending: string;
    processing: string;
    running: string;
    success: string;
    unknown: string;
    inProgress: string;
    initializing: string;
  };
  actions: {
    save: string;
    cancel: string;
    delete: string;
    create: string;
    edit: string;
    copy: string;
    retry: string;
    refresh: string;
    close: string;
    download: string;
    upload: string;
    remove: string;
    confirm: string;
    reset: string;
    back: string;
    search: string;
    export: string;
  };
  common: {
    yes: string;
    no: string;
    loading: string;
    error: string;
    warning: string;
    success: string;
    unknown: string;
    total: string;
    none: string;
  };
  validation: {
    required: string;
    invalidEmail: string;
    invalidFormat: string;
  };
  time: {
    today: string;
    yesterday: string;
    last7Days: string;
    last30Days: string;
    thisMonth: string;
    lastMonth: string;
  };
  confirm: {
    areYouSure: string;
    confirmDelete: string;
  };
  notifications: {
    error: string;
    warning: string;
    success: string;
    info: string;
  };
}

/**
 * Checks if a language code is supported.
 */
export function isSupportedLanguage(lang: string): lang is SupportedLanguage {
  return SUPPORTED_LANGUAGES.includes(lang as SupportedLanguage);
}

/**
 * Gets the supported language from a locale string.
 * Falls back to default language if not supported.
 */
export function getSupportedLanguage(locale: string | undefined): SupportedLanguage {
  if (!locale) return DEFAULT_LANGUAGE;

  // Try exact match first
  if (isSupportedLanguage(locale)) {
    return locale;
  }

  // Try language part only (e.g., 'en-US' -> 'en')
  const langPart = locale.split('-')[0]?.toLowerCase();
  if (langPart && isSupportedLanguage(langPart)) {
    return langPart;
  }

  return DEFAULT_LANGUAGE;
}
