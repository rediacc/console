/**
 * CLI i18n module
 *
 * Provides internationalization support for the CLI.
 * Language preference is stored in context config (platform config dir).
 *
 * Usage:
 *   import { t, initI18n, changeLanguage } from './i18n/index.js';
 *
 *   // Initialize on startup
 *   await initI18n('en');
 *
 *   // Use translations
 *   outputService.success(t('auth.loginSuccess', { context: 'default' }));
 *
 *   // Change language
 *   await changeLanguage('de');
 */

export {
  changeLanguage,
  initI18n,
  SUPPORTED_LANGUAGES,
  t,
} from './config.js';
