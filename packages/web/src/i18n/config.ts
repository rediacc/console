import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';
import { getSharedTranslations, SHARED_NAMESPACE } from '@rediacc/shared/i18n';
import { cookieDetector } from './cookieDetector';
// Only load default language initially (English)
import enAuth from './locales/en/auth.json';
import enCeph from './locales/en/ceph.json';
import enCommon from './locales/en/common.json';
import enFunctions from './locales/en/functions.json';
import enMachines from './locales/en/machines.json';
import enOrganization from './locales/en/organization.json';
import enQueue from './locales/en/queue.json';
import enResources from './locales/en/resources.json';
import enSettings from './locales/en/settings.json';
import enStorageProviders from './locales/en/storageProviders.json';
import enSystem from './locales/en/system.json';

// Import shared translations from @rediacc/shared

const defaultNS = 'common';

// Initial resources - only English loaded
const initialResources = {
  en: {
    common: enCommon,
    auth: enAuth,
    resources: enResources,
    machines: enMachines,
    system: enSystem,
    queue: enQueue,
    settings: enSettings,
    storageProviders: enStorageProviders,
    functions: enFunctions,
    ceph: enCeph,
    organization: enOrganization,
    [SHARED_NAMESPACE]: getSharedTranslations('en'),
  },
};

// Type for language resources - loose type for dynamic loading since translations
// may have different structures between languages during development
type LanguageResources = Record<string, Record<string, unknown>>;

// Lazy load function for other languages
const loadLanguageResources = async (lng: string) => {
  if (lng === 'en' || i18n.hasResourceBundle(lng, 'common')) {
    return; // Already loaded
  }

  try {
    // Dynamic imports for other languages
    const resources: LanguageResources = {};

    // Load shared translations synchronously (already bundled)
    const sharedLng = lng as 'de' | 'es' | 'fr' | 'ja' | 'ar' | 'ru' | 'tr' | 'zh';
    resources[SHARED_NAMESPACE] = getSharedTranslations(sharedLng) as unknown as Record<
      string,
      unknown
    >;

    switch (lng) {
      case 'es':
        resources.auth = (await import('./locales/es/auth.json')).default;
        resources.common = (await import('./locales/es/common.json')).default;
        resources.resources = (await import('./locales/es/resources.json')).default;
        resources.machines = (await import('./locales/es/machines.json')).default;
        resources.system = (await import('./locales/es/system.json')).default;
        resources.queue = (await import('./locales/es/queue.json')).default;
        resources.settings = (await import('./locales/es/settings.json')).default;
        resources.storageProviders = (await import('./locales/es/storageProviders.json')).default;
        resources.functions = (await import('./locales/es/functions.json')).default;
        resources.ceph = (await import('./locales/es/ceph.json')).default;
        resources.organization = (await import('./locales/es/organization.json')).default;
        break;
      case 'tr':
        resources.auth = (await import('./locales/tr/auth.json')).default;
        resources.common = (await import('./locales/tr/common.json')).default;
        resources.resources = (await import('./locales/tr/resources.json')).default;
        resources.machines = (await import('./locales/tr/machines.json')).default;
        resources.system = (await import('./locales/tr/system.json')).default;
        resources.queue = (await import('./locales/tr/queue.json')).default;
        resources.settings = (await import('./locales/tr/settings.json')).default;
        resources.storageProviders = (await import('./locales/tr/storageProviders.json')).default;
        resources.functions = (await import('./locales/tr/functions.json')).default;
        resources.ceph = (await import('./locales/tr/ceph.json')).default;
        resources.organization = (await import('./locales/tr/organization.json')).default;
        break;
      case 'fr':
        resources.auth = (await import('./locales/fr/auth.json')).default;
        resources.common = (await import('./locales/fr/common.json')).default;
        resources.resources = (await import('./locales/fr/resources.json')).default;
        resources.machines = (await import('./locales/fr/machines.json')).default;
        resources.system = (await import('./locales/fr/system.json')).default;
        resources.queue = (await import('./locales/fr/queue.json')).default;
        resources.settings = (await import('./locales/fr/settings.json')).default;
        resources.storageProviders = (await import('./locales/fr/storageProviders.json')).default;
        resources.functions = (await import('./locales/fr/functions.json')).default;
        resources.ceph = (await import('./locales/fr/ceph.json')).default;
        resources.organization = (await import('./locales/fr/organization.json')).default;
        break;
      case 'de':
        resources.auth = (await import('./locales/de/auth.json')).default;
        resources.common = (await import('./locales/de/common.json')).default;
        resources.resources = (await import('./locales/de/resources.json')).default;
        resources.machines = (await import('./locales/de/machines.json')).default;
        resources.system = (await import('./locales/de/system.json')).default;
        resources.queue = (await import('./locales/de/queue.json')).default;
        resources.settings = (await import('./locales/de/settings.json')).default;
        resources.storageProviders = (await import('./locales/de/storageProviders.json')).default;
        resources.functions = (await import('./locales/de/functions.json')).default;
        resources.ceph = (await import('./locales/de/ceph.json')).default;
        resources.organization = (await import('./locales/de/organization.json')).default;
        break;
      case 'zh':
        resources.auth = (await import('./locales/zh/auth.json')).default;
        resources.common = (await import('./locales/zh/common.json')).default;
        resources.resources = (await import('./locales/zh/resources.json')).default;
        resources.machines = (await import('./locales/zh/machines.json')).default;
        resources.system = (await import('./locales/zh/system.json')).default;
        resources.queue = (await import('./locales/zh/queue.json')).default;
        resources.settings = (await import('./locales/zh/settings.json')).default;
        resources.storageProviders = (await import('./locales/zh/storageProviders.json')).default;
        resources.functions = (await import('./locales/zh/functions.json')).default;
        resources.ceph = (await import('./locales/zh/ceph.json')).default;
        resources.organization = (await import('./locales/zh/organization.json')).default;
        break;
      case 'ja':
        resources.auth = (await import('./locales/ja/auth.json')).default;
        resources.common = (await import('./locales/ja/common.json')).default;
        resources.resources = (await import('./locales/ja/resources.json')).default;
        resources.machines = (await import('./locales/ja/machines.json')).default;
        resources.system = (await import('./locales/ja/system.json')).default;
        resources.queue = (await import('./locales/ja/queue.json')).default;
        resources.settings = (await import('./locales/ja/settings.json')).default;
        resources.storageProviders = (await import('./locales/ja/storageProviders.json')).default;
        resources.functions = (await import('./locales/ja/functions.json')).default;
        resources.ceph = (await import('./locales/ja/ceph.json')).default;
        resources.organization = (await import('./locales/ja/organization.json')).default;
        break;
      case 'ar':
        resources.auth = (await import('./locales/ar/auth.json')).default;
        resources.common = (await import('./locales/ar/common.json')).default;
        resources.resources = (await import('./locales/ar/resources.json')).default;
        resources.machines = (await import('./locales/ar/machines.json')).default;
        resources.system = (await import('./locales/ar/system.json')).default;
        resources.queue = (await import('./locales/ar/queue.json')).default;
        resources.settings = (await import('./locales/ar/settings.json')).default;
        resources.storageProviders = (await import('./locales/ar/storageProviders.json')).default;
        resources.functions = (await import('./locales/ar/functions.json')).default;
        resources.ceph = (await import('./locales/ar/ceph.json')).default;
        resources.organization = (await import('./locales/ar/organization.json')).default;
        break;
      case 'ru':
        resources.auth = (await import('./locales/ru/auth.json')).default;
        resources.common = (await import('./locales/ru/common.json')).default;
        resources.resources = (await import('./locales/ru/resources.json')).default;
        resources.machines = (await import('./locales/ru/machines.json')).default;
        resources.system = (await import('./locales/ru/system.json')).default;
        resources.queue = (await import('./locales/ru/queue.json')).default;
        resources.settings = (await import('./locales/ru/settings.json')).default;
        resources.storageProviders = (await import('./locales/ru/storageProviders.json')).default;
        resources.functions = (await import('./locales/ru/functions.json')).default;
        resources.ceph = (await import('./locales/ru/ceph.json')).default;
        resources.organization = (await import('./locales/ru/organization.json')).default;
        break;
    }

    // Add resources to i18n
    Object.keys(resources).forEach((ns) => {
      i18n.addResourceBundle(lng, ns, resources[ns]);
    });
  } catch {
    // Failed to load language resources
  }
};

// Configure language detector with custom cookie detector
const languageDetector = new LanguageDetector();
languageDetector.addDetector(cookieDetector);

// Initialize i18n with lazy loading
void i18n
  .use(languageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    lng: 'en',
    debug: false,
    ns: [
      'common',
      'auth',
      'resources',
      'machines',
      'system',
      'queue',
      'settings',
      'storageProviders',
      'functions',
      'ceph',
      'organization',
      SHARED_NAMESPACE,
    ],
    defaultNS,
    resources: initialResources,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['cookieDetector', 'navigator'],
      caches: ['cookieDetector'],
    },
    react: {
      useSuspense: false, // Disable suspense to prevent blocking
      bindI18n: 'languageChanged loaded', // Re-render components when language changes
      bindI18nStore: 'added removed', // Re-render when translations are added/removed
      transEmptyNodeValue: '', // Prevent showing keys for empty translations
      transSupportBasicHtmlNodes: true,
      transKeepBasicHtmlNodesFor: ['br', 'strong', 'i', 'p'],
    },
  });

// Listen for language changes to load resources dynamically
i18n.on('languageChanged', (lng) => {
  void loadLanguageResources(lng);
});

export default i18n;
