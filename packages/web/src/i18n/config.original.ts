import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import enAuth from './locales/en/auth.json';
import enCommon from './locales/en/common.json';
import enResources from './locales/en/resources.json';
import enMachines from './locales/en/machines.json';
import enSystem from './locales/en/system.json';
import enQueue from './locales/en/queue.json';
import enSettings from './locales/en/settings.json';
import enStorageProviders from './locales/en/storageProviders.json';
import enFunctions from './locales/en/functions.json';

import esAuth from './locales/es/auth.json';
import esCommon from './locales/es/common.json';
import esResources from './locales/es/resources.json';
import esMachines from './locales/es/machines.json';
import esSystem from './locales/es/system.json';
import esQueue from './locales/es/queue.json';
import esSettings from './locales/es/settings.json';
import esStorageProviders from './locales/es/storageProviders.json';
import esFunctions from './locales/es/functions.json';

import trAuth from './locales/tr/auth.json';
import trCommon from './locales/tr/common.json';
import trResources from './locales/tr/resources.json';
import trMachines from './locales/tr/machines.json';
import trSystem from './locales/tr/system.json';
import trQueue from './locales/tr/queue.json';
import trSettings from './locales/tr/settings.json';
import trStorageProviders from './locales/tr/storageProviders.json';
import trFunctions from './locales/tr/functions.json';

import frAuth from './locales/fr/auth.json';
import frCommon from './locales/fr/common.json';
import frResources from './locales/fr/resources.json';
import frMachines from './locales/fr/machines.json';
import frSystem from './locales/fr/system.json';
import frQueue from './locales/fr/queue.json';
import frSettings from './locales/fr/settings.json';
import frStorageProviders from './locales/fr/storageProviders.json';
import frFunctions from './locales/fr/functions.json';

import deAuth from './locales/de/auth.json';
import deCommon from './locales/de/common.json';
import deResources from './locales/de/resources.json';
import deMachines from './locales/de/machines.json';
import deSystem from './locales/de/system.json';
import deQueue from './locales/de/queue.json';
import deSettings from './locales/de/settings.json';
import deStorageProviders from './locales/de/storageProviders.json';
import deFunctions from './locales/de/functions.json';

import zhAuth from './locales/zh/auth.json';
import zhCommon from './locales/zh/common.json';
import zhResources from './locales/zh/resources.json';
import zhMachines from './locales/zh/machines.json';
import zhSystem from './locales/zh/system.json';
import zhQueue from './locales/zh/queue.json';
import zhSettings from './locales/zh/settings.json';
import zhStorageProviders from './locales/zh/storageProviders.json';
import zhFunctions from './locales/zh/functions.json';

import jaAuth from './locales/ja/auth.json';
import jaCommon from './locales/ja/common.json';
import jaResources from './locales/ja/resources.json';
import jaMachines from './locales/ja/machines.json';
import jaSystem from './locales/ja/system.json';
import jaQueue from './locales/ja/queue.json';
import jaSettings from './locales/ja/settings.json';
import jaStorageProviders from './locales/ja/storageProviders.json';
import jaFunctions from './locales/ja/functions.json';

import arAuth from './locales/ar/auth.json';
import arCommon from './locales/ar/common.json';
import arResources from './locales/ar/resources.json';
import arMachines from './locales/ar/machines.json';
import arSystem from './locales/ar/system.json';
import arQueue from './locales/ar/queue.json';
import arSettings from './locales/ar/settings.json';
import arStorageProviders from './locales/ar/storageProviders.json';
import arFunctions from './locales/ar/functions.json';

import ruAuth from './locales/ru/auth.json';
import ruCommon from './locales/ru/common.json';
import ruResources from './locales/ru/resources.json';
import ruMachines from './locales/ru/machines.json';
import ruSystem from './locales/ru/system.json';
import ruQueue from './locales/ru/queue.json';
import ruSettings from './locales/ru/settings.json';
import ruStorageProviders from './locales/ru/storageProviders.json';
import ruFunctions from './locales/ru/functions.json';

export const defaultNS = 'common';
export const resources = {
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
  },
  es: {
    common: esCommon,
    auth: esAuth,
    resources: esResources,
    machines: esMachines,
    system: esSystem,
    queue: esQueue,
    settings: esSettings,
    storageProviders: esStorageProviders,
    functions: esFunctions,
  },
  tr: {
    common: trCommon,
    auth: trAuth,
    resources: trResources,
    machines: trMachines,
    system: trSystem,
    queue: trQueue,
    settings: trSettings,
    storageProviders: trStorageProviders,
    functions: trFunctions,
  },
  fr: {
    common: frCommon,
    auth: frAuth,
    resources: frResources,
    machines: frMachines,
    system: frSystem,
    queue: frQueue,
    settings: frSettings,
    storageProviders: frStorageProviders,
    functions: frFunctions,
  },
  de: {
    common: deCommon,
    auth: deAuth,
    resources: deResources,
    machines: deMachines,
    system: deSystem,
    queue: deQueue,
    settings: deSettings,
    storageProviders: deStorageProviders,
    functions: deFunctions,
  },
  zh: {
    common: zhCommon,
    auth: zhAuth,
    resources: zhResources,
    machines: zhMachines,
    system: zhSystem,
    queue: zhQueue,
    settings: zhSettings,
    storageProviders: zhStorageProviders,
    functions: zhFunctions,
  },
  ja: {
    common: jaCommon,
    auth: jaAuth,
    resources: jaResources,
    machines: jaMachines,
    system: jaSystem,
    queue: jaQueue,
    settings: jaSettings,
    storageProviders: jaStorageProviders,
    functions: jaFunctions,
  },
  ar: {
    common: arCommon,
    auth: arAuth,
    resources: arResources,
    machines: arMachines,
    system: arSystem,
    queue: arQueue,
    settings: arSettings,
    storageProviders: arStorageProviders,
    functions: arFunctions,
  },
  ru: {
    common: ruCommon,
    auth: ruAuth,
    resources: ruResources,
    machines: ruMachines,
    system: ruSystem,
    queue: ruQueue,
    settings: ruSettings,
    storageProviders: ruStorageProviders,
    functions: ruFunctions,
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
    },
  });

export default i18n;
