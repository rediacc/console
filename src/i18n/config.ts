import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import enAuth from './locales/en/auth.json';
import enCommon from './locales/en/common.json';
import enOrganization from './locales/en/organization.json';
import enMachines from './locales/en/machines.json';
import enUsers from './locales/en/users.json';
import enQueue from './locales/en/queue.json';
import enSettings from './locales/en/settings.json';

import esAuth from './locales/es/auth.json';
import esCommon from './locales/es/common.json';
import esOrganization from './locales/es/organization.json';
import esMachines from './locales/es/machines.json';
import esUsers from './locales/es/users.json';
import esQueue from './locales/es/queue.json';
import esSettings from './locales/es/settings.json';

export const defaultNS = 'common';
export const resources = {
  en: {
    common: enCommon,
    auth: enAuth,
    organization: enOrganization,
    machines: enMachines,
    users: enUsers,
    queue: enQueue,
    settings: enSettings,
  },
  es: {
    common: esCommon,
    auth: esAuth,
    organization: esOrganization,
    machines: esMachines,
    users: esUsers,
    queue: esQueue,
    settings: esSettings,
  },
} as const;

// Initialize i18n and wait for it to be ready
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    lng: 'en',
    debug: false,
    ns: ['common', 'auth', 'organization', 'machines', 'users', 'queue', 'settings'],
    defaultNS,
    resources,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
    react: {
      useSuspense: true,
      wait: true
    }
  });

export default i18n;